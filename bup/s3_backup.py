import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from awsimple import S3Access, S3SyncObject, S3SyncOutcome, S3SyncResult, AWSimpleException, s3_key_to_local_path
from botocore.exceptions import BotoCoreError, ClientError
from balsa import get_logger

logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences
from bup.transfer import TransferRecord, get_transfer_out_cost
from bup.aws_prices import get_aws_prices
from bup.s3_verify import S3FileVerification, verify_local_file

log = get_logger(__application_name__)

max_keys_to_list = 20  # cap on the S3 keys named in the backup output for one bucket and one kind of outcome

verify_max_workers = 10  # local files verified against their S3 objects at a time (each takes a request to S3 and a read of the file)


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
    Total size (bytes) and object count of an S3 bucket, from a listing of the bucket with the boto3 client.
    :return: (total_size, object_count)
    """
    total_size = 0
    object_count = 0
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        for s3_object in page.get("Contents", []):  # an empty bucket (or page) has no "Contents"
            total_size += s3_object["Size"]
            object_count += 1
    return total_size, object_count


def is_folder_marker(sync_object: S3SyncObject) -> bool:
    """
    True for an object whose key ends in "/" (e.g. from the S3 console's "Create folder"). It is not a file, so a sync never downloads it,
    and it is expected to be in S3 but not in the local backup.
    """
    return sync_object.key.endswith("/")


def get_bucket_region(s3_client, bucket_name: str) -> Optional[str]:
    """
    The AWS region a bucket is in. Buckets can be in any region, whichever region the client itself is using, and the price of
    transferring data out of S3 depends on the bucket's region.
    :return: the region (e.g. "us-east-1"), or None if it could not be determined
    """
    try:
        response = s3_client.head_bucket(Bucket=bucket_name)
    except (ClientError, BotoCoreError) as e:
        log.warning(f"could not determine the region of {bucket_name} : {e}")
        return None
    bucket_region = response.get("BucketRegion") or response["ResponseMetadata"]["HTTPHeaders"].get("x-amz-bucket-region")
    return bucket_region if isinstance(bucket_region, str) else None


def compare_backup_sizes(s3_total_size: int, local_size: int) -> Tuple[str, str]:
    """
    Rough check that the sync worked, based on total sizes.
    :param s3_total_size: total size of the S3 objects that have to be in the local backup
    :param local_size: total size of the local backup of the bucket
    :return: (level, message) where level is "error" or "info"
    """
    if s3_total_size > local_size:
        # we're missing files
        return "error", "not all files backed up"
    elif s3_total_size < local_size:
        # expected over time - a sync never deletes local files, so files deleted from S3 are retained locally
        return "info", "local backup is larger than S3 (files deleted from S3 are retained locally)"
    else:
        return "info", "match"


def log_synced_object(bucket_name: str, sync_object: S3SyncObject):
    """
    Put an object that the sync downloaded (or would download, for a dry run) in the application log. Objects that are already
    up to date are not logged (that is nearly every object of nearly every run).
    """
    if sync_object.outcome in (S3SyncOutcome.downloaded, S3SyncOutcome.would_download):
        log.info(f"{bucket_name} : {sync_object.outcome} : {sync_object.key} ({sync_object.size} bytes)")


class S3Backup(BupBase):

    backup_type = BackupTypes.S3

    def sync_objects_out(self, out: Callable[[str], None], bucket_name: str, sync_objects: List[S3SyncObject], description: str):
        """
        Report S3 objects that have no current local file after a sync, each with the reason the sync gives.
        :param out: where to report (e.g. self.warning_out)
        :param sync_objects: the objects to report (only the first max_keys_to_list are named)
        :param description: what happened to these objects, e.g. "not backed up"
        """
        self.lines_out(
            out, [f'{bucket_name} : S3 object "{sync_object.key}" {description} : {sync_object.reason}' for sync_object in sync_objects], f"{bucket_name} : {{}} more S3 objects {description}"
        )

    def lines_out(self, out: Callable[[str], None], lines: List[str], more: str):
        """
        Report one line per S3 object, but only the first max_keys_to_list of them (a bucket can have any number of objects).
        :param out: where to report (e.g. self.warning_out)
        :param lines: a line per object
        :param more: reported with the number of lines that were left out in its {}, if any were
        """
        for line in lines[:max_keys_to_list]:
            out(line)
        if len(lines) > max_keys_to_list:
            out(more.format(len(lines) - max_keys_to_list))

    def verify_object(self, bucket_access: S3Access, destination: Path, sync_object: S3SyncObject) -> Optional[S3FileVerification]:
        """
        Verify the local file of one S3 object against the metadata of the object, which takes a request to S3. Called from several
        threads at a time, so it reports nothing itself.
        :return: the result, or None if a stop was requested before it started
        """
        if self.stop_requested:
            return None
        try:
            s3_object_metadata = bucket_access.get_s3_object_metadata(sync_object.key)
        except (ClientError, BotoCoreError, AWSimpleException) as e:
            return S3FileVerification(sync_object.key, [f"could not get the metadata of the S3 object ({e})"])
        return verify_local_file(s3_key_to_local_path(destination, sync_object.key), s3_object_metadata)

    def verify_bucket(self, bucket_name: str, bucket_access: S3Access, destination: Path, sync_result: S3SyncResult) -> Tuple[int, int]:
        """
        Verify every local file that the sync says is a current copy of its S3 object (downloaded or already up to date) against the
        metadata of the object: size, hash and modification time. A file that is not a copy is an error, a modification time that
        differs (of a file that is otherwise a copy) is a warning.
        :return: (number of files verified, number of them that are not a copy of their S3 object)
        """
        sync_objects = sync_result.get_objects(S3SyncOutcome.downloaded) + sync_result.get_objects(S3SyncOutcome.up_to_date)
        log.info(f'{bucket_name} : verifying {len(sync_objects)} files in "{destination}" against S3')
        with ThreadPoolExecutor(verify_max_workers) as executor:
            verifications = [verification for verification in executor.map(partial(self.verify_object, bucket_access, destination), sync_objects) if verification is not None]

        differ = [verification for verification in verifications if verification.problems]
        self.lines_out(
            self.error_out,
            [f'{bucket_name} : "{verification.key}" is not a copy of the S3 object : {"; ".join(verification.problems)}' for verification in differ],
            f"{bucket_name} : {{}} more local files are not a copy of their S3 object",
        )
        mtime_differs = [verification for verification in verifications if not verification.problems and verification.mtime_difference is not None]
        self.lines_out(
            self.warning_out,
            [f'{bucket_name} : "{verification.key}" has the contents of the S3 object, but {verification.mtime_difference}' for verification in mtime_differs],
            f"{bucket_name} : {{}} more local files have a modification time that is not their S3 object's",
        )
        no_hash_count = sum(not verification.s3_has_hash for verification in verifications)
        self.info_out(
            f"{bucket_name} : verified {len(verifications)} of {len(sync_objects)} files against S3 : {len(differ)} differ, {len(mtime_differs)} have a different modification time, "
            f"{no_hash_count} have no hash in S3 (size and modification time only)"
        )
        return len(verifications), len(differ)

    def verify_backup(self, to_verify: List[Tuple[str, S3Access, Path, S3SyncResult]]):
        """
        Verify the local files of the buckets that were synced against S3 (see verify_bucket()).
        :param to_verify: (bucket name, access to the bucket, local directory of the bucket, result of its sync) per bucket
        """
        self.info_out(f"verifying {len(to_verify)} buckets against S3 (this makes a request to S3 for every object, and reads every local file)")
        bucket_count = 0
        total_verified_count = 0
        total_differ_count = 0
        for bucket_name, bucket_access, destination, sync_result in to_verify:
            if self.stop_requested:
                break
            verified_count, differ_count = self.verify_bucket(bucket_name, bucket_access, destination, sync_result)
            bucket_count += 1
            total_verified_count += verified_count
            total_differ_count += differ_count
        stopped = " (stopped before all files were verified)" if self.stop_requested else ""
        self.info_out(f"verified {total_verified_count} files in {bucket_count} buckets against S3, {total_differ_count} differ{stopped}")

    def run_backup(self):

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run
        size_only = preferences.s3_size_only

        backup_directory = os.path.join(preferences.backup_directory, "s3")

        os.makedirs(backup_directory, exist_ok=True)

        credentials = {
            "profile_name": preferences.aws_profile or None,
            "aws_access_key_id": preferences.aws_access_key_id or None,
            "aws_secret_access_key": preferences.aws_secret_access_key or None,
        }
        s3_access = S3Access(region_name=preferences.aws_region or None, **credentials)

        try:
            buckets = s3_access.bucket_list()
        except (ClientError, BotoCoreError) as e:
            self.error_out(f"could not list S3 buckets - check credentials and connectivity : {e}")
            return
        self.info_out(f"found {len(buckets)} buckets")

        count = 0
        dry_run_count = 0
        total_synced_count = 0
        to_verify = []  # the buckets to verify against S3 once every bucket is backed up
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

            # A bucket is accessed in its own region, whichever region the preferences give. The sync never deletes local files: we want
            # to keep 'old' files locally.
            bucket_region = get_bucket_region(s3_access.client, bucket_name)
            log.info(f'{bucket_name} : sync to "{destination}" ({bucket_region=}, {size_only=}, {dry_run=})')
            try:
                bucket_access = S3Access(bucket_name, region_name=bucket_region or preferences.aws_region or None, **credentials)
                sync_result = bucket_access.sync_to_directory(destination, size_only=size_only, dry_run=dry_run, stop_event=self.stop_event, callback=partial(log_synced_object, bucket_name))
            except (ClientError, BotoCoreError, AWSimpleException, OSError) as e:
                self.error_out(f"could not sync {bucket_name} : {e}")
                continue  # don't count or verify a failed sync

            synced_count = sync_result.get_count(S3SyncOutcome.would_download if dry_run else S3SyncOutcome.downloaded)
            total_synced_count += synced_count

            # Objects without a current local file: folder markers are expected (application log only), any other object the sync skips
            # is not backed up (a warning, with the reason), and an object that could not be downloaded is an error.
            skipped = sync_result.get_objects(S3SyncOutcome.skipped)
            folder_marker_keys = [sync_object.key for sync_object in skipped if is_folder_marker(sync_object)]
            if folder_marker_keys:
                listed = ", ".join(folder_marker_keys[:max_keys_to_list]) + (" ..." if len(folder_marker_keys) > max_keys_to_list else "")
                log.info(f"{bucket_name} : {len(folder_marker_keys)} S3 objects are folder markers, which are not files and are not downloaded : {listed}")
            not_backed_up = [sync_object for sync_object in skipped if not is_folder_marker(sync_object)]
            self.sync_objects_out(self.warning_out, bucket_name, not_backed_up, "not backed up")
            failed = sync_result.get_objects(S3SyncOutcome.failed)
            self.sync_objects_out(self.error_out, bucket_name, failed, "could not be backed up")

            # check the results (skip during dry run - nothing was synced)
            if dry_run:
                dry_run_count += 1
                self.info_out(f"{bucket_name} : {synced_count} files would be synced")
                continue

            # what the sync received from S3, and approximately what AWS charges for sending it (at the prices of the bucket's region)
            if (synced_size := sync_result.get_size(S3SyncOutcome.downloaded)) > 0:
                self.transfer_out(TransferRecord(BackupTypes.S3, bucket_name, synced_size, cost=get_transfer_out_cost(synced_size, get_aws_prices(bucket_region)), region=bucket_region))

            if self.stop_requested:
                break  # the downloads that had not started were not attempted, so there is nothing to verify

            if preferences.s3_verify:
                to_verify.append((bucket_name, bucket_access, destination, sync_result))

            # Verify the sync with a listing of the bucket of our own (not the sync's): everything in the bucket, other than the objects the
            # sync reported as not downloaded (which have been reported above), has to be in the local backup.
            try:
                s3_total_size, s3_object_count = get_bucket_size(bucket_access.client, bucket_name)
            except (ClientError, BotoCoreError) as e:
                self.error_out(f"could not list contents of {bucket_name} to verify the sync : {e}")
                continue

            if not failed:
                count += 1
            backed_up_size = s3_total_size - sync_result.get_size(S3SyncOutcome.skipped) - sync_result.get_size(S3SyncOutcome.failed)
            local_size, local_count = get_dir_size(destination)
            level, message = compare_backup_sizes(backed_up_size, local_size)
            output_routines = {"error": self.error_out, "info": log.info}
            output_routines[level](
                f"{bucket_name} : {message} (synced={synced_count}, not_backed_up={len(not_backed_up)}, failed={len(failed)}, s3_count={s3_object_count}, local_count={local_count}; "
                f"s3_total_size={s3_total_size}, backed_up_size={backed_up_size}, local_size={local_size})"
            )

        if dry_run:
            self.info_out(f"{len(buckets)} buckets, {dry_run_count} dry run, {total_synced_count} files would be synced, {len(exclusions_no_comments)} excluded")
        else:
            self.info_out(f"{len(buckets)} buckets, {count} backed up, {total_synced_count} files synced, {len(exclusions_no_comments)} excluded")
            if preferences.s3_verify and not self.stop_requested:
                self.verify_backup(to_verify)
            self.transfer_summary_out()
