"""
What the verification of the S3 backup against S3 (see S3Backup.verify_bucket()) needs besides awsimple's verification itself: what
the verification of a bucket found, and the watch that ends a verification when S3 can no longer be reached.
"""

import threading
from dataclasses import dataclass
from typing import List, Optional, Set

from awsimple import S3VerifyObject, S3VerifyOutcome
from botocore.exceptions import BotoCoreError, ClientError
from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)

# during a verification, find out if S3 can still be reached once this many objects have failed one after the other (see VerifyWatch)
verify_failures_before_reachability_check = 3


def get_s3_unreachable_reason(s3_client, bucket_name: str) -> Optional[str]:
    """
    Find out if S3 can be reached, with one request about a bucket. Any answer from S3 means it can be, whatever the answer is
    (e.g. access to the bucket is denied).

    :param s3_client: a boto3 S3 client
    :param bucket_name: the bucket to ask about
    :return: None if S3 answered, otherwise why the request could not be made (e.g. no connection, or the credentials are no longer there)
    """
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        return None  # an answer from S3
    except BotoCoreError as e:
        return str(e)
    return None


@dataclass
class BucketVerification:
    """
    What the verification of a bucket against S3 found (see S3Backup.verify_bucket()).
    """

    verified_count: int = 0  # files that were compared with their S3 object, or that this was attempted for
    differ_count: int = 0  # those that are not a copy of their S3 object
    failed_count: int = 0  # those that could not be verified
    unreachable: bool = False  # True if the verification ended because S3 could no longer be reached


class VerifyWatch:
    """
    Watches the verification of a bucket as it goes, to end it when S3 can no longer be reached (e.g. the internet connection drops).
    awsimple makes a failed request the outcome of that one object and goes on with the others, so without this every file that is
    left fails after its own retries, and is an error of its own.

    A failed object does not say why it failed, so once verify_failures_before_reachability_check objects have failed one after the
    other, S3 is asked about the bucket. If there is no answer, the verification is stopped, and those failures (with any of objects
    that were under way) are in unreachable_keys. If S3 answers, the objects failed for reasons of their own.

    The verification is given the stop event of this watch, which is also set when the backup is stopped.
    """

    def __init__(self, s3_client, bucket_name: str, backup_stop_event: threading.Event):
        """
        :param s3_client: the boto3 S3 client of the access to the bucket that is verified, which S3 is asked with
        :param bucket_name: the bucket that is verified
        :param backup_stop_event: the stop event of the backup
        """
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.backup_stop_event = backup_stop_event
        self.stop_event = threading.Event()  # for the verification: the backup was stopped, or S3 can not be reached
        self.unreachable_reason: Optional[str] = None  # why S3 can not be reached (None while it can be, as far as is known)
        self.unreachable_keys: Set[str] = set()  # the objects that failed because S3 could not be reached
        self._last_failed_keys: List[str] = []  # the objects that failed since an object was last verified, or S3 last answered

    def object_out(self, verify_object: S3VerifyObject):
        """
        The callback of the verification, which awsimple calls (from the thread of the backup) with every object as its outcome is known.
        """
        if self.backup_stop_event.is_set():
            self.stop_event.set()
        if verify_object.outcome == S3VerifyOutcome.failed:
            self._last_failed_keys.append(verify_object.key)
            if self.unreachable_reason is not None:
                self.unreachable_keys.add(verify_object.key)  # was under way when S3 was found to be unreachable
            elif len(self._last_failed_keys) >= verify_failures_before_reachability_check:
                self.check_last_failures()
        elif verify_object.outcome in (S3VerifyOutcome.verified, S3VerifyOutcome.differs, S3VerifyOutcome.mtime_differs):
            self._last_failed_keys = []  # the metadata of this object was had, so S3 can be reached

    def check_last_failures(self):
        """
        If objects failed since an object was last verified, find out if that is because S3 can not be reached, and if so stop the
        verification. Also called once the verification is done, for a bucket that ends with fewer failures than are checked during it.
        """
        if self.unreachable_reason is None and len(self._last_failed_keys) > 0:
            self.unreachable_reason = get_s3_unreachable_reason(self.s3_client, self.bucket_name)
            if self.unreachable_reason is not None:
                log.warning(f"{self.bucket_name} : S3 can not be reached, so the verification ends : {self.unreachable_reason}")
                self.unreachable_keys.update(self._last_failed_keys)
                self.stop_event.set()
            self._last_failed_keys = []
