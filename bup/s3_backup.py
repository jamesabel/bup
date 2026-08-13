import logging
import subprocess
import os
from pathlib import Path
from typing import Tuple

from awsimple import S3Access
from botocore.exceptions import BotoCoreError, ClientError
from balsa import get_logger

logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences
from bup.aws_cli import find_aws_cli, make_aws_cli_env, get_aws_cli_version, get_latest_awscli_version, check_aws_cli_version

log = get_logger(__application_name__)

decoding = "utf-8"


# sundry candidate
def get_dir_size(dir_path: Path) -> Tuple[int, int]:
    dir_size = 0
    file_count = 0
    for root, _unused_dir_names, file_names in os.walk(dir_path):
        for file_name in file_names:
            file_path = os.path.join(root, file_name)
            try:
                dir_size += os.path.getsize(file_path)
                file_count += 1
            except OSError as e:
                # e.g. file removed mid-walk, or path too long for the OS API - don't let one file kill the backup
                log.warning(f'could not get size of "{file_path}" : {e}')
    return dir_size, file_count


def get_bucket_size(s3_client, bucket_name: str) -> Tuple[int, int]:
    """
    Total size (bytes) and object count of an S3 bucket, via the boto3 client.
    :return: (total_size, object_count)
    """
    total_size = 0
    object_count = 0
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        for s3_object in page.get("Contents", []):
            total_size += s3_object["Size"]
            object_count += 1
    return total_size, object_count


def count_synced_files(sync_stdout: str) -> int:
    """
    Number of files "aws s3 sync" transferred (or would transfer, for a dry run), from its stdout -
    the CLI emits one "download:" (or "copy:") line per file, and nothing for files already up to date.
    """
    synced_count = 0
    for line in sync_stdout.splitlines():
        line = line.strip()
        if line.startswith("(dryrun) "):
            line = line[len("(dryrun) ") :]
        if line.startswith(("download:", "copy:")):
            synced_count += 1
    return synced_count


def compare_backup_sizes(s3_total_size: int, local_size: int) -> Tuple[str, str]:
    """
    Rough check that the sync worked, based on total sizes.
    :return: (level, message) where level is "error" or "info"
    """
    if s3_total_size > local_size:
        # we're missing files
        return "error", "not all files backed up"
    elif s3_total_size < local_size:
        # expected over time - sync intentionally doesn't use --delete, so files deleted from S3 are retained locally
        return "info", "local backup is larger than S3 (files deleted from S3 are retained locally)"
    else:
        return "info", "match"


class S3Backup(BupBase):

    backup_type = BackupTypes.S3

    def run_stoppable_subprocess(self, command_line: list, env_var: dict) -> Tuple[int, str, str]:
        """
        Run a subprocess, polling for a stop request. On stop, terminate the subprocess so it isn't orphaned.
        :return: (returncode, stdout, stderr)
        """
        process = subprocess.Popen(command_line, env=env_var, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            try:
                stdout, stderr = process.communicate(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                if self.stop_requested:
                    process.terminate()
                    stdout, stderr = process.communicate()
                    break
        return process.returncode, stdout.decode(decoding, errors="replace"), stderr.decode(decoding, errors="replace")

    def run_backup(self):

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

        aws_cli_path, python_path = find_aws_cli()
        if aws_cli_path is None:
            self.error_out("AWS CLI executable not found - S3 backup cannot run")
            return

        env_var = make_aws_cli_env(python_path)

        # check that the AWS CLI doing the backups is the latest available (warn but proceed - an outdated CLI can still back up)
        aws_cli_version_level, aws_cli_version_message = check_aws_cli_version(get_aws_cli_version(aws_cli_path, env_var), get_latest_awscli_version())
        {"warning": self.warning_out, "info": self.info_out}[aws_cli_version_level](aws_cli_version_message)

        try:
            buckets = s3_access.bucket_list()
        except (ClientError, BotoCoreError) as e:
            self.error_out(f"could not list S3 buckets - check credentials and connectivity : {e}")
            return
        self.info_out(f"found {len(buckets)} buckets")

        count = 0
        dry_run_count = 0
        total_synced_count = 0
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
                sync_returncode, sync_stdout, sync_stderr = self.run_stoppable_subprocess(sync_command_line, env_var)
            except (FileNotFoundError, OSError) as e:
                self.error_out(f'error executing {" ".join(sync_command_line)} {e}')
                return

            if self.stop_requested:
                break

            for line in sync_stdout.splitlines():
                log.info(f"{bucket_name}:{line.strip()}")
            for line in sync_stderr.splitlines():
                line = line.strip()
                if line:
                    self.warning_out(f"{bucket_name}:{line}")
            if sync_returncode != 0:
                self.error_out(f"aws s3 sync failed (exit code {sync_returncode}) for {bucket_name}")
                continue  # don't count or verify a failed sync

            synced_count = count_synced_files(sync_stdout)
            total_synced_count += synced_count

            # check the results (skip during dry run - nothing was synced)
            if dry_run:
                dry_run_count += 1
                self.info_out(f"{bucket_name} : {synced_count} files would be synced")
                continue

            try:
                s3_total_size, s3_object_count = get_bucket_size(s3_access.client, bucket_name)
            except (ClientError, BotoCoreError) as e:
                self.error_out(f"could not list contents of {bucket_name} to verify the sync : {e}")
                continue

            count += 1
            local_size, local_count = get_dir_size(destination)
            level, message = compare_backup_sizes(s3_total_size, local_size)
            output_routines = {"error": self.error_out, "info": log.info}
            output_routines[level](
                f"{bucket_name} : {message} (synced={synced_count}, s3_count={s3_object_count}, local_count={local_count}; s3_total_size={s3_total_size}, local_size={local_size})"
            )

        if dry_run:
            self.info_out(f"{len(buckets)} buckets, {dry_run_count} dry run, {total_synced_count} files would be synced, {len(exclusions_no_comments)} excluded")
        else:
            self.info_out(f"{len(buckets)} buckets, {count} backed up, {total_synced_count} files synced, {len(exclusions_no_comments)} excluded")
