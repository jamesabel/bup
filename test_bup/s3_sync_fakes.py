"""
Stand-ins for awsimple's S3Access in tests of the S3 backup, so a backup runs with given sync results and no S3 at all.
Everything in this file is AI-authored (Claude Code).
"""

from pathlib import Path
from typing import Callable, Dict, List, Optional, Union
from unittest.mock import patch, MagicMock

from awsimple import AWSimpleException, S3ObjectMetadata, S3SyncObject, S3SyncOutcome, S3SyncResult

from bup import UITypes
from bup.s3_backup import S3Backup


def make_sync_result(sync_objects: List[S3SyncObject]) -> S3SyncResult:
    return S3SyncResult({sync_object.key: sync_object for sync_object in sync_objects})


def downloaded(key: str, size: int) -> S3SyncObject:
    return S3SyncObject(key, size, S3SyncOutcome.downloaded)


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
    bucket is in .bucket_accesses, with the keyword arguments it was made with in .bucket_access_kwargs.
    """

    def __init__(self, sync_results: Dict[str, Union[S3SyncResult, Exception, Callable[..., S3SyncResult]]], bucket_region: str = "us-east-1"):
        self.sync_results = sync_results
        self.bucket_region = bucket_region
        self.bucket_accesses: Dict[str, MagicMock] = {}
        # the metadata of the objects (or the exception that getting it raises), by key, for a verification of the local files against S3
        self.object_metadata: Dict[str, Union[S3ObjectMetadata, Exception]] = {}
        self.bucket_access_kwargs: Dict[str, dict] = {}

    def __call__(self, bucket_name: Optional[str] = None, **kwargs) -> MagicMock:
        s3_access = MagicMock()
        s3_access.bucket_list.return_value = list(self.sync_results)
        s3_access.client.head_bucket.return_value = head_bucket_response(self.bucket_region)
        s3_access.get_s3_object_metadata.side_effect = self.get_s3_object_metadata
        if bucket_name is not None:
            sync_result = self.sync_results[bucket_name]
            if isinstance(sync_result, Exception) or callable(sync_result):
                s3_access.sync_to_directory.side_effect = sync_result  # raised, or called as the sync and its return value is the result
            else:
                s3_access.sync_to_directory.return_value = sync_result
                # the listing of the bucket that verifies the sync: the objects of the sync result
                contents = [{"Key": sync_object.key, "Size": sync_object.size} for sync_object in sync_result.objects.values()]
                s3_access.client.get_paginator.return_value.paginate.return_value = [{"Contents": contents}]
            self.bucket_accesses[bucket_name] = s3_access
            self.bucket_access_kwargs[bucket_name] = kwargs
        return s3_access

    def get_s3_object_metadata(self, s3_key: str) -> S3ObjectMetadata:
        if s3_key not in self.object_metadata:
            raise AWSimpleException(f"{s3_key=} does not exist")
        if isinstance(object_metadata := self.object_metadata[s3_key], Exception):
            raise object_metadata
        return object_metadata


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
