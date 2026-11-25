"""
Stand-ins for awsimple's S3Access in tests of the S3 backup, so a backup runs with given sync results and no S3 at all.
Everything in this file is AI-authored (Claude Code).
"""

from pathlib import Path
from threading import Event
from typing import Callable, Dict, List, Optional, Union
from unittest.mock import patch, MagicMock

from awsimple import S3SyncObject, S3SyncOutcome, S3SyncResult, S3Usage, S3VerifyObject, S3VerifyOutcome, S3VerifyResult

from bup import UITypes
from bup.s3_backup import S3Backup


def make_sync_result(sync_objects: List[S3SyncObject]) -> S3SyncResult:
    return S3SyncResult({sync_object.key: sync_object for sync_object in sync_objects})


def downloaded(key: str, size: int) -> S3SyncObject:
    return S3SyncObject(key, size, S3SyncOutcome.downloaded)


def make_verify_result(verify_objects: List[S3VerifyObject]) -> S3VerifyResult:
    return S3VerifyResult({verify_object.key: verify_object for verify_object in verify_objects})


def verified(key: str, hash_name: Optional[str] = "SHA-512") -> S3VerifyObject:
    return S3VerifyObject(key, S3VerifyOutcome.verified, hash_name=hash_name)


def head_bucket_response(bucket_region: str) -> dict:
    return {"BucketRegion": bucket_region, "ResponseMetadata": {"HTTPHeaders": {"x-amz-bucket-region": bucket_region}}}


def make_preferences(tmp_path: Path, dry_run: bool = False, s3_size_only: bool = False, aws_region: Optional[str] = None, s3_verify: bool = False) -> MagicMock:
    return MagicMock(
        backup_directory=str(tmp_path),
        dry_run=dry_run,
        s3_size_only=s3_size_only,
        s3_verify=s3_verify,
        aws_profile=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_region=aws_region,
    )


