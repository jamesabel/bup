import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from botocore.exceptions import ClientError, NoCredentialsError

from bup import UITypes
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


def _make_preferences(tmp_path: Path, dry_run: bool = False) -> MagicMock:
    preferences = MagicMock()
    preferences.backup_directory = str(tmp_path)
    preferences.dry_run = dry_run
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


@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_bucket_list_failure_surfaces_error(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.side_effect = NoCredentialsError()
    errors = []
    backup = _make_backup(error=errors.append)

    backup.run()

    assert len(errors) == 1
    assert "could not list S3 buckets" in errors[0]
    assert backup.error_count == 1


@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_excluded_bucket_is_not_synced(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_s3_access.return_value.bucket_list.return_value = ["excluded-bucket", "backed-up-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = ["excluded-bucket"]
    backup = _make_backup()

    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, "", "")) as mock_subprocess:
        backup.run()

    assert mock_subprocess.call_count == 1
    sync_command_line = mock_subprocess.call_args.args[0]
    assert any("backed-up-bucket" in part for part in sync_command_line)
    assert "--dryrun" in sync_command_line


@patch("bup.s3_backup.get_bucket_size")
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_incomplete_sync_surfaces_error(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    mock_get_bucket_size.return_value = (100, 3)  # S3 has 100 bytes, local destination is empty
    errors = []
    backup = _make_backup(error=errors.append)

    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, "", "")):
        backup.run()

    assert any("not all files backed up" in e for e in errors)


@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_failed_sync_surfaces_error_and_skips_verification(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    errors = []
    infos = []
    backup = _make_backup(info=infos.append, error=errors.append)

    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(1, "", "some failure")):
        backup.run()

    assert any("aws s3 sync failed" in e for e in errors)
    assert any("0 backed up" in i for i in infos)


@patch("bup.s3_backup.get_bucket_size")
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_verification_failure_surfaces_error(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    mock_get_bucket_size.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListObjectsV2")
    errors = []
    backup = _make_backup(error=errors.append)

    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, "", "")):
        backup.run()

    assert any("could not list contents" in e for e in errors)
