"""
Tests for what the S3 backup reports as received from S3.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import logging
import os
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto.server import ThreadedMotoServer

from bup import UITypes, BackupTypes, __application_name__
from bup.s3_backup import (
    S3Backup,
    get_synced_size,
    get_synced_keys,
    get_local_path,
    get_key_components,
    get_bucket_region,
    find_s3_objects_without_local_file,
    find_local_name_mismatches,
    rename_local_to_match_key,
)
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
def test_get_local_path_drops_empty_key_components(tmp_path):
    assert get_local_path(tmp_path, "a.txt") == Path(tmp_path, "a.txt")
    assert get_local_path(tmp_path, "folder/sub folder/a.txt") == Path(tmp_path, "folder", "sub folder", "a.txt")
    # a key that starts with "/" does not make the path absolute (which would be outside of the backup)
    assert get_local_path(tmp_path, "/temp/a.txt") == Path(tmp_path, "temp", "a.txt")
    assert get_local_path(tmp_path, "folder//a.txt") == Path(tmp_path, "folder", "a.txt")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_keys_with_empty_key_components(tmp_path):
    # as "aws s3 sync" prints them: the key as it is in S3, and the local path without the empty components
    sync_stdout = (
        f"download: s3://my-bucket//temp/2020/manifest.json to {tmp_path}{os.sep}temp{os.sep}2020{os.sep}manifest.json\n"
        f"download: s3://my-bucket/folder//a to b.txt to {tmp_path}{os.sep}folder{os.sep}a to b.txt\n"
    )

    assert get_synced_keys(sync_stdout, "my-bucket", tmp_path) == ["/temp/2020/manifest.json", "folder//a to b.txt"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_keys_with_local_paths_relative_to_the_current_directory(tmp_path, monkeypatch):
    # the AWS CLI prints the local path relative to the current directory when the backup is on the same drive
    destination = tmp_path / "backup" / "my-bucket"
    current_directory = tmp_path / "work" / "here"
    current_directory.mkdir(parents=True)
    monkeypatch.chdir(current_directory)
    relative_destination = os.path.join("..", "..", "backup", "my-bucket")
    sync_stdout = (
        f"download: s3://my-bucket/a.txt to {relative_destination}{os.sep}a.txt\n"
        f"download: s3://my-bucket/folder/b to c.txt to {relative_destination}{os.sep}folder{os.sep}b to c.txt\n"
        f"download: s3://my-bucket/elsewhere.txt to {os.path.join('..', 'not-the-backup', 'elsewhere.txt')}\n"  # not this bucket's local path
    )

    assert get_synced_keys(sync_stdout, "my-bucket", destination) == ["a.txt", "folder/b to c.txt"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_size_of_keys_with_empty_components(tmp_path):
    Path(tmp_path, "temp").mkdir()
    Path(tmp_path, "temp", "a.txt").write_bytes(b"x" * 10)
    Path(tmp_path, "folder").mkdir()
    Path(tmp_path, "folder", "b.txt").write_bytes(b"x" * 20)

    assert get_synced_size(tmp_path, ["/temp/a.txt", "folder//b.txt"]) == 30


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def moto_s3_endpoint(monkeypatch, tmp_path):
    """
    A local in-memory S3 server, with the environment set up so both in-process boto3/awsimple and the AWS CLI subprocess
    (via AWS_ENDPOINT_URL) talk to it and not real AWS.
    """
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    endpoint_url = f"http://{host}:{port}"
    monkeypatch.setenv("AWS_ENDPOINT_URL", endpoint_url)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    # keep any real AWS profile/config on this machine from leaking into the test
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials-file"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config-file"))
    # moto keeps its buckets in this process, across servers: start without the buckets of earlier tests, and leave none behind
    reset_request = urllib.request.Request(f"{endpoint_url}/moto-api/reset", method="POST")
    urllib.request.urlopen(reset_request, timeout=10.0).close()
    yield endpoint_url
    urllib.request.urlopen(reset_request, timeout=10.0).close()
    server.stop()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_sync_of_keys_with_slashes_including_a_leading_slash(moto_s3_endpoint, tmp_path, online, caplog):
    """
    Run the real "aws s3 sync" (the actual AWS CLI subprocess) against a local S3 server holding objects whose keys start with
    "/" or contain "//", next to ordinary keys with "/" in them: every object is backed up to its local file, and what was
    downloaded is counted (and costed) for all of them.
    """
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="slash-keys-bucket")
    s3_client.put_object(Bucket="slash-keys-bucket", Key="plain.txt", Body=b"x" * 1000)
    s3_client.put_object(Bucket="slash-keys-bucket", Key="/temp/leading.txt", Body=b"x" * 2000)
    s3_client.put_object(Bucket="slash-keys-bucket", Key="folder//doubled.txt", Body=b"x" * 4000)
    s3_client.put_object(Bucket="slash-keys-bucket", Key="folder/sub folder/nested.txt", Body=b"x" * 8000)
    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=False, s3_size_only=False, aws_profile=None, aws_access_key_id=None, aws_secret_access_key=None, aws_region=None)
    infos = []
    warnings = []
    errors = []
    backup = S3Backup(UITypes.cli, infos.append, warnings.append, errors.append)

    with (
        patch("bup.s3_backup.get_preferences", return_value=preferences),
        patch("bup.s3_backup.ExclusionPreferences") as mock_exclusions,
        caplog.at_level(logging.WARNING, logger=__application_name__),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()

    destination = tmp_path / "s3" / "slash-keys-bucket"
    assert (destination / "temp" / "leading.txt").stat().st_size == 2000
    assert (destination / "folder" / "doubled.txt").stat().st_size == 4000
    assert not any("could not determine the S3 key" in record.getMessage() for record in caplog.records)
    assert not any("could not get size of downloaded file" in record.getMessage() for record in caplog.records)
    assert (destination / "folder" / "sub folder" / "nested.txt").stat().st_size == 8000
    assert [(transfer_record.name, transfer_record.received_bytes) for transfer_record in backup.transfer_records] == [("slash-keys-bucket", 15000)]
    assert backup.transfer_records[0].cost == pytest.approx(15000 / bytes_per_gb * 0.09)
    assert any("4 files synced" in info for info in infos)
    assert warnings == []  # every object has its local file, so nothing is reported as missing or misnamed
    assert errors == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_key_components():
    assert get_key_components("a.txt") == ["a.txt"]
    assert get_key_components("folder/sub folder/a.txt") == ["folder", "sub folder", "a.txt"]
    assert get_key_components("/temp/a.txt") == ["temp", "a.txt"]
    assert get_key_components("//temp///a.txt") == ["temp", "a.txt"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_keys_with_empty_components_are_not_reported_as_missing_local_files(tmp_path):
    Path(tmp_path, "temp").mkdir()
    Path(tmp_path, "temp", "leading.txt").write_bytes(b"x")
    Path(tmp_path, "folder").mkdir()
    Path(tmp_path, "folder", "doubled.txt").write_bytes(b"x")
    s3_objects = [{"Key": key, "Size": 1} for key in ("/temp/leading.txt", "folder//doubled.txt", "/temp/not-downloaded.txt")]
    s3_client = MagicMock()
    s3_client.get_paginator.return_value.paginate.return_value = [{"Contents": s3_objects}]

    folder_marker_keys, missing_keys = find_s3_objects_without_local_file(s3_client, "my-bucket", tmp_path)

    assert folder_marker_keys == []
    assert missing_keys == ["/temp/not-downloaded.txt"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_local_name_of_a_key_that_starts_with_a_slash_is_checked_and_fixed(tmp_path):
    # the local copy differs from the key only in case, which makes "aws s3 sync" download the object on every run
    Path(tmp_path, "Temp").mkdir()
    Path(tmp_path, "Temp", "leading.txt").write_bytes(b"x")

    mismatches = find_local_name_mismatches(tmp_path, "/temp/leading.txt")
    assert [(mismatch.local_name, mismatch.key_name) for mismatch in mismatches] == [("Temp", "temp")]

    renames, failure = rename_local_to_match_key(tmp_path, "/temp/leading.txt")
    assert failure is None
    assert len(renames) == 1
    assert "temp" in os.listdir(tmp_path)
    assert find_local_name_mismatches(tmp_path, "/temp/leading.txt") == []


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