class FakeS3:
    """
    What S3Access is replaced with: every instance lists the given buckets, and the instance of a bucket syncs with that bucket's
    given result (or raises it, if it is an exception, or calls it for the result, if it is a function). The instance made for each
    bucket is in .bucket_accesses, with the keyword arguments it was made with in .bucket_access_kwargs. A verification of a bucket
    gives the result in .verify_results for it, or without one finds every file verified that the sync downloaded or found up to date.

    Every instance has a usage (awsimple's S3Usage) as an S3Access has, which nothing is counted in since no request is made: a test
    gives the S3 requests that the sync and the verification of a bucket count in .sync_requests and .verify_requests.
    """

    def __init__(self, sync_results: Dict[str, Union[S3SyncResult, Exception, Callable[..., S3SyncResult]]], bucket_region: str = "us-east-1"):
        self.sync_results = sync_results
        self.bucket_region = bucket_region
        self.bucket_accesses: Dict[str, MagicMock] = {}
        self.verify_results: Dict[str, S3VerifyResult] = {}  # by bucket name
        self.bucket_access_kwargs: Dict[str, dict] = {}
        # by bucket name, each request as (S3 API operation, storage class) or, for one S3 sent an object for, (S3 API operation, storage class, bytes sent)
        self.sync_requests: Dict[str, List[tuple]] = {}
        self.verify_requests: Dict[str, List[tuple]] = {}  # likewise

    def __call__(self, bucket_name: Optional[str] = None, **kwargs) -> MagicMock:
        s3_access = MagicMock()
        s3_access.usage = S3Usage()
        s3_access.bucket_list.return_value = list(self.sync_results)
        s3_access.client.head_bucket.return_value = head_bucket_response(self.bucket_region)
        if bucket_name is not None:
            sync_result = self.sync_results[bucket_name]
            s3_access.sync_to_directory.side_effect = lambda *args, **kwargs: self.run_sync(bucket_name, *args, **kwargs)
            if isinstance(sync_result, S3SyncResult):
                # the listing of the bucket that verifies the sync: the objects of the sync result
                contents = [{"Key": sync_object.key, "Size": sync_object.size} for sync_object in sync_result.objects.values()]
                s3_access.client.get_paginator.return_value.paginate.return_value = [{"Contents": contents}]
            s3_access.verify_directory.side_effect = lambda dest_dir, **kwargs: self.run_verification(bucket_name, **kwargs)
            self.bucket_accesses[bucket_name] = s3_access
            self.bucket_access_kwargs[bucket_name] = kwargs
        return s3_access

    def record_requests(self, bucket_name: str, requests: Dict[str, List[tuple]]):
        for request in requests.get(bucket_name, []):
            self.bucket_accesses[bucket_name].usage.record(*request)

    def run_sync(self, bucket_name: str, *args, **kwargs) -> S3SyncResult:
        """
        The sync of a bucket: its given result, which is raised if it is an exception, and called as the sync if it is a function.
        """
        self.record_requests(bucket_name, self.sync_requests)
        sync_result = self.sync_results[bucket_name]
        if isinstance(sync_result, Exception):
            raise sync_result
        return sync_result(*args, **kwargs) if callable(sync_result) else sync_result

    def run_verification(self, bucket_name: str, sync_result: S3SyncResult, stop_event: Optional[Event] = None, callback: Optional[Callable[[S3VerifyObject], None]] = None) -> S3VerifyResult:
        """
        What awsimple's verify_directory() does with the objects of the result, one after the other: once a stop is requested the
        objects that are left are not attempted, and the callback is called with every object.
        """
        self.record_requests(bucket_name, self.verify_requests)
        verify_result = self.verify_directory(bucket_name, sync_result)
        for verify_object in verify_result.objects.values():
            if stop_event is not None and stop_event.is_set() and verify_object.outcome != S3VerifyOutcome.skipped:
                verify_object.set_outcome(S3VerifyOutcome.not_attempted)
            if callback is not None:
                callback(verify_object)
        return verify_result

    def verify_directory(self, bucket_name: str, sync_result: S3SyncResult) -> S3VerifyResult:
        if bucket_name in self.verify_results:
            return self.verify_results[bucket_name]
        return make_verify_result([verified(sync_object.key) for sync_object in sync_result.objects.values() if sync_object.outcome in (S3SyncOutcome.downloaded, S3SyncOutcome.up_to_date)])


def run_s3_backup(
    tmp_path: Path, fake_s3: Callable[..., MagicMock], preferences: Optional[MagicMock] = None, exclusions: Optional[List[str]] = None, backup: Optional[S3Backup] = None
) -> S3Backup:
    """
    Run an S3 backup to tmp_path against a FakeS3 (or a function that makes what a FakeS3 makes, for a test that changes it).
    :return: the backup, with what it put out in .infos, .warnings and .errors
    """
    if backup is None:
        backup = make_s3_backup()
    with (
        patch("bup.s3_backup.get_preferences", return_value=make_preferences(tmp_path) if preferences is None else preferences),
        patch("bup.s3_backup.S3Access", fake_s3),
        patch("bup.s3_backup.ExclusionPreferences") as mock_exclusions,
    ):
        mock_exclusions.return_value.get_no_comments.return_value = exclusions or []
        backup.run()
    return backup


def make_s3_backup() -> S3Backup:
    infos: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []
    backup = S3Backup(UITypes.cli, infos.append, warnings.append, errors.append)
    backup.infos = infos
    backup.warnings = warnings
    backup.errors = errors
    return backup


def run_real_s3_backup(backup_directory: Path, **preferences) -> S3Backup:
    """
    Run an S3 backup with the real awsimple S3Access, against the local S3 server of the moto_s3_endpoint fixture (see conftest.py).
    :param preferences: the preferences that are not the defaults of make_preferences(), e.g. dry_run=True
    :return: the backup, with what it put out in .infos, .warnings and .errors
    """
    backup = make_s3_backup()
    with (
        patch("bup.s3_backup.get_preferences", return_value=make_preferences(backup_directory, **preferences)),
        patch("bup.s3_backup.ExclusionPreferences") as mock_exclusions,
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return backup
