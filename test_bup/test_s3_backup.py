import logging
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from moto.server import ThreadedMotoServer

from bup import UITypes, __application_name__
from bup.s3_backup import (
    LocalNameMismatch,
    S3Backup,
    compare_backup_sizes,
    count_synced_files,
    find_local_name_mismatches,
    find_s3_objects_without_local_file,
    get_bucket_size,
    get_dir_size,
    get_synced_keys,
    rename_local_to_match_key,
)

fake_aws_cli = (Path("aws"), Path("python"))


@pytest.fixture(autouse=True)
def up_to_date_aws_cli():
    # keep run() tests from shelling out to a real AWS CLI or hitting PyPI for the version check
    with (
        patch("bup.s3_backup.get_aws_cli_version", return_value="1.0.0"),
        patch("bup.s3_backup.get_latest_awscli_version", return_value="1.0.0"),
    ):
        yield


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


def test_count_synced_files():
    sync_stdout = "download: s3://b/k1.txt to dir\\k1.txt\nCompleted 2 of 3 file(s)\ndownload: s3://b/k2.txt to dir\\k2.txt\ncopy: s3://b/k3.txt to s3://b/k3-copy.txt\n"
    assert count_synced_files(sync_stdout) == 3


def test_count_synced_files_dry_run():
    assert count_synced_files("(dryrun) download: s3://b/k.txt to dir\\k.txt\n") == 1


def test_count_synced_files_slash_in_object_name():
    # S3 object keys may contain "/" (folder-like keys); each key still counts as one file
    sync_stdout = "download: s3://b/folder/sub folder/k1.txt to dir\\folder\\sub folder\\k1.txt\n(dryrun) download: s3://b/a/b/c/k2.txt to dir\\a\\b\\c\\k2.txt\n"
    assert count_synced_files(sync_stdout) == 2


def test_count_synced_files_nothing_to_do():
    # files already up to date produce no output
    assert count_synced_files("") == 0


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
    assert "--size-only" not in sync_command_line  # off by default


