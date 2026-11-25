"""
Tests for what the S3 backup reports as received from S3.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

from pathlib import Path
from unittest.mock import MagicMock

import boto3
import pytest
from awsimple import S3SyncObject, S3SyncOutcome
from botocore.exceptions import ClientError

from bup import BackupTypes
from bup.s3_backup import S3Backup, get_bucket_region
from bup.transfer import TransferRecord, bytes_per_gb

from .aws_price_offers import make_fetch_offer
from .s3_sync_fakes import FakeS3, downloaded, head_bucket_response, make_preferences, make_sync_result, run_real_s3_backup, run_s3_backup


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

    assert [region for _unused_service_code, region in online.fetched] == ["eu-west-1"] * 3  # the price list files of the bucket's region
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
def test_dry_run_receives_nothing(tmp_path, online):
    # the sync of the fake makes no requests, so there is nothing to report for the bucket
    backup = _run_backup(tmp_path, {"a.txt": 1024}, dry_run=True)

    assert not any(info.startswith("my-bucket : received") for info in backup.infos)
    assert "transfer total : received 0 B" in backup.infos
    assert online.fetched == []


def _one_file_bucket(tmp_path: Path) -> FakeS3:
    """
    :return: a FakeS3 of "my-bucket", whose sync downloads a.txt (1024 bytes)
    """
    destination = Path(tmp_path, "s3", "my-bucket")
    destination.mkdir(parents=True)
    Path(destination, "a.txt").write_bytes(b"x" * 1024)
    return FakeS3({"my-bucket": make_sync_result([downloaded("a.txt", 1024)])})


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_requests_are_reported_and_priced_by_tier_and_storage_class(tmp_path, online):
    fake_s3 = _one_file_bucket(tmp_path)
    fake_s3.sync_requests["my-bucket"] = [("ListObjectsV2", "STANDARD")] * 2 + [("HeadObject", "GLACIER_IR")] * 3 + [("GetObject", "STANDARD")]

    backup = run_s3_backup(tmp_path, fake_s3)

    # the data transfer out, 2 list requests, 3 requests for Glacier Instant Retrieval objects and 1 for a STANDARD object
    cost = 1024 / bytes_per_gb * 0.09 + 2 / 1000 * 0.005 + 3 / 1000 * 0.01 + 1 / 1000 * 0.0004
    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 1024, cost=pytest.approx(cost), region="us-east-1", requests=6)]
    assert "my-bucket : received 1.0 KB, 6 S3 requests, approximately less than $0.0001 before any AWS free allowance" in backup.infos
    assert "transfer total : received 1.0 KB, 6 S3 requests, approximately less than $0.0001 before any AWS free allowance" in backup.infos
    assert ("AmazonS3", "us-east-1") in online.fetched


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_requests_of_a_bucket_that_downloaded_nothing_are_reported(tmp_path, online):
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])})
    fake_s3.sync_requests["my-bucket"] = [("ListObjectsV2", "STANDARD")] * 4000

    backup = run_s3_backup(tmp_path, fake_s3)

    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 0, cost=pytest.approx(0.02), region="us-east-1", requests=4000)]
    assert "my-bucket : received 0 B, 4000 S3 requests, approximately $0.0200 before any AWS free allowance" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_requests_that_are_not_charged_for_are_not_reported(tmp_path, online):
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])})
    fake_s3.sync_requests["my-bucket"] = [("DeleteObject", "STANDARD")]

    backup = run_s3_backup(tmp_path, fake_s3)

    assert backup.transfer_records == []
    assert online.fetched == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_requests_of_the_verification_are_reported_on_their_own(tmp_path, online):
    fake_s3 = _one_file_bucket(tmp_path)
    fake_s3.sync_requests["my-bucket"] = [("ListObjectsV2", "STANDARD")]
    fake_s3.verify_requests["my-bucket"] = [("HeadObject", "GLACIER_IR")] * 2000

    backup = run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_verify=True))

    assert backup.transfer_records == [
        TransferRecord(BackupTypes.S3, "my-bucket", 1024, cost=pytest.approx(1024 / bytes_per_gb * 0.09 + 0.000005), region="us-east-1", requests=1),
        TransferRecord(BackupTypes.S3, "my-bucket (verification)", 0, cost=pytest.approx(0.02), region="us-east-1", requests=2000),
    ]
    assert "my-bucket (verification) : received 0 B, 2000 S3 requests, approximately $0.0200 before any AWS free allowance" in backup.infos
    assert "transfer total : received 1.0 KB, 2001 S3 requests, approximately $0.0200 before any AWS free allowance" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_requests_of_a_dry_run_are_reported(tmp_path, online):
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([S3SyncObject("a.txt", 1024, S3SyncOutcome.would_download)])})
    fake_s3.sync_requests["my-bucket"] = [("ListObjectsV2", "STANDARD")] * 2

    backup = run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, dry_run=True))

    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 0, cost=pytest.approx(0.00001), region="us-east-1", requests=2)]
    assert "transfer total : received 0 B, 2 S3 requests, approximately less than $0.0001 before any AWS free allowance" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_requests_without_prices_are_reported_without_a_cost(tmp_path):
    # offline (see conftest.py), and no prices were fetched before
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])})
    fake_s3.sync_requests["my-bucket"] = [("ListObjectsV2", "STANDARD")]

    backup = run_s3_backup(tmp_path, fake_s3)

    assert backup.transfer_records == [TransferRecord(BackupTypes.S3, "my-bucket", 0, cost=None, region="us-east-1", requests=1)]
    assert "my-bucket : received 0 B, 1 S3 requests" in backup.infos
    assert backup.error_count == 0


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_requests_of_a_sync_and_a_verification_are_counted(moto_s3_endpoint, tmp_path, online):
    """
    The real awsimple against a local S3 server: the requests of the sync and of the verification are counted and priced.
    """
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="counted-bucket")
    for number in range(3):
        s3_client.put_object(Bucket="counted-bucket", Key=f"{number}.txt", Body=b"x" * 1000)

    backup = run_real_s3_backup(tmp_path, s3_verify=True)

    assert backup.errors == []
    sync_record, verify_record = backup.transfer_records
    assert (sync_record.name, sync_record.received_bytes, sync_record.region) == ("counted-bucket", 3000, "us-east-1")
    assert sync_record.requests >= 3 + 2  # a request for each object that is downloaded, the listing of the sync and the listing that checks it
    assert sync_record.cost > 3000 / bytes_per_gb * 0.09  # the data transfer out, and the requests
    # the verification is a request for the metadata of each object, which here are STANDARD objects
    assert verify_record == TransferRecord(BackupTypes.S3, "counted-bucket (verification)", 0, cost=pytest.approx(3 / 1000 * 0.0004), region="us-east-1", requests=3)
