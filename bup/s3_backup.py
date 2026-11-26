"""
The S3 backup: every bucket is synced to a local directory with awsimple's S3Access.sync_to_directory() (which never deletes a local
file), the sync is checked against a listing of the bucket, and optionally every local file is then verified against the metadata
of its S3 object (with awsimple's S3Access.verify_directory()), and a local file that has the contents of its S3 object but another
modification time can then be given the time of the S3 object (see s3_mtime_fix.py). See README "S3 backup".

The parts: the helpers of a sync and its check (below), SyncedBucket, and S3Backup, whose methods are grouped as output, the sync
of a bucket, the verification and the backup itself. The watch of a verification is in s3_verify.py.
"""

import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from awsimple import S3Access, S3SyncObject, S3SyncOutcome, S3SyncResult, S3VerifyObject, S3VerifyOutcome, S3VerifyResult, AWSimpleException
from botocore.exceptions import BotoCoreError, ClientError
from balsa import get_logger

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences
from bup.aws_access import get_aws_access_kwargs
from bup.backup_types import get_backup_type_directory
from bup.s3_mtime_fix import MtimeFix, MtimeFixOutcome, fix_local_mtime, remove_temp_dir, temp_dir_name
from bup.s3_verify import BucketVerification, VerifyWatch, get_s3_unreachable_reason, verify_failures_before_reachability_check  # the last for those who import it from here
from bup.transfer import TransferRecord, get_charged_request_count, get_s3_cost
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

    def files_out(self, out: Callable[[str], None], bucket_name: str, files: Sequence[Union[S3VerifyObject, MtimeFix]], description: str, more: str):
        """
        Report what the verification (or the fix of modification times) found for local files, a line per file with its reason.
        :param out: where to report (e.g. self.error_out)
        :param files: the outcome of each file to report, which has the key and the reason (only the first max_keys_to_list are named)
        :param description: what was found for these files, which the reason of a file follows, e.g. "could not be verified : "
        :param more: what the files that are not named are counted as, e.g. "local files could not be verified"
        """
        self.lines_out(out, [f'{bucket_name} : "{file.key}" {description}{file.reason}' for file in files], f"{bucket_name} : {{}} more {more}")

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

    def usage_out(self, bucket: SyncedBucket, name: str, received_bytes: int = 0):
        """
        Report what was received from S3 for a bucket and the S3 requests that were made for it since this was last called for the
        bucket (awsimple counts every request of the bucket's access), with approximately what AWS charges at the prices of the
        bucket's region: for the data transfer, for the requests, and the retrieval fee of the bytes S3 sent of the storage classes
        that have one. Nothing is reported if nothing was received and no request was made.

        :param bucket: the bucket
        :param name: what the transfer is reported as, e.g. the name of the bucket
        :param received_bytes: the size of what was downloaded
        """
        usage = bucket.access.usage
        tier_counts = usage.get_tier_counts()
        download_sizes = usage.get_download_sizes()  # by storage class: also what a download that failed part way was sent
        usage.reset()  # what is reported next (e.g. the verification) starts from here
        request_count = get_charged_request_count(tier_counts)
        if received_bytes > 0 or request_count > 0:
            cost = get_s3_cost(received_bytes, tier_counts, download_sizes, get_aws_prices(bucket.region))
            self.transfer_out(TransferRecord(BackupTypes.S3, name, received_bytes, cost=cost, region=bucket.region, requests=request_count))

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
        self.counts.files = (self.counts.files or 0) + local_count
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

    def remove_mtime_fix_temp_dir(self, temp_dir: Path):
        """
        Remove the directory of the downloads of the fix of modification times, with anything a run that was cut short left in it.
        A directory that can not be removed is an error: it can hold a download, which is not part of the backup.
        """
        try:
            remove_temp_dir(temp_dir)
        except OSError as e:
            self.error_out(f'could not remove the temporary directory "{temp_dir}" of the downloads that fix modification times : {e}')

    def fix_mtimes(self, bucket: SyncedBucket, mtime_differs: List[S3VerifyObject], temp_dir: Path) -> Tuple[Dict[str, MtimeFix], Optional[str]]:
        """
        Give the local files that the verification found to have another modification time than their S3 object the time of the S3
        object, one file after the other, each only once its contents are known to be the S3 object's (see fix_local_mtime(), which
        downloads an object S3 has no hash of to compare it). Every time that is changed is in the application log. This ends when
        the backup is stopped, and when S3 can no longer be reached (which is one error).

        A download is deleted as soon as it has been compared. The directory of the downloads is also removed before the first file
        (a run that was cut short can have left a download in it) and after the last one, however this ends.

        :param bucket: the bucket
        :param mtime_differs: the objects of the verification whose local file has another modification time
        :param temp_dir: the directory of the downloads, on the backup drive
        :return: (the outcome of every file this got to, by S3 key, and why S3 could not be reached - None if it could be)
        """
        if len(mtime_differs) == 0:
            return {}, None
        self.remove_mtime_fix_temp_dir(temp_dir)
        try:
            return self._fix_mtimes(bucket, mtime_differs, temp_dir)
        finally:
            self.remove_mtime_fix_temp_dir(temp_dir)

    def _fix_mtimes(self, bucket: SyncedBucket, mtime_differs: List[S3VerifyObject], temp_dir: Path) -> Tuple[Dict[str, MtimeFix], Optional[str]]:
        """
        fix_mtimes(), other than the removal of the directory of the downloads.
        """
        fixes: Dict[str, MtimeFix] = {}
        for verify_object in mtime_differs:
            if self.stop_requested:
                break
            assert verify_object.local_path is not None  # a file that was verified
            fix = fix_local_mtime(bucket.access, verify_object.key, verify_object.local_path, temp_dir)
            if fix.outcome == MtimeFixOutcome.failed and (unreachable_reason := get_s3_unreachable_reason(bucket.access.client, bucket.name)) is not None:
                self.error_out(f"{bucket.name} : S3 could not be reached while fixing modification times, which ended there : {unreachable_reason}")
                return fixes, unreachable_reason
            fixes[verify_object.key] = fix
            if fix.outcome == MtimeFixOutcome.fixed:
                how = "the S3 object was downloaded to compare" if fix.downloaded else "the hash is the S3 object's"
                log.info(f'{bucket.name} : "{verify_object.key}" : modification time changed from {fix.old_mtime} to {fix.new_mtime}, that of the S3 object ({how})')
        return fixes, None

    def verify_bucket(self, bucket: SyncedBucket, mtime_fix_temp_dir: Optional[Path] = None) -> BucketVerification:
        """
        Verify every local file that the sync says is a current copy of its S3 object (downloaded or already up to date) against the
        metadata of the object, with awsimple's S3Access.verify_directory(): size, hash and modification time. If S3 can no longer
        be reached, the verification ends there (see VerifyWatch). What was found is reported by verification_out().

        With mtime_fix_temp_dir, the files whose modification time differs are then given the time of their S3 object (see
        fix_mtimes()).

        :param bucket: the bucket
        :param mtime_fix_temp_dir: the directory of the downloads of the fix, to fix the modification times that differ (None to not fix them)
        :return: what the verification found
        """
        log.info(f'{bucket.name} : verifying the files in "{bucket.destination}" against S3')
        watch = VerifyWatch(bucket.access.client, bucket.name, self.stop_event)
        try:
            verify_result = bucket.access.verify_directory(bucket.destination, sync_result=bucket.sync_result, stop_event=watch.stop_event, callback=watch.object_out)
        except (ClientError, BotoCoreError, AWSimpleException, OSError) as e:
            # awsimple puts what fails for one object in its result, so this is something else (e.g. credentials that are no longer there)
            self.error_out(f"{bucket.name} : could not verify the files against S3 : {e}")
            return BucketVerification()
        watch.check_last_failures()

        mtime_fixes: Optional[Dict[str, MtimeFix]] = None  # None: the modification times are not fixed
        fix_unreachable_reason = None
        if mtime_fix_temp_dir is not None:
            mtime_fixes = {}
            if watch.unreachable_reason is None:
                mtime_fixes, fix_unreachable_reason = self.fix_mtimes(bucket, verify_result.get_objects(S3VerifyOutcome.mtime_differs), mtime_fix_temp_dir)
        bucket_verification = self.verification_out(bucket.name, verify_result, watch, mtime_fixes)
        bucket_verification.unreachable = bucket_verification.unreachable or fix_unreachable_reason is not None
        return bucket_verification

    def verification_out(self, bucket_name: str, verify_result: S3VerifyResult, watch: VerifyWatch, mtime_fixes: Optional[Dict[str, MtimeFix]]) -> BucketVerification:
        """
        Report what the verification of a bucket found, and what the fix of its modification times did:

        - a file that is not a copy of its S3 object is an error, whether the verification or the fix found that,
        - a file that could not be verified is an error, and so is one whose modification time could not be fixed,
        - a file that has the contents of its S3 object but another modification time is a warning, unless the fix got to it (it is
          then fixed, or one of the errors above),
        - the files that were not verified because S3 could no longer be reached are one error,
        - and a result line, with a second one for the fix if there were modification times to fix.

        :param bucket_name: the bucket
        :param verify_result: the result of awsimple's verification
        :param watch: the watch of that verification
        :param mtime_fixes: the outcome of every file the fix of modification times got to, by S3 key (None if they are not fixed)
        :return: what the verification found
        """
        fixes = list((mtime_fixes or {}).values())
        fix_differ = [fix for fix in fixes if fix.outcome == MtimeFixOutcome.differs]  # found not to be a copy by the fix
        fix_failed = [fix for fix in fixes if fix.outcome == MtimeFixOutcome.failed]
        fixed = [fix for fix in fixes if fix.outcome == MtimeFixOutcome.fixed]
        differ = verify_result.get_objects(S3VerifyOutcome.differs)
        # the files that failed because S3 could not be reached are one error (below), and the others are an error each
        failed = [verify_object for verify_object in verify_result.get_objects(S3VerifyOutcome.failed) if verify_object.key not in watch.unreachable_keys]
        mtime_differs = verify_result.get_objects(S3VerifyOutcome.mtime_differs)
        mtime_not_fixed = [verify_object for verify_object in mtime_differs if verify_object.key not in (mtime_fixes or {})]  # the fix did not get to these

        self.files_out(self.error_out, bucket_name, [*differ, *fix_differ], "is not a copy of the S3 object : ", "local files are not a copy of their S3 object")
        self.files_out(self.error_out, bucket_name, failed, "could not be verified : ", "local files could not be verified")
        self.files_out(self.error_out, bucket_name, fix_failed, ": the modification time could not be fixed : ", "modification times could not be fixed")
        self.files_out(self.warning_out, bucket_name, mtime_not_fixed, "has the contents of the S3 object, but ", "local files have a modification time that is not their S3 object's")

        same_contents = verify_result.get_objects(S3VerifyOutcome.verified) + mtime_differs
        no_hash_count = sum(verify_object.hash_name is None for verify_object in same_contents)  # S3 has no hash of the whole contents of these
        verified_count = len(same_contents) + len(differ) + len(failed)
        not_verified_count = len(watch.unreachable_keys) + verify_result.get_count(S3VerifyOutcome.not_attempted)  # S3 could not be reached, or the verification was stopped
        if watch.unreachable_reason is not None:
            self.error_out(
                f"{bucket_name} : S3 could not be reached during the verification, which ended there : {not_verified_count} of {verified_count + not_verified_count} files were not verified : "
                f"{watch.unreachable_reason}"
            )
        could_not = f", {len(failed)} could not be verified" if failed else ""
        differ_count = len(differ) + len(fix_differ)
        self.info_out(
            f"{bucket_name} : verified {verified_count} of {verified_count + not_verified_count} files against S3 : {differ_count} differ, "
            f"{len(mtime_differs) - len(fix_differ)} have a different modification time, {no_hash_count} have no hash in S3 (size and modification time only){could_not}"
        )
        if mtime_fixes is not None and len(mtime_differs) > 0:
            downloaded_count = sum(fix.downloaded for fix in fixed)
            self.info_out(
                f"{bucket_name} : fixed the modification time of {len(fixed)} of {len(mtime_differs)} files that have a different modification time "
                f"({downloaded_count} after a download to compare, since S3 has no hash of them)"
            )
        return BucketVerification(verified_count, differ_count, len(failed), watch.unreachable_reason is not None)

    def verify_backup(self, buckets: List[SyncedBucket]):
        """
        Verify the local files of the buckets that were synced against S3 (see verify_bucket()). The verification ends with the
        bucket during which S3 can no longer be reached (e.g. the internet connection drops): the buckets after it would only fail.
        With the s3_fix_mtime preference, a local file that has the contents of its S3 object but another modification time is
        given the time of the S3 object. What that downloads (the objects S3 has no hash of) goes to a temporary directory in the
        backup directory, which has the room for it.
        """
        preferences = get_preferences(self.ui_type)
        fix_mtime = bool(preferences.s3_fix_mtime)  # the preferences database gives a bool preference as an int (and None if it was never set)
        mtime_fix_temp_dir = Path(preferences.backup_directory, temp_dir_name) if fix_mtime else None
        self.info_out(f"verifying {len(buckets)} buckets against S3 (this makes a request to S3 for every object, and reads every local file)")
        bucket_count = 0
        total_verified_count = 0
        total_differ_count = 0
        total_failed_count = 0
        unreachable = False
        for bucket in buckets:
            if self.stop_requested or unreachable:
                break
            bucket_verification = self.verify_bucket(bucket, mtime_fix_temp_dir)
            # a request for every object, which AWS charges for. Only the fix of modification times receives objects (those S3 has no hash of).
            received_bytes = sum(bucket.access.usage.get_download_sizes().values()) if fix_mtime else 0
            self.usage_out(bucket, f"{bucket.name} (verification)", received_bytes)
            bucket_count += 1
            total_verified_count += bucket_verification.verified_count
            total_differ_count += bucket_verification.differ_count
            total_failed_count += bucket_verification.failed_count
            unreachable = bucket_verification.unreachable
        could_not = f", {total_failed_count} could not be verified" if total_failed_count > 0 else ""
        stopped = " (stopped before all files were verified)" if self.stop_requested else ""
        ended = f" (S3 could not be reached, so the verification ended : {len(buckets) - bucket_count} more buckets were not verified)" if unreachable else ""
        self.info_out(f"verified {total_verified_count} files in {bucket_count} buckets against S3, {total_differ_count} differ{could_not}{stopped}{ended}")

    # ----------------------------------------------------------------------------------------------------------------------------
    # the backup
    # ----------------------------------------------------------------------------------------------------------------------------

    def run_backup(self):
        """
        Back up every bucket: sync it, report what the sync did, and check it. A failure of one bucket does not end the backup of the
        others. With the s3_verify preference, every local file is then verified against S3, and with the s3_fix_mtime preference
        as well, the modification times that the verification finds to differ are fixed.
        """
        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run

        backup_directory = get_backup_type_directory(preferences.backup_directory, self.backup_type)
        backup_directory.mkdir(parents=True, exist_ok=True)

        try:
            s3_access = S3Access(**get_aws_access_kwargs(preferences))  # making the access raises if the AWS profile does not exist
            bucket_names = s3_access.bucket_list()
        except (ClientError, BotoCoreError) as e:
            # BotoCoreError covers e.g. ProfileNotFound, NoCredentialsError and EndpointConnectionError
            self.error_out(f"could not list S3 buckets - check credentials and connectivity : {e}")
            return
        self.info_out(f"found {len(bucket_names)} buckets")
        self.start_counts(len(bucket_names), dry_run)
        if not dry_run:  # a dry run syncs nothing
            self.counts.files_synced = 0

        count = 0  # buckets backed up, or dry run
        total_synced_count = 0  # objects downloaded (or that a sync would download, for a dry run)
        synced_buckets = []  # the buckets to verify against S3 once every bucket is backed up
        exclusions = ExclusionPreferences(self.backup_type.name).get_no_comments()
        for bucket_name in bucket_names:
            if self.stop_requested:
                break

            if bucket_name in exclusions:
                self.info_out(f"excluding {bucket_name}")
                self.count_excluded()
                continue

            self.info_out(f"dry run {bucket_name}" if dry_run else f"{bucket_name}")

            destination = Path(backup_directory, bucket_name)
            destination.mkdir(parents=True, exist_ok=True)
            if (bucket := self.sync_bucket(preferences, s3_access, bucket_name, destination)) is None:
                continue  # don't count or check a sync that could not be done

            synced_count = bucket.sync_result.get_count(S3SyncOutcome.would_download if dry_run else S3SyncOutcome.downloaded)
            total_synced_count += synced_count
            self.sync_exceptions_out(bucket)

            # nothing was synced in a dry run, so there is nothing to check (finding out what a sync would do makes requests though)
            if dry_run:
                count += 1
                self.info_out(f"{bucket_name} : {synced_count} files would be synced")
                self.usage_out(bucket, bucket_name)
                continue

            self.counts.files_synced = total_synced_count
            # when stopped, the downloads that had not started were not attempted, so there is nothing to check
            if not self.stop_requested:
                synced_buckets.append(bucket)
                if self.check_bucket_size(bucket) and not bucket.get_failed():
                    count += 1
                    self.counts.backed_up = count

            # After the check, whose listing of the bucket is a request too, and after the counts are set, since the history is
            # updated when a transfer is reported. A stop ends the backup at the top of the loop.
            self.usage_out(bucket, bucket_name, bucket.sync_result.get_size(S3SyncOutcome.downloaded))

        if dry_run:
            self.info_out(f"{len(bucket_names)} buckets, {count} dry run, {total_synced_count} files would be synced, {len(exclusions)} excluded")
        else:
            self.info_out(f"{len(bucket_names)} buckets, {count} backed up, {total_synced_count} files synced, {len(exclusions)} excluded")
            if preferences.s3_verify and not self.stop_requested:
                self.verify_backup(synced_buckets)
        self.transfer_summary_out()