@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_size_only_preference_adds_the_flag(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True, s3_size_only=True)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    backup = _make_backup()

    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, "", "")) as mock_subprocess:
        backup.run()

    sync_command_line = mock_subprocess.call_args.args[0]
    assert "--size-only" in sync_command_line


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


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_major_version_behind_aws_cli_surfaces_warning(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_s3_access.return_value.bucket_list.return_value = []
    mock_exclusions.return_value.get_no_comments.return_value = []
    warnings = []
    backup = _make_backup(warning=warnings.append)

    with (
        patch("bup.s3_backup.get_aws_cli_version", return_value="1.0.0"),
        patch("bup.s3_backup.get_latest_awscli_version", return_value="2.0.0"),
    ):
        backup.run()

    assert any("major version behind" in w for w in warnings)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_minor_version_behind_aws_cli_only_goes_to_the_log(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path, caplog):
    # a minor/patch release behind is not shown in the backup output (no warning, no info) - it only goes to the application log
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_s3_access.return_value.bucket_list.return_value = []
    mock_exclusions.return_value.get_no_comments.return_value = []
    warnings = []
    infos = []
    backup = _make_backup(info=infos.append, warning=warnings.append)

    with (
        patch("bup.s3_backup.get_aws_cli_version", return_value="1.0.0"),
        patch("bup.s3_backup.get_latest_awscli_version", return_value="1.1.0"),
        caplog.at_level(logging.INFO, logger=__application_name__),
    ):
        backup.run()

    assert not any("AWS CLI" in w for w in warnings)
    assert not any("AWS CLI" in i for i in infos)
    assert any("not the latest" in record.getMessage() for record in caplog.records)


@patch("bup.s3_backup.get_bucket_size")
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_synced_file_count_in_summary(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    mock_get_bucket_size.return_value = (0, 0)
    infos = []
    backup = _make_backup(info=infos.append)

    sync_stdout = "download: s3://my-bucket/a.txt to dir\\a.txt\ndownload: s3://my-bucket/b.txt to dir\\b.txt\n"
    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")):
        backup.run()

    assert any("2 files synced" in i for i in infos)


@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_synced_file_count_in_dry_run_summary(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    infos = []
    backup = _make_backup(info=infos.append)

    sync_stdout = "(dryrun) download: s3://my-bucket/a.txt to dir\\a.txt\n"
    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")):
        backup.run()

    assert any("1 files would be synced" in i for i in infos)


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


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_keys(tmp_path):
    destination = tmp_path / "b"
    sync_stdout = (
        f"download: s3://b/k1.txt to {destination}{os.sep}k1.txt\n"
        f"Completed 1 of 3 file(s)\n"
        f"(dryrun) download: s3://b/folder/sub folder/k2.txt to {destination}{os.sep}folder{os.sep}sub folder{os.sep}k2.txt\n"
        f"download: s3://b/a to b to {destination}{os.sep}a to b\n"  # a key containing " to "
    )
    assert get_synced_keys(sync_stdout, "b", destination) == ["k1.txt", "folder/sub folder/k2.txt", "a to b"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_synced_keys_unparseable_line_is_skipped_with_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger=__application_name__):
        synced_keys = get_synced_keys("download: s3://b/k.txt to somewhere\\else\\k.txt\n", "b", tmp_path / "b")
    assert synced_keys == []
    assert any("could not determine the S3 key" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_local_name_mismatches_exact_match(tmp_path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "a.js").write_bytes(b"x")
    assert find_local_name_mismatches(tmp_path, "vendor/a.js") == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_local_name_mismatches_case(tmp_path):
    (tmp_path / "Vendor").mkdir()
    (tmp_path / "Vendor" / "A.js").write_bytes(b"x")
    mismatches = find_local_name_mismatches(tmp_path, "vendor/a.js")
    assert mismatches == [
        LocalNameMismatch(tmp_path, "Vendor", "vendor", "only in case"),
        LocalNameMismatch(tmp_path / "Vendor", "A.js", "a.js", "only in case"),
    ]
    assert str(mismatches[0]) == 'local name "Vendor" differs from S3 key "vendor" only in case'


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_local_name_mismatches_trailing_space(tmp_path):
    (tmp_path / "report.pdf").write_bytes(b"x")  # what Windows stores for a key ending in a space
    mismatches = find_local_name_mismatches(tmp_path, "report.pdf ")
    assert len(mismatches) == 1
    assert mismatches[0].local_name == "report.pdf"
    assert "trailing space or dot" in mismatches[0].difference


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_local_name_mismatches_trailing_space_is_fine_when_stored_exactly(tmp_path):
    # a file system that keeps trailing spaces (Linux/macOS) holds the key's name exactly - nothing to report
    with patch("bup.s3_backup.os.listdir", return_value=["report.pdf "]):
        assert find_local_name_mismatches(tmp_path, "report.pdf ") == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_local_name_mismatches_unicode_normalization(tmp_path):
    (tmp_path / "café.txt").write_bytes(b"x")  # decomposed (NFD) on disk
    mismatches = find_local_name_mismatches(tmp_path, "café.txt")  # composed (NFC) key
    assert len(mismatches) == 1
    assert mismatches[0].difference == "only in Unicode normalization"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_local_name_mismatches_nothing_similar(tmp_path):
    # nothing similarly named is not a mismatch - it's the normal state before a download (e.g. in a dry run)
    (tmp_path / "other.txt").write_bytes(b"x")
    assert find_local_name_mismatches(tmp_path, "missing.txt") == []
    assert find_local_name_mismatches(tmp_path, "no such dir/missing.txt") == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rename_local_to_match_key_directory_and_file(tmp_path):
    (tmp_path / "Vendor").mkdir()
    (tmp_path / "Vendor" / "A.js").write_bytes(b"x")
    (tmp_path / "Vendor" / "other.js").write_bytes(b"y")

    renames, failure = rename_local_to_match_key(tmp_path, "vendor/a.js")

    assert failure is None
    assert renames == [f'renamed "{tmp_path / "Vendor"}" to "vendor"', f'renamed "{tmp_path / "vendor" / "A.js"}" to "a.js"']
    assert os.listdir(tmp_path) == ["vendor"]
    assert sorted(os.listdir(tmp_path / "vendor")) == ["a.js", "other.js"]  # the sibling moved with the directory
    assert find_local_name_mismatches(tmp_path, "vendor/a.js") == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rename_local_to_match_key_nothing_to_do(tmp_path):
    (tmp_path / "a.js").write_bytes(b"x")
    assert rename_local_to_match_key(tmp_path, "a.js") == ([], None)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rename_local_to_match_key_rename_fails(tmp_path):
    (tmp_path / "A.js").write_bytes(b"x")
    with patch("bup.s3_backup.os.rename", side_effect=PermissionError("in use")):
        renames, failure = rename_local_to_match_key(tmp_path, "a.js")
    assert renames == []
    assert failure == f'could not rename "{tmp_path / "A.js"}" to "a.js" : in use'


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rename_local_to_match_key_name_the_file_system_will_not_store(tmp_path):
    # Windows strips a trailing space from the new name, so the rename is a no-op and the mismatch can't be fixed
    (tmp_path / "report.pdf").write_bytes(b"x")
    with patch("bup.s3_backup.os.rename"):
        renames, failure = rename_local_to_match_key(tmp_path, "report.pdf ")
    assert renames == []
    assert failure == f'the file system will not store the name "report.pdf " (renaming "{tmp_path / "report.pdf"}" to it had no effect)'


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_find_s3_objects_without_local_file(tmp_path):
    (tmp_path / "present.txt").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.txt").write_bytes(b"x")
    (tmp_path / "Case.txt").write_bytes(b"x")
    client = FakeS3Client(
        [
            {"Contents": [{"Key": "present.txt", "Size": 1}, {"Key": "sub/", "Size": 0}, {"Key": "sub/nested.txt", "Size": 1}]},
            {"Contents": [{"Key": "empty/", "Size": 0}, {"Key": "case.txt", "Size": 1}, {"Key": "gone.txt", "Size": 1}]},
            {},
        ]
    )
    folder_marker_keys, missing_keys = find_s3_objects_without_local_file(client, "my-bucket", tmp_path)
    assert folder_marker_keys == ["sub/", "empty/"]
    assert missing_keys == ["case.txt", "gone.txt"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.get_bucket_size", return_value=(1, 1))
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_downloaded_file_with_case_mismatch_is_renamed(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path):
    # the local copy exists under a different case, so sync (an exact match on the key) downloaded it again; bup renames it to the key
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    destination = tmp_path / "s3" / "my-bucket"
    (destination / "Vendor").mkdir(parents=True)
    (destination / "Vendor" / "a.js").write_bytes(b"x")
    (destination / "Vendor" / "b.js").write_bytes(b"x")
    infos = []
    warnings = []
    backup = _make_backup(info=infos.append, warning=warnings.append)

    # both files under the directory are downloaded; the first download's fix renames the directory, so the second needs nothing
    sync_stdout = f"download: s3://my-bucket/vendor/a.js to {destination}{os.sep}vendor{os.sep}a.js\n" f"download: s3://my-bucket/vendor/b.js to {destination}{os.sep}vendor{os.sep}b.js\n"
    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")):
        backup.run()

    assert warnings == []
    rename_infos = [i for i in infos if "renamed" in i]
    assert rename_infos == [f'my-bucket : renamed "{destination / "Vendor"}" to "vendor" to match the S3 key "vendor/a.js" so the next sync finds it already backed up']
    assert os.listdir(destination) == ["vendor"]
    assert find_local_name_mismatches(destination, "vendor/b.js") == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.get_bucket_size", return_value=(1, 1))
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_downloaded_file_whose_name_cannot_be_fixed_is_a_warning(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    destination = tmp_path / "s3" / "my-bucket"
    destination.mkdir(parents=True)
    (destination / "A.js").write_bytes(b"x")
    warnings = []
    backup = _make_backup(warning=warnings.append)

    sync_stdout = f"download: s3://my-bucket/a.js to {destination}{os.sep}a.js\n"
    with (
        patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")),
        patch("bup.s3_backup.os.rename", side_effect=PermissionError("in use")),
    ):
        backup.run()

    assert len(warnings) == 1
    assert '"a.js" will be downloaded on every run until the local name matches the S3 key exactly : could not rename' in warnings[0]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_dry_run_reports_a_case_mismatch_without_renaming(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    destination = tmp_path / "s3" / "my-bucket"
    destination.mkdir(parents=True)
    (destination / "A.js").write_bytes(b"x")
    warnings = []
    backup = _make_backup(warning=warnings.append)

    sync_stdout = f"(dryrun) download: s3://my-bucket/a.js to {destination}{os.sep}a.js\n"
    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")):
        backup.run()

    assert len(warnings) == 1
    assert '"a.js" is downloaded on every run : local name "A.js" differs from S3 key "a.js" only in case' in warnings[0]
    assert os.listdir(destination) == ["A.js"]  # a dry run changes nothing


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_dry_run_of_a_new_file_is_not_a_mismatch(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, tmp_path):
    # the file doesn't exist locally yet, which is exactly why it would be downloaded - no warning
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_exclusions.return_value.get_no_comments.return_value = []
    destination = tmp_path / "s3" / "my-bucket"
    warnings = []
    backup = _make_backup(warning=warnings.append)

    sync_stdout = f"(dryrun) download: s3://my-bucket/new/a.js to {destination}{os.sep}new{os.sep}a.js\n"
    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")):
        backup.run()

    assert warnings == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.get_bucket_size", return_value=(1, 3))
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_fewer_local_files_than_s3_objects_is_explained(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path, caplog):
    # S3: one real file (backed up), one folder marker (expected to be absent locally), one object whose local name differs in case
    # but that sync did not download this run (so its content isn't known to be current and it is reported, not renamed)
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_s3_access.return_value.client = FakeS3Client([{"Contents": [{"Key": "a.txt", "Size": 1}, {"Key": "folder/", "Size": 0}, {"Key": "folder/b.txt", "Size": 0}]}])
    mock_exclusions.return_value.get_no_comments.return_value = []
    destination = tmp_path / "s3" / "my-bucket"
    (destination / "Folder").mkdir(parents=True)
    (destination / "a.txt").write_bytes(b"x")
    (destination / "Folder" / "b.txt").write_bytes(b"")
    warnings = []
    backup = _make_backup(warning=warnings.append)

    with (
        patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, "", "")),
        caplog.at_level(logging.INFO, logger=__application_name__),
    ):
        backup.run()

    assert any("1 of the 1 S3 objects without a local file are zero-byte folder markers" in record.getMessage() and "folder/" in record.getMessage() for record in caplog.records)
    assert len(warnings) == 1
    assert 'S3 object "folder/b.txt" has no local file at exactly that path' in warnings[0]
    assert 'local name "Folder" differs from S3 key "folder" only in case' in warnings[0]
    assert os.listdir(destination / "Folder") == ["b.txt"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@patch("bup.s3_backup.get_bucket_size", return_value=(1, 2))
@patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli)
@patch("bup.s3_backup.ExclusionPreferences")
@patch("bup.s3_backup.S3Access")
@patch("bup.s3_backup.get_preferences")
def test_missing_local_file_with_nothing_similar_is_still_reported(mock_get_prefs, mock_s3_access, mock_exclusions, mock_find_aws_cli, mock_get_bucket_size, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
    mock_s3_access.return_value.client = FakeS3Client([{"Contents": [{"Key": "a.txt", "Size": 1}, {"Key": "gone.txt", "Size": 0}]}])
    mock_exclusions.return_value.get_no_comments.return_value = []
    destination = tmp_path / "s3" / "my-bucket"
    destination.mkdir(parents=True)
    (destination / "a.txt").write_bytes(b"x")
    warnings = []
    backup = _make_backup(warning=warnings.append)

    with patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, "", "")):
        backup.run()

    assert len(warnings) == 1
    assert 'S3 object "gone.txt" has no local file at exactly that path : no similarly named local file found' in warnings[0]
