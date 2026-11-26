"""
Tests for the optional fix of the modification times that the verification of the S3 backup finds to differ: a local file that has
the contents of its S3 object gets the modification time of the S3 object, where the contents are compared by the hash S3 has, or
with a download of the object when S3 has no hash of it. The download goes to a temporary directory in the backup directory, and is
deleted once it has been compared.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import hashlib
import os
import sys
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import boto3
import pytest
from awsimple import AWSimpleException, S3SyncObject, S3SyncOutcome, S3VerifyObject, S3VerifyOutcome
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError

from bup import arguments
from bup.cli.cli_main import cli_main
from bup.gui.preferences_widget import PreferencesWidget
from bup import s3_mtime_fix
from bup.s3_mtime_fix import MtimeFix, MtimeFixOutcome, fix_local_mtime, temp_dir_name

from .s3_sync_fakes import FakeS3, make_preferences, make_s3_backup, make_sync_result, make_verify_result, run_real_s3_backup, run_s3_backup

mtime_offset = 25198.0  # seconds a local file is newer than its S3 object, which a sync leaves alone
mtime_reason = "the local file was modified +25198 seconds from the S3 object (2026-11-20T12:00:00+00:00)"


def _put_objects(endpoint_url: str, bucket_name: str, contents: dict, with_hash: bool):
    """
    Make a bucket with the given objects (contents by key), written with a checksum of the whole object or with none at all.
    """
    # boto3 writes an object with a checksum unless it is told to only do so when S3 requires one
    s3_client = boto3.client("s3", endpoint_url=endpoint_url, config=Config(request_checksum_calculation="when_supported" if with_hash else "when_required"))
    s3_client.create_bucket(Bucket=bucket_name)
    for key, body in contents.items():
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=body)


def _get_s3_mtime(endpoint_url: str, bucket_name: str, key: str) -> float:
    return boto3.client("s3", endpoint_url=endpoint_url).head_object(Bucket=bucket_name, Key=key)["LastModified"].timestamp()


def _offset_mtime(local_path: Path) -> float:
    """
    Make a local file newer than it is.
    :return: the modification time it now has
    """
    mtime = local_path.stat().st_mtime + mtime_offset
    os.utime(local_path, (mtime, mtime))
    return mtime


def _run_fake_backup_with_mtimes_that_differ(tmp_path: Path, keys: List[str], bucket_names: tuple = ("my-bucket",), backup=None):
    """
    Run an S3 backup with the verification and the fix on, whose (faked) verification of "my-bucket" finds the local files of
    the given keys to have another modification time. The other buckets are empty.
    :return: (the backup, the fake S3)
    """
    bucket_directory = Path(tmp_path, "s3", "my-bucket")
    bucket_directory.mkdir(parents=True)
    for key in keys:
        Path(bucket_directory, key).write_bytes(b"x" * 10)
    sync_results = {bucket_name: make_sync_result([]) for bucket_name in bucket_names}
    sync_results["my-bucket"] = make_sync_result([S3SyncObject(key, 10, S3SyncOutcome.up_to_date) for key in keys])
    fake_s3 = FakeS3(sync_results)
    fake_s3.verify_results["my-bucket"] = make_verify_result([S3VerifyObject(key, S3VerifyOutcome.mtime_differs, Path(bucket_directory, key), mtime_reason) for key in keys])
    return run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_verify=True, s3_fix_mtime=True), backup=backup), fake_s3


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_file_with_the_hash_of_its_s3_object_gets_its_modification_time(moto_s3_endpoint, tmp_path):
    _put_objects(moto_s3_endpoint, "hash-bucket", {"a.txt": b"x" * 1000}, with_hash=True)
    run_real_s3_backup(tmp_path)
    local_path = tmp_path / "s3" / "hash-bucket" / "a.txt"
    _offset_mtime(local_path)

    backup = run_real_s3_backup(tmp_path, s3_verify=True, s3_fix_mtime=True)

    assert backup.errors == []
    assert backup.warnings == []
    assert local_path.stat().st_mtime == pytest.approx(_get_s3_mtime(moto_s3_endpoint, "hash-bucket", "a.txt"), abs=1.0)
    assert local_path.read_bytes() == b"x" * 1000
    assert "hash-bucket : fixed the modification time of 1 of 1 files that have a different modification time (0 after a download to compare, since S3 has no hash of them)" in backup.infos
    # the object was not downloaded: S3 has a hash of it
    assert [(record.name, record.received_bytes) for record in backup.transfer_records] == [("hash-bucket", 0), ("hash-bucket (verification)", 0)]

    # and the next verification finds nothing
    second_backup = run_real_s3_backup(tmp_path, s3_verify=True, s3_fix_mtime=True)
    assert second_backup.warnings == []
    assert "hash-bucket : verified 1 of 1 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in second_backup.infos
    assert not any("fixed the modification time" in info for info in second_backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_file_without_a_hash_in_s3_is_compared_with_a_download_and_gets_the_modification_time(moto_s3_endpoint, tmp_path):
    _put_objects(moto_s3_endpoint, "no-hash-bucket", {"folder/a.txt": b"x" * 1000}, with_hash=False)
    run_real_s3_backup(tmp_path)
    local_path = tmp_path / "s3" / "no-hash-bucket" / "folder" / "a.txt"
    _offset_mtime(local_path)

    hashed_paths = []
    real_get_file_hash = s3_mtime_fix.get_file_hash

    def get_file_hash(hashed_path):
        hashed_paths.append(hashed_path)
        return real_get_file_hash(hashed_path)

    with patch("bup.s3_mtime_fix.get_file_hash", get_file_hash):
        backup = run_real_s3_backup(tmp_path, s3_verify=True, s3_fix_mtime=True)

    assert backup.errors == []
    assert backup.warnings == []
    assert "no-hash-bucket : verified 1 of 1 files against S3 : 0 differ, 1 have a different modification time, 1 have no hash in S3 (size and modification time only)" in backup.infos
    # the local file was compared with a download in the temporary directory of the backup directory (so on the backup drive), which is gone again
    temp_dir = tmp_path / temp_dir_name
    local_hashed_path, download_hashed_path = hashed_paths
    assert local_hashed_path == local_path
    assert download_hashed_path.is_relative_to(temp_dir)
    assert not temp_dir.exists()
    assert local_path.stat().st_mtime == pytest.approx(_get_s3_mtime(moto_s3_endpoint, "no-hash-bucket", "folder/a.txt"), abs=1.0)
    assert "no-hash-bucket : fixed the modification time of 1 of 1 files that have a different modification time (1 after a download to compare, since S3 has no hash of them)" in backup.infos
    # the download is what the verification received
    assert [(record.name, record.received_bytes) for record in backup.transfer_records] == [("no-hash-bucket", 0), ("no-hash-bucket (verification)", 1000)]
    assert [path.name for path in (tmp_path / "s3" / "no-hash-bucket").rglob("*") if path.is_file()] == ["a.txt"]  # the download is not in the backup


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_file_without_a_hash_in_s3_that_is_not_the_download_is_an_error_and_is_left_as_it_is(moto_s3_endpoint, tmp_path):
    _put_objects(moto_s3_endpoint, "no-hash-bucket", {"a.txt": b"x" * 1000}, with_hash=False)
    run_real_s3_backup(tmp_path)
    local_path = tmp_path / "s3" / "no-hash-bucket" / "a.txt"
    local_path.write_bytes(b"z" * 1000)  # other contents of the same size, which the size and the modification time do not show
    mtime = _offset_mtime(local_path)

    backup = run_real_s3_backup(tmp_path, s3_verify=True, s3_fix_mtime=True)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith('no-hash-bucket : "a.txt" is not a copy of the S3 object : the sha512 of the local file is ')
    assert backup.errors[0].endswith(f"but that of the S3 object, which was downloaded to compare, is {hashlib.sha512(b'x' * 1000).hexdigest()}")
    assert backup.warnings == []  # an error, not also a warning
    assert local_path.stat().st_mtime == mtime
    assert local_path.read_bytes() == b"z" * 1000
    assert not (tmp_path / temp_dir_name).exists()  # the download is deleted, also when it is not what the local file is
    assert "no-hash-bucket : verified 1 of 1 files against S3 : 1 differ, 0 have a different modification time, 1 have no hash in S3 (size and modification time only)" in backup.infos
    assert "no-hash-bucket : fixed the modification time of 0 of 1 files that have a different modification time (0 after a download to compare, since S3 has no hash of them)" in backup.infos
    assert "verified 1 files in 1 buckets against S3, 1 differ" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_modification_time_is_not_fixed_unless_the_preference_is_set(moto_s3_endpoint, tmp_path):
    _put_objects(moto_s3_endpoint, "hash-bucket", {"a.txt": b"x" * 1000}, with_hash=True)
    run_real_s3_backup(tmp_path)
    local_path = tmp_path / "s3" / "hash-bucket" / "a.txt"
    mtime = _offset_mtime(local_path)

    backup = run_real_s3_backup(tmp_path, s3_verify=True)

    assert len(backup.warnings) == 1
    assert local_path.stat().st_mtime == mtime
    assert not any("fixed the modification time" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_modification_time_that_could_not_be_fixed_is_an_error(tmp_path):
    with patch("bup.s3_backup.fix_local_mtime", side_effect=lambda access, key, local_path, temp_dir: MtimeFix(key, MtimeFixOutcome.failed, "no such object")):
        backup, _unused_fake_s3 = _run_fake_backup_with_mtimes_that_differ(tmp_path, ["a.txt"])

    # S3 answers (the fake's head_bucket), so the file failed for a reason of its own
    assert backup.errors == ['my-bucket : "a.txt" : the modification time could not be fixed : no such object']
    assert backup.warnings == []
    assert "my-bucket : fixed the modification time of 0 of 1 files that have a different modification time (0 after a download to compare, since S3 has no hash of them)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fix_ends_when_s3_can_not_be_reached(tmp_path):
    connection_error = EndpointConnectionError(endpoint_url="https://my-bucket.s3.amazonaws.com/")

    def unreachable_fix(access, key, local_path, temp_dir):
        access.client.head_bucket.side_effect = connection_error  # from here on S3 does not answer
        return MtimeFix(key, MtimeFixOutcome.failed, str(connection_error))

    with patch("bup.s3_backup.fix_local_mtime", side_effect=unreachable_fix) as mock_fix:
        backup, fake_s3 = _run_fake_backup_with_mtimes_that_differ(tmp_path, ["a.txt", "b.txt"], bucket_names=("my-bucket", "other-bucket"))

    assert mock_fix.call_count == 1  # the fix of the second file is not attempted
    assert backup.errors == [f"my-bucket : S3 could not be reached while fixing modification times, which ended there : {connection_error}"]
    assert len(backup.warnings) == 2  # the files are as they were, which is what the verification found
    fake_s3.bucket_accesses["other-bucket"].verify_directory.assert_not_called()
    assert any(info.endswith("(S3 could not be reached, so the verification ended : 1 more buckets were not verified)") for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fix_ends_when_the_backup_is_stopped(tmp_path):
    backup = make_s3_backup()

    def stopping_fix(access, key, local_path, temp_dir):
        backup.request_stop()  # e.g. Stop is pressed during the fix of the first file
        return MtimeFix(key, MtimeFixOutcome.fixed, old_mtime=2.0, new_mtime=1.0)

    with patch("bup.s3_backup.fix_local_mtime", side_effect=stopping_fix) as mock_fix:
        _run_fake_backup_with_mtimes_that_differ(tmp_path, ["a.txt", "b.txt"], backup=backup)

    assert mock_fix.call_count == 1
    assert backup.errors == []
    assert backup.warnings == [f'my-bucket : "b.txt" has the contents of the S3 object, but {mtime_reason}']  # not fixed
    assert "my-bucket : fixed the modification time of 1 of 2 files that have a different modification time (0 after a download to compare, since S3 has no hash of them)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fix_local_mtime_leaves_a_file_of_another_size(tmp_path):
    local_path = tmp_path / "a.txt"
    local_path.write_bytes(b"x" * 10)
    mtime = local_path.stat().st_mtime
    access = MagicMock()
    access.get_s3_object_metadata.return_value.size = 11

    fix = fix_local_mtime(access, "a.txt", local_path, tmp_path / temp_dir_name)

    assert fix == MtimeFix("a.txt", MtimeFixOutcome.differs, "the local file is 10 bytes but the S3 object is 11 bytes")
    access.download.assert_not_called()
    assert local_path.stat().st_mtime == mtime


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("failure", [AWSimpleException("bucket_name='b' s3_key='a.txt' does not exist"), OSError("no space left on device")])
def test_fix_local_mtime_reports_a_failure_and_does_not_raise(tmp_path, failure):
    local_path = tmp_path / "a.txt"
    local_path.write_bytes(b"x" * 10)
    access = MagicMock()
    access.get_s3_object_metadata.side_effect = failure

    assert fix_local_mtime(access, "a.txt", local_path, tmp_path / temp_dir_name) == MtimeFix("a.txt", MtimeFixOutcome.failed, str(failure))


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fix_local_mtime_deletes_a_download_that_failed_part_way(tmp_path):
    local_path = tmp_path / "a.txt"
    local_path.write_bytes(b"x" * 10)
    mtime = local_path.stat().st_mtime
    temp_dir = tmp_path / temp_dir_name
    download_paths = []

    def download(key, download_path, s3_object_metadata):
        download_paths.append(download_path)
        download_path.write_bytes(b"x" * 4)  # what was received before the connection dropped
        raise AWSimpleException("couldn't download b/a.txt after 3 attempts")

    access = MagicMock()
    access.get_s3_object_metadata.return_value = MagicMock(size=10, sha512=None, checksums={})
    access.get_s3_object_metadata.return_value.get_content_sha512.return_value = None  # S3 has no hash of this object
    access.download.side_effect = download

    fix = fix_local_mtime(access, "a.txt", local_path, temp_dir)

    assert fix == MtimeFix("a.txt", MtimeFixOutcome.failed, "couldn't download b/a.txt after 3 attempts")
    assert len(download_paths) == 1 and download_paths[0].is_relative_to(temp_dir)
    assert not download_paths[0].exists()
    assert list(temp_dir.iterdir()) == []
    assert local_path.stat().st_mtime == mtime


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_download_left_by_a_run_that_was_cut_short_is_removed(tmp_path):
    leftover = tmp_path / temp_dir_name / "tmp_of_an_earlier_run" / "s3_object"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"x" * 1000)

    with patch("bup.s3_backup.fix_local_mtime", side_effect=lambda access, key, local_path, temp_dir: MtimeFix(key, MtimeFixOutcome.fixed, old_mtime=2.0, new_mtime=1.0)):
        backup, _unused_fake_s3 = _run_fake_backup_with_mtimes_that_differ(tmp_path, ["a.txt"])

    assert backup.errors == []
    assert not (tmp_path / temp_dir_name).exists()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_temporary_directory_that_can_not_be_removed_is_an_error(tmp_path):
    with (
        patch("bup.s3_backup.fix_local_mtime", side_effect=lambda access, key, local_path, temp_dir: MtimeFix(key, MtimeFixOutcome.fixed, old_mtime=2.0, new_mtime=1.0)),
        patch("bup.s3_backup.remove_temp_dir", side_effect=[None, PermissionError("access is denied")]),  # before the first file, and after the last
    ):
        backup, _unused_fake_s3 = _run_fake_backup_with_mtimes_that_differ(tmp_path, ["a.txt"])

    assert backup.errors == [f'could not remove the temporary directory "{tmp_path / temp_dir_name}" of the downloads that fix modification times : access is denied']


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fix_mtime_command_line_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bup", "backup_dir", "-s", "--verify", "--fix_mtime"])
    assert arguments().fix_mtime is True

    monkeypatch.setattr(sys, "argv", ["bup", "backup_dir", "-s", "--verify"])
    assert arguments().fix_mtime is False


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("fix_mtime", [True, False])
def test_fix_mtime_argument_is_written_to_the_preferences(fix_mtime):
    preferences = MagicMock(detailed_log_directory=None, detailed_log_file_size_limit_mb=None)
    args = MagicMock(
        path="backup_dir",
        token=None,
        profile=None,
        region=None,
        dry_run=False,
        size_only=False,
        verify=True,
        fix_mtime=fix_mtime,
        exclude=None,
        s3=False,
        dynamodb=False,
        github=False,
        aws=False,
    )

    with patch("bup.cli.cli_main.get_preferences", return_value=preferences), patch("bup.cli.cli_main.Balsa"), patch("bup.cli.cli_main.set_detailed_file_logging"):
        cli_main(args)

    assert preferences.s3_fix_mtime is fix_mtime


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fix_mtime_check_box_loads_and_saves_the_preference(qapp):
    preferences = MagicMock(
        backup_directory="backup_dir",
        aws_profile=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_region=None,
        github_token=None,
        detailed_log_directory=None,
        detailed_log_file_size_limit_mb=None,
        verbose=False,
        dry_run=False,
        s3_size_only=False,
        s3_verify=True,
        s3_fix_mtime=True,
        automatic_backup=False,
        backup_period=None,
    )
    with patch("bup.gui.preferences_widget.get_gui_preferences", return_value=preferences), patch("bup.gui.preferences_widget.set_detailed_file_logging"):
        preferences_widget = PreferencesWidget()
        assert preferences_widget.s3_fix_mtime_check_box.isChecked()

        preferences_widget.s3_fix_mtime_check_box.click()

    assert not preferences_widget.s3_fix_mtime_check_box.isChecked()
    assert preferences.s3_fix_mtime is False
