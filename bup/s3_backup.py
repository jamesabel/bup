import logging
import subprocess
import os
import unicodedata
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from awsimple import S3Access
from botocore.exceptions import BotoCoreError, ClientError
from balsa import get_logger

logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences
from bup.aws_cli import find_aws_cli, make_aws_cli_env, get_aws_cli_version, get_latest_awscli_version, check_aws_cli_version, subprocess_creation_flags

log = get_logger(__application_name__)

decoding = "utf-8"

max_keys_to_list = 20  # cap on the S3 keys named in one diagnostic message


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


def is_folder_marker(s3_object: dict) -> bool:
    """
    True for a zero-byte object whose key ends in "/" (e.g. from the S3 console's "Create folder"). "aws s3 sync" never downloads
    these (it only creates the local directory), so they are in the S3 object count but can never be in the local file count.
    """
    return s3_object["Size"] == 0 and s3_object["Key"].endswith("/")


def get_local_keys(dir_path: Path) -> set:
    """
    The S3-key-style relative paths ("/" separated) of every file under dir_path - what "aws s3 sync" matches S3 keys against.
    """
    local_keys = set()
    for root, _unused_dir_names, file_names in os.walk(dir_path):
        for file_name in file_names:
            local_keys.add(os.path.relpath(os.path.join(root, file_name), dir_path).replace(os.sep, "/"))
    return local_keys


def find_s3_objects_without_local_file(s3_client, bucket_name: str, destination: Path) -> Tuple[List[str], List[str]]:
    """
    Explain why the S3 object count exceeds the local file count: which objects are folder markers (never downloaded - expected),
    and which objects have no local file at exactly the key's path (unexpected).
    :return: (folder_marker_keys, missing_keys)
    """
    local_keys = get_local_keys(destination)
    folder_marker_keys = []
    missing_keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        for s3_object in page.get("Contents", []):
            key = s3_object["Key"]
            if is_folder_marker(s3_object):
                folder_marker_keys.append(key)
            elif key not in local_keys:
                missing_keys.append(key)
    return folder_marker_keys, missing_keys


class LocalNameMismatch(NamedTuple):
    """
    A local file or directory whose name differs from the corresponding component of an S3 key in a way "aws s3 sync" does not match.
    """

    directory: Path  # the directory holding the entry
    local_name: str
    key_name: str
    difference: str  # how the two names differ

    def __str__(self):
        return f'local name "{self.local_name}" differs from S3 key "{self.key_name}" {self.difference}'


def find_local_name_mismatches(destination: Path, key: str) -> List[LocalNameMismatch]:
    """
    Why "aws s3 sync" would not consider the local copy of an S3 object to be the same file. Sync matches the S3 key against the
    local relative path as an exact string, but Windows opens files case-insensitively and silently strips trailing spaces and dots,
    so a download can land in an existing file or directory under a different name - and be downloaded again on every run.
    :return: one entry per near-miss along the key's path, outermost first (empty if the local path matches the key exactly, or if
             nothing similarly named exists locally - e.g. a dry run, where nothing has been downloaded yet)
    """
    mismatches = []
    current_dir = destination
    for component in key.split("/"):
        entries = os.listdir(current_dir)
        if component in entries:
            current_dir = Path(current_dir, component)
            continue
        matched_entry = None
        for entry in entries:
            if entry.lower() == component.lower():
                difference = "only in case"
            elif unicodedata.normalize("NFC", entry) == unicodedata.normalize("NFC", component):
                difference = "only in Unicode normalization"
            elif entry == component.rstrip(" ."):
                difference = "only by the trailing space or dot, which Windows strips from file names"
            else:
                continue
            matched_entry = entry
            mismatches.append(LocalNameMismatch(current_dir, entry, component, difference))
            break
        if matched_entry is None:
            break
        current_dir = Path(current_dir, matched_entry)
    return mismatches


def rename_local_to_match_key(destination: Path, key: str) -> Tuple[List[str], Optional[str]]:
    """
    Rename the local file and/or directories of an S3 object so the local path is exactly the key, outermost first - renaming a
    directory moves everything under it, so the path is re-checked after each rename.
    :return: (one message per rename done, why the path still doesn't match - or None if it now does)
    """
    renames = []
    while True:
        mismatches = find_local_name_mismatches(destination, key)
        if not mismatches:
            return renames, None
        mismatch = mismatches[0]
        old_path = Path(mismatch.directory, mismatch.local_name)
        try:
            os.rename(old_path, Path(mismatch.directory, mismatch.key_name))
        except OSError as e:
            return renames, f'could not rename "{old_path}" to "{mismatch.key_name}" : {e}'
        if mismatch.key_name not in os.listdir(mismatch.directory):
            # e.g. Windows silently stripped the key's trailing space or dot, so the name on disk can't be made to match
            return renames, f'the file system will not store the name "{mismatch.key_name}" (renaming "{old_path}" to it had no effect)'
        renames.append(f'renamed "{old_path}" to "{mismatch.key_name}"')


