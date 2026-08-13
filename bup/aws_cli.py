import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)

decoding = "utf-8"

awscli_pypi_url = "https://pypi.org/pypi/awscli/json"


def find_aws_cli() -> Tuple[Optional[Path], Optional[Path]]:
    """
    Locate the AWS CLI executable and the python executable it should run with.
    Use sys.executable to reliably locate python and aws CLI in the same directory,
    which works for both local venv and installed app scenarios.
    :return: (aws_cli_path, python_path), or (None, None) if not found
    """
    python_exe = Path(sys.executable)
    aws_names = ["aws.cmd", "aws.exe", "aws"] if sys.platform == "win32" else ["aws"]
    aws_candidates = (
        [(python_exe, python_exe.parent / name) for name in aws_names]  # same dir as python (venv Scripts/)
        + [(python_exe, python_exe.parent / "Scripts" / name) for name in aws_names]  # CLIP layout: python at root, scripts in Scripts/
        + [(Path("venv", "Scripts", "python.exe").absolute(), Path("venv", "Scripts", name).absolute()) for name in aws_names]  # local venv from CWD
    )
    for p, a in aws_candidates:
        if p.exists() and a.exists():
            return a, p

    # fall back to whatever is on the system PATH
    aws_in_path = shutil.which("aws")
    if aws_in_path:
        return Path(aws_in_path), python_exe

    log.error(f"AWS CLI executable not found ({aws_candidates=})")
    return None, None


def make_aws_cli_env(python_path: Path) -> dict:
    """
    Environment for running the AWS CLI. The AWS CLI needs the python executable to be in the PATH if it's not in the same dir, which happens
    when this program is installed. Make the directory of our python.exe the first in the list so it's found and not any of the others that
    may or may not be in the PATH.
    """
    env_var = os.environ.copy()
    env_var["PATH"] = f"{str(python_path.parent)}{os.pathsep}{env_var.get('PATH', '')}"
    return env_var


def get_aws_cli_version(aws_cli_path: Path, env_var: dict) -> Optional[str]:
    """
    Version of the given AWS CLI executable (e.g. "1.42.35"), from "aws --version".
    :return: the version string, or None if it could not be determined
    """
    command_line = [str(aws_cli_path), "--version"]
    try:
        result = subprocess.run(command_line, env=env_var, capture_output=True, timeout=60.0)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning(f'error executing {" ".join(command_line)} : {e}')
        return None
    # output looks like "aws-cli/1.42.35 Python/3.13.0 Windows/11 botocore/1.40.35" (older AWS CLI versions write it to stderr, newer to stdout)
    output = f"{result.stdout.decode(decoding, errors='replace')} {result.stderr.decode(decoding, errors='replace')}"
    match = re.search(r"aws-cli/(\S+)", output)
    if match is None:
        log.warning(f'could not parse AWS CLI version from "{output.strip()}"')
        return None
    return match.group(1)


def get_latest_awscli_version(timeout: float = 10.0) -> Optional[str]:
    """
    Latest awscli version published on PyPI (the AWS CLI is pip-installed as the awscli package).
    :return: the version string, or None if it could not be determined (e.g. offline)
    """
    try:
        with urllib.request.urlopen(awscli_pypi_url, timeout=timeout) as response:
            package_info = json.load(response)
        return package_info["info"]["version"]
    except (OSError, ValueError, KeyError) as e:
        # OSError covers URLError and timeouts, ValueError covers JSONDecodeError
        log.info(f"could not get latest awscli version from {awscli_pypi_url} : {e}")
        return None


def parse_version(version: str) -> Optional[Tuple[int, ...]]:
    """
    Parse a dotted numeric version string (e.g. "1.42.35") into a comparable tuple of ints.
    :return: the tuple, or None if the string is not a dotted numeric version
    """
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def check_aws_cli_version(installed_version: Optional[str], latest_version: Optional[str]) -> Tuple[str, str]:
    """
    Check that the installed AWS CLI is the latest available.
    :return: (level, message) where level is "warning" or "info"
    """
    if installed_version is None:
        return "warning", "could not determine the installed AWS CLI version"
    if latest_version is None:
        return "warning", f"could not determine the latest AWS CLI version (installed: {installed_version})"
    installed = parse_version(installed_version)
    latest = parse_version(latest_version)
    if installed is None or latest is None:
        return "warning", f"could not compare AWS CLI versions (installed: {installed_version}, latest: {latest_version})"
    if installed < latest:
        return "warning", f'AWS CLI {installed_version} is not the latest ({latest_version}) - upgrade with "pip install --upgrade awscli"'
    return "info", f"AWS CLI {installed_version} is up to date (latest: {latest_version})"
