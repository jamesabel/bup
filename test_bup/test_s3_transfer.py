"""
Tests for what the S3 backup reports as received from S3.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from bup import UITypes, BackupTypes
from bup.s3_backup import S3Backup, get_synced_size, get_bucket_region
from bup.transfer import TransferRecord, bytes_per_gb

from .aws_price_offers import make_fetch_offer

fake_aws_cli = (Path("aws"), Path("python"))


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture(autouse=True)
def up_to_date_aws_cli():
    # keep run() from shelling out to a real AWS CLI or hitting PyPI for the version check
    with (
        patch("bup.s3_backup.get_aws_cli_version", return_value="1.0.0"),
        patch("bup.s3_backup.get_latest_awscli_version", return_value="1.0.0"),
    ):
        yield


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def online(monkeypatch):
    # the AWS price list is reachable - the returned stand-in for fetch_offer records what was fetched
    fake_fetch_offer = make_fetch_offer()
    monkeypatch.setattr("bup.aws_prices.fetch_offer", fake_fetch_offer)
    return fake_fetch_offer


def _head_bucket_response(bucket_region: str) -> dict:
    return {"BucketRegion": bucket_region, "ResponseMetadata": {"HTTPHeaders": {"x-amz-bucket-region": bucket_region}}}


def _run_backup(tmp_path: Path, file_sizes: dict, dry_run: bool = False, bucket_region: str = "us-east-1") -> S3Backup:
    """
    Run an S3 backup of "my-bucket" whose (faked) sync downloads the given files.
    :return: the backup, with its info output in .infos
    """
    destination = Path(tmp_path, "s3", "my-bucket")
    destination.mkdir(parents=True)
    sync_stdout = ""
    for file_name, file_size in file_sizes.items():
        Path(destination, file_name).write_bytes(b"x" * file_size)
        sync_stdout += f"download: s3://my-bucket/{file_name} to {destination}{os.sep}{file_name}\n"
    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=dry_run, s3_size_only=False, aws_profile=None, aws_access_key_id=None, aws_secret_access_key=None, aws_region=None)
    infos = []
    backup = S3Backup(UITypes.cli, infos.append, lambda s: None, lambda s: None)
    backup.infos = infos
    with (
        patch("bup.s3_backup.get_preferences", return_value=preferences),
        patch("bup.s3_backup.S3Access") as mock_s3_access,
        patch("bup.s3_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli),
        patch("bup.s3_backup.get_bucket_size", return_value=(sum(file_sizes.values()), len(file_sizes))),
        patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")),
    ):
        mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
        mock_s3_access.return_value.client.head_bucket.return_value = _head_bucket_response(bucket_region)
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return backup


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_size(tmp_path):
    Path(tmp_path, "folder").mkdir()
    Path(tmp_path, "a.txt").write_bytes(b"x" * 10)
    Path(tmp_path, "folder", "b.txt").write_bytes(b"x" * 20)
    Path(tmp_path, "not_synced.txt").write_bytes(b"x" * 40)

    assert get_synced_size(tmp_path, ["a.txt", "folder/b.txt"]) == 30
    assert get_synced_size(tmp_path, []) == 0


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_size_skips_a_missing_file_with_a_warning(tmp_path, caplog):
    Path(tmp_path, "a.txt").write_bytes(b"x" * 10)

    assert get_synced_size(tmp_path, ["a.txt", "missing.txt"]) == 10
    assert any("could not get size of downloaded file" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_bucket_region():
    s3_client = MagicMock()
    s3_client.head_bucket.return_value = _head_bucket_response("eu-west-1")

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