def get_synced_keys(sync_stdout: str, bucket_name: str, destination: Path) -> List[str]:
    """
    The S3 keys "aws s3 sync" downloaded (or would download, for a dry run), from its stdout. Each line is
    "download: s3://<bucket>/<key> to <destination><sep><key with OS separators>"; since a key may itself contain " to ",
    the key is the prefix whose local path reconstructs the rest of the line.
    """
    synced_keys = []
    s3_prefix = f"s3://{bucket_name}/"
    local_prefix = f"{destination}{os.sep}"
    for line in sync_stdout.splitlines():
        line = line.strip()
        if line.startswith("(dryrun) "):
            line = line[len("(dryrun) ") :]
        if not line.startswith("download: "):
            continue
        line = line[len("download: ") :]
        if not line.startswith(s3_prefix):
            log.warning(f'unexpected "aws s3 sync" output for {bucket_name} : "{line}"')
            continue
        line = line[len(s3_prefix) :]
        key = None
        separator_index = line.find(" to ")
        while separator_index >= 0:
            candidate_key = line[:separator_index]
            if line[separator_index + len(" to ") :] == local_prefix + candidate_key.replace("/", os.sep):
                key = candidate_key
                break
            separator_index = line.find(" to ", separator_index + 1)
        if key is None:
            log.warning(f'could not determine the S3 key from "aws s3 sync" output for {bucket_name} : "{line}"')
            continue
        synced_keys.append(key)
    return synced_keys


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
        process = subprocess.Popen(command_line, env=env_var, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess_creation_flags)
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

    def explain_missing_local_files(self, s3_client, bucket_name: str, destination: Path, count_difference: int):
        """
        Say why the S3 object count exceeds the local file count: folder markers are expected (application log only), objects with no
        exactly-named local file are not (a warning in the backup output, with the reason when a near-match is found on disk).
        """
        try:
            folder_marker_keys, missing_keys = find_s3_objects_without_local_file(s3_client, bucket_name, destination)
        except (ClientError, BotoCoreError) as e:
            self.error_out(f"could not list contents of {bucket_name} to explain the file count difference : {e}")
            return
        if folder_marker_keys:
            listed = ", ".join(folder_marker_keys[:max_keys_to_list]) + (" ..." if len(folder_marker_keys) > max_keys_to_list else "")
            log.info(
                f'{bucket_name} : {len(folder_marker_keys)} of the {count_difference} S3 objects without a local file are zero-byte folder markers, which "aws s3 sync" never downloads : {listed}'
            )
        for missing_key in missing_keys[:max_keys_to_list]:
            try:
                reasons = [str(mismatch) for mismatch in find_local_name_mismatches(destination, missing_key)]
            except OSError as e:
                reasons = [f"could not check for a similarly named local file : {e}"]
            if not reasons:
                reasons = ["no similarly named local file found (a key with characters Windows cannot store, or the file was removed after the sync)"]
            self.warning_out(f'{bucket_name} : S3 object "{missing_key}" has no local file at exactly that path : {"; ".join(reasons)}')
        if len(missing_keys) > max_keys_to_list:
            self.warning_out(f"{bucket_name} : {len(missing_keys) - max_keys_to_list} more S3 objects have no local file at exactly their path")

    def fix_local_name(self, bucket_name: str, destination: Path, key: str, dry_run: bool):
        """
        After "aws s3 sync" downloaded an object, make the local path exactly the key. Sync matches keys to local paths as exact strings,
        so a local copy whose name differs (e.g. only in case, on Windows) is downloaded again on every run; the download just made is
        the current version, so renaming it to the key's name is all that's needed for the next sync to find it already backed up.
        """
        try:
            if dry_run:
                for mismatch in find_local_name_mismatches(destination, key):
                    self.warning_out(f'{bucket_name} : "{key}" is downloaded on every run : {mismatch} (a backup run renames the local copy to match the S3 key)')
                return
            renames, failure = rename_local_to_match_key(destination, key)
        except OSError as e:
            self.warning_out(f'{bucket_name} : could not check the local name of "{key}" against its S3 key : {e}')
            return
        for rename in renames:
            self.info_out(f'{bucket_name} : {rename} to match the S3 key "{key}" so the next sync finds it already backed up')
        if failure is not None:
            self.warning_out(f'{bucket_name} : "{key}" will be downloaded on every run until the local name matches the S3 key exactly : {failure}')

    def run_backup(self):

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run
        size_only = preferences.s3_size_only

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

        # check the AWS CLI doing the backups: a likely compatibility problem is a warning in the backup output, anything else (e.g. a patch
        # release behind) only goes to the application log. Either way proceed - an outdated CLI can still back up.
        aws_cli_version_level, aws_cli_version_message = check_aws_cli_version(get_aws_cli_version(aws_cli_path, env_var), get_latest_awscli_version())
        {"warning": self.warning_out, "info": log.info}[aws_cli_version_level](aws_cli_version_message)

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
            if size_only:
                sync_command_line.append("--size-only")
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

            # a file that sync downloads on every run is one whose local name doesn't match its S3 key exactly - fix the local name
            for synced_key in get_synced_keys(sync_stdout, bucket_name, destination):
                self.fix_local_name(bucket_name, destination, synced_key, dry_run)

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
            if local_count < s3_object_count:
                self.explain_missing_local_files(s3_access.client, bucket_name, destination, s3_object_count - local_count)

        if dry_run:
            self.info_out(f"{len(buckets)} buckets, {dry_run_count} dry run, {total_synced_count} files would be synced, {len(exclusions_no_comments)} excluded")
        else:
            self.info_out(f"{len(buckets)} buckets, {count} backed up, {total_synced_count} files synced, {len(exclusions_no_comments)} excluded")
