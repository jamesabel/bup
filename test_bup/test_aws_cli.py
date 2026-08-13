from pathlib import Path
from unittest.mock import patch, MagicMock

from bup.aws_cli import get_aws_cli_version, get_latest_awscli_version, parse_version, check_aws_cli_version


def _make_completed_process(stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    completed_process = MagicMock()
    completed_process.stdout = stdout
    completed_process.stderr = stderr
    return completed_process


def test_get_aws_cli_version_from_stdout():
    with patch("bup.aws_cli.subprocess.run", return_value=_make_completed_process(stdout=b"aws-cli/1.42.35 Python/3.13.0 Windows/11 botocore/1.40.35")):
        assert get_aws_cli_version(Path("aws"), {}) == "1.42.35"


def test_get_aws_cli_version_from_stderr():
    # older AWS CLI versions write --version output to stderr
    with patch("bup.aws_cli.subprocess.run", return_value=_make_completed_process(stderr=b"aws-cli/1.16.0 Python/3.6.0 Windows/10 botocore/1.12.0")):
        assert get_aws_cli_version(Path("aws"), {}) == "1.16.0"


def test_get_aws_cli_version_unparseable_output():
    with patch("bup.aws_cli.subprocess.run", return_value=_make_completed_process(stdout=b"something unexpected")):
        assert get_aws_cli_version(Path("aws"), {}) is None


def test_get_aws_cli_version_executable_not_found():
    with patch("bup.aws_cli.subprocess.run", side_effect=FileNotFoundError("no such file")):
        assert get_aws_cli_version(Path("aws"), {}) is None


def test_get_latest_awscli_version():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"info": {"version": "1.43.0"}}'
    with patch("bup.aws_cli.urllib.request.urlopen", return_value=response):
        assert get_latest_awscli_version() == "1.43.0"


def test_get_latest_awscli_version_offline():
    with patch("bup.aws_cli.urllib.request.urlopen", side_effect=OSError("no network")):
        assert get_latest_awscli_version() is None


def test_parse_version():
    assert parse_version("1.42.35") == (1, 42, 35)
    assert parse_version("2.0") == (2, 0)
    assert parse_version("1.2.3rc1") is None
    assert parse_version("") is None


def test_check_aws_cli_version_up_to_date():
    level, message = check_aws_cli_version("1.42.35", "1.42.35")
    assert level == "info"
    assert "up to date" in message
    assert "latest: 1.42.35" in message


def test_check_aws_cli_version_newer_than_latest_is_info():
    level, _unused_message = check_aws_cli_version("1.42.36", "1.42.35")
    assert level == "info"


def test_check_aws_cli_version_outdated():
    level, message = check_aws_cli_version("1.42.34", "1.42.35")
    assert level == "warning"
    assert "not the latest" in message
    assert "1.42.34" in message
    assert "1.42.35" in message


def test_check_aws_cli_version_installed_unknown():
    level, message = check_aws_cli_version(None, "1.42.35")
    assert level == "warning"
    assert "installed" in message


def test_check_aws_cli_version_latest_unknown():
    level, message = check_aws_cli_version("1.42.35", None)
    assert level == "warning"
    assert "latest" in message


def test_check_aws_cli_version_unparseable():
    level, message = check_aws_cli_version("1.42.35", "not-a-version")
    assert level == "warning"
    assert "could not compare" in message
