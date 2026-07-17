import logging
import shutil
import subprocess
import sys
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from awsimple import S3Access
from balsa import get_logger

logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences

log = get_logger(__application_name__)


# sundry candidate
def get_dir_size(dir_path: Path):
    dir_size = 0
    file_count = 0
    for root, _, file_names in os.walk(dir_path):
        for file_name in file_names:
            file_count += 1
            dir_size += os.path.getsize(os.path.join(root, file_name))
    return dir_size, file_count


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


class S3Backup(BupBase):

    backup_type = BackupTypes.S3

    def run(self):

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run

        backup_directory = os.path.join(preferences.backup_directory, "s3")

        os.makedirs(backup_directory, exist_ok=True)

        s3_access = S3Access(
            profile_name=preferences.aws_profile or None,
            aws_access_key_id=preferences.aws_access_key_id or None,
            aws_secret_access_key=preferences.aws_secret_access_key or None,
            region_name=preferences.aws_region or None,
        )

        decoding = "utf-8"

        # we delete all whitespace below
        ls_re = re.compile(r"TotalObjects:([0-9]+)TotalSize:([0-9]+)")

        aws_cli_path, python_path = find_aws_cli()
        if aws_cli_path is None:
            self.error_out("AWS CLI executable not found - S3 backup cannot run")
            return

        # The AWS CLI app also needs the python executable to be in the path if it's not in the same dir, which happens when this program is installed.
        # Make the directory of our python.exe the first in the list so it's found and not any of the others that may or may not be in the PATH.
        env_var = os.environ.copy()
        env_var["PATH"] = f"{str(python_path.parent)}{os.pathsep}{env_var.get('PATH', '')}"

        buckets = s3_access.bucket_list()
        self.info_out(f"found {len(buckets)} buckets")

        count = 0
        dry_run_count = 0
        exclusions_no_comments = ExclusionPreferences(BackupTypes.S3.name).get_no_comments()
        for bucket_name in buckets:
            if self.stop_requested:
                break

            # do the sync
            if bucket_name in exclusions_no_comments:
                self.info_out(f"excluding {bucket_name}")
                continue

            if dry_run:
                self.info_out(f"dry run {bucket_name}")
            else:
                self.info_out(f"{bucket_name}")

            destination = Path(backup_directory, bucket_name)
            os.makedirs(destination, exist_ok=True)
            s3_bucket_path = f"s3://{bucket_name}"
            # Don't use --delete.  We want to keep 'old' files locally.
            sync_command_line = [str(aws_cli_path), "s3", "sync", s3_bucket_path, str(destination.absolute())]
            if dry_run:
                sync_command_line.append("--dryrun")
            log.info(subprocess.list2cmdline(sync_command_line))

            try:
                sync_result = subprocess.run(sync_command_line, env=env_var, capture_output=True)
            except (FileNotFoundError, OSError) as e:
                self.error_out(f'error executing {" ".join(sync_command_line)} {e}')
                return

            for line in sync_result.stdout.decode(decoding).splitlines():
                log.info(f"{bucket_name}:{line.strip()}")
            for line in sync_result.stderr.decode(decoding).splitlines():
                line = line.strip()
                if line:
                    self.warning_out(f"{bucket_name}:{line}")
            if sync_result.returncode != 0:
                self.error_out(f"aws s3 sync failed (exit code {sync_result.returncode}) for {bucket_name}")
                continue  # don't count or verify a failed sync

            # check the results (skip during dry run - nothing was synced)
            if dry_run:
                dry_run_count += 1
                continue
            ls_command_line = [str(aws_cli_path), "s3", "ls", "--summarize", "--recursive", s3_bucket_path]
            ls_command_line_str = subprocess.list2cmdline(ls_command_line)
            log.info(ls_command_line_str)
            ls_result = subprocess.run(ls_command_line, env=env_var, capture_output=True)
            for line in ls_result.stderr.decode(decoding).splitlines():
                line = line.strip()
                if line:
                    self.warning_out(f"{bucket_name}:{line}")
            ls_stdout = "".join([c for c in ls_result.stdout.decode(decoding) if c not in " \r\n"])  # remove all whitespace
            if len(ls_stdout) == 0:
                self.error_out(f'"{ls_command_line_str}" failed ({ls_stdout=}) - check internet connection')
            else:
                ls_parsed = ls_re.search(ls_stdout)
                if ls_parsed is None:
                    self.error_out(f"parse error:\n{ls_command_line_str=}\n{ls_stdout=}")
                else:
                    count += 1
                    s3_object_count = int(ls_parsed.group(1))
                    s3_total_size = int(ls_parsed.group(2))
                    local_size, local_count = get_dir_size(destination)

                    # rough check that the sync worked
                    if s3_total_size > local_size:
                        # we're missing files
                        message = "not all files backed up"
                        output_routine = self.error_out
                    elif s3_total_size != local_size:
                        # Compare size, not number of files, since aws s3 sync does not copy files of zero size.
                        message = "mismatch"
                        output_routine = self.warning_out
                    else:
                        message = "match"
                        output_routine = log.info
                    output_routine(f"{bucket_name} : {message} (s3_count={s3_object_count}, local_count={local_count}; s3_total_size={s3_total_size}, local_size={local_size})")

        if dry_run:
            self.info_out(f"{len(buckets)} buckets, {dry_run_count} dry run, {len(exclusions_no_comments)} excluded")
        else:
            self.info_out(f"{len(buckets)} buckets, {count} backed up, {len(exclusions_no_comments)} excluded")
