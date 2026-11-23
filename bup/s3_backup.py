"""
The S3 backup: every bucket is synced to a local directory with awsimple's S3Access.sync_to_directory() (which never deletes a local
file), the sync is checked against a listing of the bucket, and optionally every local file is then verified against the metadata
of its S3 object (with awsimple's S3Access.verify_directory()). See README "S3 backup".
"""

import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from awsimple import S3Access, S3SyncObject, S3SyncOutcome, S3SyncResult, S3VerifyOutcome, AWSimpleException
from botocore.exceptions import BotoCoreError, ClientError
from balsa import get_logger

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences
from bup.aws_access import get_aws_access_kwargs
from bup.transfer import TransferRecord, get_transfer_out_cost
from bup.aws_prices import get_aws_prices

log = get_logger(__application_name__)

max_keys_to_list = 20  # cap on the S3 keys named in the backup output for one bucket and one kind of outcome


# sundry candidate
def get_dir_size(dir_path: Path) -> Tuple[int, int]:
    """
    Total size (bytes) and number of the files under a directory, at any depth. A file whose size can not be had is left out
    (with a warning in the log).
    :return: (total size, file count)
    """
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


@dataclass
class SyncedBucket:
    """
    A bucket whose sync ran, with what reporting on it and verifying it need.
    """

    name: str
    access: S3Access  # access to the bucket, in the bucket's region
    region: Optional[str]  # the region the bucket is in (None if it could not be determined)
    destination: Path  # the local directory of the bucket
    sync_result: S3SyncResult  # the outcome of every object of the bucket

    def get_not_backed_up(self) -> List[S3SyncObject]:
        """
        :return: the objects the sync skipped on purpose that are files (so not the folder markers), which are not backed up
        """
        return [sync_object for sync_object in self.sync_result.get_objects(S3SyncOutcome.skipped) if not is_folder_marker(sync_object)]

    def get_folder_marker_keys(self) -> List[str]:
        """
        :return: the keys of the folder markers, which are not files and are expected to not be in the local backup
        """
        return [sync_object.key for sync_object in self.sync_result.get_objects(S3SyncOutcome.skipped) if is_folder_marker(sync_object)]

    def get_failed(self) -> List[S3SyncObject]:
        """
        :return: the objects that could not be downloaded
        """
        return self.sync_result.get_objects(S3SyncOutcome.failed)

    def get_backed_up(self) -> List[S3SyncObject]:
        """
        :return: the objects the sync says have a current local file: downloaded in this run, or already up to date
        """
        return self.sync_result.get_objects(S3SyncOutcome.downloaded) + self.sync_result.get_objects(S3SyncOutcome.up_to_date)


