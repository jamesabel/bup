import logging
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import boto3
import pytest
from awsimple import S3SyncResult
from botocore.exceptions import ClientError, NoCredentialsError
from moto.server import ThreadedMotoServer

from bup import UITypes, __application_name__
from bup.s3_backup import S3Backup, compare_backup_sizes, get_bucket_size, get_dir_size

fake_aws_cli = (Path("aws"), Path("python"))


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, Bucket):
        return self.pages


class FakeS3Client:
    def __init__(self, pages):
        self.pages = pages

    def get_paginator(self, operation_name):
        return FakePaginator(self.pages)


def _make_backup(info=None, warning=None, error=None) -> S3Backup:
    return S3Backup(UITypes.cli, info or (lambda s: None), warning or (lambda s: None), error or (lambda s: None))


def _make_preferences(tmp_path: Path, dry_run: bool = False, s3_size_only: bool = False) -> MagicMock:
    preferences = MagicMock()
    preferences.backup_directory = str(tmp_path)
    preferences.dry_run = dry_run
    preferences.s3_size_only = s3_size_only
    preferences.aws_profile = None
    preferences.aws_access_key_id = None
    preferences.aws_secret_access_key = None
    preferences.aws_region = None
    return preferences


def test_compare_backup_sizes_missing_files_is_error():
    level, message = compare_backup_sizes(s3_total_size=100, local_size=50)
    assert level == "error"
    assert "not all files" in message


def test_compare_backup_sizes_match_is_info():
    level, _unused_message = compare_backup_sizes(s3_total_size=100, local_size=100)
    assert level == "info"


def test_compare_backup_sizes_local_larger_is_info():
    # sync intentionally doesn't use --delete, so a larger local backup is expected over time and not a warning
    level, message = compare_backup_sizes(s3_total_size=50, local_size=100)
    assert level == "info"
    assert "retained" in message


def test_get_bucket_size_sums_pages():
    client = FakeS3Client([{"Contents": [{"Size": 10}, {"Size": 5}]}, {"Contents": [{"Size": 1}]}, {}])
    total_size, object_count = get_bucket_size(client, "my-bucket")
    assert total_size == 16
    assert object_count == 3


def test_get_dir_size(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"12345")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_bytes(b"123")
    dir_size, file_count = get_dir_size(tmp_path)
    assert dir_size == 8
    assert file_count == 2


def test_get_dir_size_tolerates_unreadable_file(tmp_path):
    (tmp_path / "good.txt").write_bytes(b"1234")
    (tmp_path / "bad.txt").write_bytes(b"12")

    original_getsize = os.path.getsize

    def flaky_getsize(file_path):
        if "bad.txt" in str(file_path):
            raise OSError("simulated unreadable file")
        return original_getsize(file_path)

    with patch("bup.s3_backup.os.path.getsize", side_effect=flaky_getsize):
        dir_size, file_count = get_dir_size(tmp_path)
    assert dir_size == 4
    assert file_count == 1


@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_bucket_list_failure_surfaces_error(mock_get_prefs, mock_s3_access, mock_exclusions, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.side_effect = NoCredentialsError()
    errors = []
    backup = _make_backup(error=errors.append)

    backup.run()

    assert len(errors) == 1
    assert "could not list S3 buckets" in errors[0]
    assert backup.error_count == 1


@pytest.fixture
def moto_s3_endpoint(monkeypatch, tmp_path):
    """
    A local in-memory S3 server, with the environment set up so both in-process boto3/awsimple and the
    AWS CLI subprocess (via AWS_ENDPOINT_URL) talk to it instead of real AWS.
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
    yield endpoint_url
    server.stop()


@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.get_preferences")
def test_s3_sync_end_to_end_including_no_redownload(mock_get_prefs, mock_exclusions, moto_s3_endpoint, tmp_path):
    """
    Run the real "aws s3 sync" (the actual AWS CLI subprocess) against a local S3 server: the first backup
    downloads everything, and a second backup re-downloads nothing since the objects are already backed up.
    """
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_exclusions.return_value.get_no_comments.return_value = []

    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="e2e-bucket")
    s3_client.put_object(Bucket="e2e-bucket", Key="top.txt", Body=b"top content")
    s3_client.put_object(Bucket="e2e-bucket", Key="folder/nested.txt", Body=b"nested content")  # "/" in the object name

    infos = []
    errors = []
    backup = _make_backup(info=infos.append, error=errors.append)
    backup.run()

    assert errors == []
    top_file = tmp_path / "s3" / "e2e-bucket" / "top.txt"
    nested_file = tmp_path / "s3" / "e2e-bucket" / "folder" / "nested.txt"
    assert top_file.read_bytes() == b"top content"
    assert nested_file.read_bytes() == b"nested content"
    assert any("2 files synced" in i for i in infos)

    modification_times = (top_file.stat().st_mtime_ns, nested_file.stat().st_mtime_ns)

    second_infos = []
    second_errors = []
    second_backup = _make_backup(info=second_infos.append, error=second_errors.append)
    second_backup.run()

    assert second_errors == []
    assert any("0 files synced" in i for i in second_infos)
    # untouched files prove sync didn't re-download them
    assert (top_file.stat().st_mtime_ns, nested_file.stat().st_mtime_ns) == modification_times


@patch("bup.s3_backup.get_bucket_size")
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_verification_failure_surfaces_error(mock_get_prefs, mock_s3_access, mock_exclusions, mock_get_bucket_size, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_s3_access.return_value.sync_to_directory.return_value = S3SyncResult()  # the sync itself succeeds (an empty bucket)
    mock_exclusions.return_value.get_no_comments.return_value = []
    mock_get_bucket_size.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListObjectsV2")
    errors = []
    backup = _make_backup(error=errors.append)

    backup.run()

    assert any("could not list contents" in e for e in errors)
