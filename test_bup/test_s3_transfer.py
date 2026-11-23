"""
Tests for what the S3 backup reports as received from S3.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from awsimple import S3SyncObject, S3SyncOutcome
from botocore.exceptions import ClientError

from bup import BackupTypes
from bup.s3_backup import S3Backup, get_bucket_region
from bup.transfer import TransferRecord, bytes_per_gb

from .aws_price_offers import make_fetch_offer
from .s3_sync_fakes import FakeS3, downloaded, head_bucket_response, make_preferences, make_sync_result, run_s3_backup


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def online(monkeypatch):
    # the AWS price list is reachable - the returned stand-in for fetch_offer records what was fetched
    fake_fetch_offer = make_fetch_offer()
    monkeypatch.setattr("bup.aws_prices.fetch_offer", fake_fetch_offer)
    return fake_fetch_offer


def _run_backup(tmp_path: Path, file_sizes: dict, dry_run: bool = False, bucket_region: str = "us-east-1") -> S3Backup:
    """
    Run an S3 backup of "my-bucket" whose (faked) sync downloads the given files (or would download them, for a dry run).
    :return: the backup, with its info output in .infos
    """
    destination = Path(tmp_path, "s3", "my-bucket")
    destination.mkdir(parents=True)
    sync_objects = []
    for file_name, file_size in file_sizes.items():
        if dry_run:
            sync_objects.append(S3SyncObject(file_name, file_size, S3SyncOutcome.would_download))
        else:
            Path(destination, file_name).write_bytes(b"x" * file_size)
            sync_objects.append(downloaded(file_name, file_size))
    fake_s3 = FakeS3({"my-bucket": make_sync_result(sync_objects)}, bucket_region=bucket_region)
    return run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, dry_run=dry_run))


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_bucket_region():
    s3_client = MagicMock()
    s3_client.head_bucket.return_value = head_bucket_response("eu-west-1")

    assert get_bucket_region(s3_client, "my-bucket") == "eu-west-1"
    s3_client.head_bucket.assert_called_once_with(Bucket="my-bucket")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_bucket_region_from_the_response_header():
    # older boto3 versions only have the region in the HTTP header
    s3_client = MagicMock()
    s3_client.head_bucket.return_value = {"ResponseMetadata": {"HTTPHeaders": {"x-amz-bucket-region": "ap-southeast-2"}}}

    assert get_bucket_region(s3_client, "my-bucket") == "ap-southeast-2"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_bucket_region_undetermined(caplog):
    s3_client = MagicMock()
    s3_client.head_bucket.return_value = {"ResponseMetadata": {"HTTPHeaders": {}}}
    assert get_bucket_region(s3_client, "my-bucket") is None

    s3_client.head_bucket.side_effect = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket")
    assert get_bucket_region(s3_client, "my-bucket") is None
    assert any("could not determine the region of my-bucket" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_downloaded_bytes_and_cost_are_reported(tmp_path, online):
    backup = _run_backup(tmp_path, {"a.txt": 1024, "b.txt": 2048})

    assert "my-bucket : received 3.0 KB, approximately less than $0.0001 before any AWS free allowance" in backup.infos
    assert "transfer total : received 3.0 KB, approximately less than $0.0001 before any AWS free allowance" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_only_downloaded_objects_are_counted_as_received(tmp_path):
    # objects that are already up to date, that the sync skips, or whose download failed received nothing that is kept
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    Path(tmp_path, "s3", "my-bucket", "new.txt").write_bytes(b"x" * 1024)
    Path(tmp_path, "s3", "my-bucket", "old.txt").write_bytes(b"x" * 4096)
    sync_objects = [
        downloaded("new.txt", 1024),
        S3SyncObject("old.txt", 4096, S3SyncOutcome.up_to_date),
        S3SyncObject("archive.zip", 8192, S3SyncOutcome.skipped, reason="archived"),
        S3SyncObject("broken.txt", 16384, S3SyncOutcome.failed, reason="connection lost"),
    ]

    backup = run_s3_backup(tmp_path, FakeS3({"my-bucket": make_sync_result(sync_objects)}))

    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 1024, cost=None, region="us-east-1")]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cost_uses_the_prices_of_the_buckets_region(tmp_path, online):
    backup = _run_backup(tmp_path, {"a.txt": 4096}, bucket_region="eu-west-1")

    assert online.fetched[0] == ("AWSDataTransfer", "eu-west-1")
    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 4096, cost=pytest.approx(4096 / bytes_per_gb * 0.09), region="eu-west-1")]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_without_prices_the_bytes_are_reported_without_a_cost(tmp_path):
    # offline (see conftest.py), and no prices were fetched before
    backup = _run_backup(tmp_path, {"a.txt": 1024})

    assert "my-bucket : received 1.0 KB" in backup.infos
    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 1024, cost=None, region="us-east-1")]
    assert backup.error_count == 0


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_nothing_downloaded_reports_only_a_zero_total_and_needs_no_prices(tmp_path, online):
    backup = _run_backup(tmp_path, {})

    assert not any(info.startswith("my-bucket : received") for info in backup.infos)
    assert "transfer total : received 0 B" in backup.infos
    assert online.fetched == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dry_run_reports_no_transfer(tmp_path, online):
    backup = _run_backup(tmp_path, {"a.txt": 1024}, dry_run=True)

    assert not any("received" in info for info in backup.infos)
    assert online.fetched == []