class S3Backup(BupBase):
    """
    Backs up every S3 bucket the credentials can list (other than the excluded ones) to <backup directory>/s3/<bucket>.
    """

    backup_type = BackupTypes.S3

    # ----------------------------------------------------------------------------------------------------------------------------
    # output
    # ----------------------------------------------------------------------------------------------------------------------------

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

    # ----------------------------------------------------------------------------------------------------------------------------
    # the sync of a bucket
    # ----------------------------------------------------------------------------------------------------------------------------

    def sync_bucket(self, preferences, s3_access: S3Access, bucket_name: str, destination: Path) -> Optional[SyncedBucket]:
        """
        Sync one bucket to its local directory (or, for a dry run, find out what a sync would download). A bucket is accessed in its
        own region, whichever region the preferences give. The sync never deletes local files: files deleted from S3 are kept.

        :param preferences: the preferences
        :param s3_access: an access to S3 (to no bucket in particular), to find the bucket's region with
        :param bucket_name: the bucket
        :param destination: the local directory of the bucket
        :return: the synced bucket, or None if the sync could not be done at all (which is reported as an error)
        """
        bucket_region = get_bucket_region(s3_access.client, bucket_name)
        # The preferences database gives a bool preference as an int (and None if it was never set), and awsimple checks the types of its arguments.
        size_only = bool(preferences.s3_size_only)
        dry_run = bool(preferences.dry_run)
        log.info(f'{bucket_name} : sync to "{destination}" ({bucket_region=}, {size_only=}, {dry_run=})')
        try:
            bucket_access = S3Access(bucket_name, **get_aws_access_kwargs(preferences, bucket_region))
            sync_result = bucket_access.sync_to_directory(destination, size_only=size_only, dry_run=dry_run, stop_event=self.stop_event, callback=partial(log_synced_object, bucket_name))
        except (ClientError, BotoCoreError, AWSimpleException, OSError) as e:
            self.error_out(f"could not sync {bucket_name} : {e}")
            return None
        return SyncedBucket(bucket_name, bucket_access, bucket_region, destination, sync_result)

    def sync_exceptions_out(self, bucket: SyncedBucket):
        """
        Report the objects of a bucket that have no current local file after its sync: folder markers are expected (application log
        only), any other object the sync skips is not backed up (a warning, with the reason), and an object that could not be
        downloaded is an error.
        """
        if folder_marker_keys := bucket.get_folder_marker_keys():
            listed = ", ".join(folder_marker_keys[:max_keys_to_list]) + (" ..." if len(folder_marker_keys) > max_keys_to_list else "")
            log.info(f"{bucket.name} : {len(folder_marker_keys)} S3 objects are folder markers, which are not files and are not downloaded : {listed}")
        self.sync_objects_out(self.warning_out, bucket.name, bucket.get_not_backed_up(), "not backed up")
        self.sync_objects_out(self.error_out, bucket.name, bucket.get_failed(), "could not be backed up")

    def sync_transfer_out(self, bucket: SyncedBucket):
        """
        Report what the sync of a bucket received from S3, and approximately what AWS charges for sending it (at the prices of the
        bucket's region). Nothing is reported for a sync that downloaded nothing.
        """
        if (synced_size := bucket.sync_result.get_size(S3SyncOutcome.downloaded)) > 0:
            cost = get_transfer_out_cost(synced_size, get_aws_prices(bucket.region))
            self.transfer_out(TransferRecord(BackupTypes.S3, bucket.name, synced_size, cost=cost, region=bucket.region))

    def check_bucket_size(self, bucket: SyncedBucket) -> bool:
        """
        Check the sync of a bucket with a listing of the bucket of our own (not the sync's): everything in the bucket, other than the
        objects the sync reported as not downloaded (which sync_exceptions_out() reports), has to be in the local backup. This is a
        comparison of total sizes. S3 being larger is an error, and the other outcomes only go to the application log.

        :return: True if the bucket was checked, False if it could not be listed (which is reported as an error)
        """
        try:
            s3_total_size, s3_object_count = get_bucket_size(bucket.access.client, bucket.name)
        except (ClientError, BotoCoreError) as e:
            self.error_out(f"could not list contents of {bucket.name} to verify the sync : {e}")
            return False

        sync_result = bucket.sync_result
        backed_up_size = s3_total_size - sync_result.get_size(S3SyncOutcome.skipped) - sync_result.get_size(S3SyncOutcome.failed)
        local_size, local_count = get_dir_size(bucket.destination)
        level, message = compare_backup_sizes(backed_up_size, local_size)
        output_routines = {"error": self.error_out, "info": log.info}
        output_routines[level](
            f"{bucket.name} : {message} (synced={sync_result.get_count(S3SyncOutcome.downloaded)}, not_backed_up={len(bucket.get_not_backed_up())}, failed={len(bucket.get_failed())}, "
            f"s3_count={s3_object_count}, local_count={local_count}; s3_total_size={s3_total_size}, backed_up_size={backed_up_size}, local_size={local_size})"
        )
        return True

    # ----------------------------------------------------------------------------------------------------------------------------
    # the optional verification of every local file against S3
    # ----------------------------------------------------------------------------------------------------------------------------

    def verify_bucket(self, bucket: SyncedBucket) -> Tuple[int, int, int]:
        """
        Verify every local file that the sync says is a current copy of its S3 object (downloaded or already up to date) against the
        metadata of the object, with awsimple's S3Access.verify_directory(): size, hash and modification time. A file that is not a
        copy, or that could not be verified, is an error. A modification time that differs (of a file that has the contents of its
        S3 object) is a warning.
        :return: (number of files that were verified, number of them that are not a copy of their S3 object, number that could not be verified)
        """
        log.info(f'{bucket.name} : verifying the files in "{bucket.destination}" against S3')
        verify_result = bucket.access.verify_directory(bucket.destination, sync_result=bucket.sync_result, stop_event=self.stop_event)

        differ = verify_result.get_objects(S3VerifyOutcome.differs)
        self.lines_out(
            self.error_out,
            [f'{bucket.name} : "{verify_object.key}" is not a copy of the S3 object : {verify_object.reason}' for verify_object in differ],
            f"{bucket.name} : {{}} more local files are not a copy of their S3 object",
        )
        failed = verify_result.get_objects(S3VerifyOutcome.failed)
        self.lines_out(
            self.error_out,
            [f'{bucket.name} : "{verify_object.key}" could not be verified : {verify_object.reason}' for verify_object in failed],
            f"{bucket.name} : {{}} more local files could not be verified",
        )
        mtime_differs = verify_result.get_objects(S3VerifyOutcome.mtime_differs)
        self.lines_out(
            self.warning_out,
            [f'{bucket.name} : "{verify_object.key}" has the contents of the S3 object, but {verify_object.reason}' for verify_object in mtime_differs],
            f"{bucket.name} : {{}} more local files have a modification time that is not their S3 object's",
        )
        same_contents = verify_result.get_objects(S3VerifyOutcome.verified) + mtime_differs
        no_hash_count = sum(verify_object.hash_name is None for verify_object in same_contents)  # S3 has no hash of the whole contents of these
        verified_count = len(same_contents) + len(differ) + len(failed)
        could_not = f", {len(failed)} could not be verified" if failed else ""
        self.info_out(
            f"{bucket.name} : verified {verified_count} of {verified_count + verify_result.get_count(S3VerifyOutcome.not_attempted)} files against S3 : {len(differ)} differ, "
            f"{len(mtime_differs)} have a different modification time, {no_hash_count} have no hash in S3 (size and modification time only){could_not}"
        )
        return verified_count, len(differ), len(failed)

    def verify_backup(self, buckets: List[SyncedBucket]):
        """
        Verify the local files of the buckets that were synced against S3 (see verify_bucket()).
        """
        self.info_out(f"verifying {len(buckets)} buckets against S3 (this makes a request to S3 for every object, and reads every local file)")
        bucket_count = 0
        total_verified_count = 0
        total_differ_count = 0
        total_failed_count = 0
        for bucket in buckets:
            if self.stop_requested:
                break
            verified_count, differ_count, failed_count = self.verify_bucket(bucket)
            bucket_count += 1
            total_verified_count += verified_count
            total_differ_count += differ_count
            total_failed_count += failed_count
        could_not = f", {total_failed_count} could not be verified" if total_failed_count > 0 else ""
        stopped = " (stopped before all files were verified)" if self.stop_requested else ""
        self.info_out(f"verified {total_verified_count} files in {bucket_count} buckets against S3, {total_differ_count} differ{could_not}{stopped}")

    # ----------------------------------------------------------------------------------------------------------------------------
    # the backup
    # ----------------------------------------------------------------------------------------------------------------------------

    def run_backup(self):
        """
        Back up every bucket: sync it, report what the sync did, and check it. A failure of one bucket does not end the backup of the
        others. With the s3_verify preference, every local file is then verified against S3.
        """
        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run

        backup_directory = os.path.join(preferences.backup_directory, "s3")
        os.makedirs(backup_directory, exist_ok=True)

        try:
            s3_access = S3Access(**get_aws_access_kwargs(preferences))  # making the access raises if the AWS profile does not exist
            bucket_names = s3_access.bucket_list()
        except (ClientError, BotoCoreError) as e:
            # BotoCoreError covers e.g. ProfileNotFound, NoCredentialsError and EndpointConnectionError
            self.error_out(f"could not list S3 buckets - check credentials and connectivity : {e}")
            return
        self.info_out(f"found {len(bucket_names)} buckets")

        count = 0  # buckets backed up, or dry run
        total_synced_count = 0  # objects downloaded (or that a sync would download, for a dry run)
        synced_buckets = []  # the buckets to verify against S3 once every bucket is backed up
        exclusions = ExclusionPreferences(BackupTypes.S3.name).get_no_comments()
        for bucket_name in bucket_names:
            if self.stop_requested:
                break

            if bucket_name in exclusions:
                self.info_out(f"excluding {bucket_name}")
                continue

            self.info_out(f"dry run {bucket_name}" if dry_run else f"{bucket_name}")

            destination = Path(backup_directory, bucket_name)
            os.makedirs(destination, exist_ok=True)
            if (bucket := self.sync_bucket(preferences, s3_access, bucket_name, destination)) is None:
                continue  # don't count or check a sync that could not be done

            synced_count = bucket.sync_result.get_count(S3SyncOutcome.would_download if dry_run else S3SyncOutcome.downloaded)
            total_synced_count += synced_count
            self.sync_exceptions_out(bucket)

            # nothing was synced in a dry run, so there is nothing to check
            if dry_run:
                count += 1
                self.info_out(f"{bucket_name} : {synced_count} files would be synced")
                continue

            self.sync_transfer_out(bucket)

            if self.stop_requested:
                break  # the downloads that had not started were not attempted, so there is nothing to check

            synced_buckets.append(bucket)
            if self.check_bucket_size(bucket) and not bucket.get_failed():
                count += 1

        if dry_run:
            self.info_out(f"{len(bucket_names)} buckets, {count} dry run, {total_synced_count} files would be synced, {len(exclusions)} excluded")
        else:
            self.info_out(f"{len(bucket_names)} buckets, {count} backed up, {total_synced_count} files synced, {len(exclusions)} excluded")
            if preferences.s3_verify and not self.stop_requested:
                self.verify_backup(synced_buckets)
            self.transfer_summary_out()
