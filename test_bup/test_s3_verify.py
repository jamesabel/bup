"""
Tests for the optional verification of every local file of the S3 backup against the metadata of its S3 object. The verification
itself is awsimple's S3Access.verify_directory() (which has its own tests): these are of when bup verifies, what it reports, and the
preference that turns it on.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import os
import sys
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import boto3
import pytest
from awsimple import S3SyncObject, S3SyncOutcome, S3VerifyObject, S3VerifyOutcome

from bup import arguments
from bup.cli.cli_main import cli_main
from bup.gui.preferences_widget import PreferencesWidget
from bup.s3_backup import max_keys_to_list

from .s3_sync_fakes import FakeS3, downloaded, make_preferences, make_s3_backup, make_sync_result, make_verify_result, run_real_s3_backup, run_s3_backup, verified


def _up_to_date(key: str, size: int = 10) -> S3SyncObject:
    return S3SyncObject(key, size, S3SyncOutcome.up_to_date)


def _run_verified_backup(tmp_path: Path, sync_objects: List[S3SyncObject], verify_objects: List[S3VerifyObject], **preferences):
    """
    Run an S3 backup of "my-bucket" with the verification on, whose (faked) sync and verification have the given objects.
    :return: (the backup, the fake S3)
    """
    for sync_object in sync_objects:
        if sync_object.outcome in (S3SyncOutcome.downloaded, S3SyncOutcome.up_to_date):
            local_path = Path(tmp_path, "s3", "my-bucket", sync_object.key)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(b"x" * sync_object.size)  # so that the check of the bucket's size finds everything
    fake_s3 = FakeS3({"my-bucket": make_sync_result(sync_objects)})
    fake_s3.verify_results["my-bucket"] = make_verify_result(verify_objects)
    return run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_verify=True, **preferences)), fake_s3


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_is_not_verified_against_s3_unless_the_preference_is_set(tmp_path):
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    Path(tmp_path, "s3", "my-bucket", "a.txt").write_bytes(b"x" * 10)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([downloaded("a.txt", 10)])})

    backup = run_s3_backup(tmp_path, fake_s3)

    fake_s3.bucket_accesses["my-bucket"].verify_directory.assert_not_called()
    assert not any("verif" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_every_bucket_is_verified_after_the_backup_with_the_result_of_its_sync(tmp_path):
    sync_objects = [downloaded("new.txt", 10), _up_to_date("folder/old.txt"), S3SyncObject("folder/", 0, S3SyncOutcome.skipped, reason="a folder marker")]
    verify_objects = [verified("new.txt"), verified("folder/old.txt"), S3VerifyObject("folder/", S3VerifyOutcome.skipped, reason="sync outcome is skipped : a folder marker")]

    backup, fake_s3 = _run_verified_backup(tmp_path, sync_objects, verify_objects)

    # awsimple verifies what the sync says is local, without listing the bucket again, and stops when the backup is stopped
    verify_call = fake_s3.bucket_accesses["my-bucket"].verify_directory.call_args
    assert verify_call.args == (Path(tmp_path, "s3", "my-bucket"),)
    assert verify_call.kwargs["sync_result"] is fake_s3.sync_results["my-bucket"]
    assert not verify_call.kwargs["stop_event"].is_set()  # the verification's own stop event (see test_s3_verify_unreachable.py)
    assert backup.errors == []
    assert backup.warnings == []
    summary_index = backup.infos.index("1 buckets, 1 backed up, 1 files synced, 0 excluded")
    assert backup.infos[summary_index + 1 : summary_index + 4] == [
        "verifying 1 buckets against S3 (this makes a request to S3 for every object, and reads every local file)",
        "my-bucket : verified 2 of 2 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)",
        "verified 2 files in 1 buckets against S3, 0 differ",
    ]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_local_file_that_is_not_a_copy_is_an_error(tmp_path):
    reason = "the SHA-512 of the local file is 11 but the S3 object's is 22"
    verify_objects = [verified("good.txt"), S3VerifyObject("damaged.txt", S3VerifyOutcome.differs, reason=reason)]

    backup, _unused_fake_s3 = _run_verified_backup(tmp_path, [_up_to_date("good.txt"), _up_to_date("damaged.txt")], verify_objects)

    assert backup.errors == [f'my-bucket : "damaged.txt" is not a copy of the S3 object : {reason}']
    assert backup.error_count == 1
    assert "my-bucket : verified 2 of 2 files against S3 : 1 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos
    assert "verified 2 files in 1 buckets against S3, 1 differ" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_mtime_that_differs_is_a_warning(tmp_path):
    reason = "the local file was modified +3600 seconds from the S3 object (2026-11-20T12:00:00+00:00)"
    verify_objects = [S3VerifyObject("a.txt", S3VerifyOutcome.mtime_differs, reason=reason, hash_name="SHA-512")]

    backup, _unused_fake_s3 = _run_verified_backup(tmp_path, [_up_to_date("a.txt")], verify_objects)

    assert backup.errors == []
    assert backup.warnings == [f'my-bucket : "a.txt" has the contents of the S3 object, but {reason}']
    assert "my-bucket : verified 1 of 1 files against S3 : 0 differ, 1 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_file_that_could_not_be_verified_is_an_error(tmp_path):
    reason = "could not get the metadata of the S3 object (403 Forbidden)"
    verify_objects = [verified("a.txt"), S3VerifyObject("b.txt", S3VerifyOutcome.failed, reason=reason)]

    backup, _unused_fake_s3 = _run_verified_backup(tmp_path, [_up_to_date("a.txt"), _up_to_date("b.txt")], verify_objects)

    assert backup.errors == [f'my-bucket : "b.txt" could not be verified : {reason}']
    assert (
        "my-bucket : verified 2 of 2 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only), 1 could not be verified"
        in backup.infos
    )
    assert "verified 2 files in 1 buckets against S3, 0 differ, 1 could not be verified" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_objects_without_a_hash_in_s3_are_counted(tmp_path):
    # S3 has no hash of the whole contents of these, so awsimple verified them by size and modification time (no hash name)
    verify_objects = [verified("a.txt"), verified("b.txt", hash_name=None), S3VerifyObject("c.txt", S3VerifyOutcome.mtime_differs, reason="the local file was modified +60 seconds")]

    backup, _unused_fake_s3 = _run_verified_backup(tmp_path, [_up_to_date("a.txt"), _up_to_date("b.txt"), _up_to_date("c.txt")], verify_objects)

    assert backup.errors == []
    assert "my-bucket : verified 3 of 3 files against S3 : 0 differ, 1 have a different modification time, 2 have no hash in S3 (size and modification time only)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_only_the_first_files_that_differ_are_named(tmp_path):
    keys = [f"{index}.txt" for index in range(max_keys_to_list + 2)]
    verify_objects = [S3VerifyObject(key, S3VerifyOutcome.differs, reason="the local file is 1 bytes but the S3 object is 2 bytes") for key in keys]

    backup, _unused_fake_s3 = _run_verified_backup(tmp_path, [_up_to_date(key) for key in keys], verify_objects)

    assert len(backup.errors) == max_keys_to_list + 1
    assert backup.errors[-1] == "my-bucket : 2 more local files are not a copy of their S3 object"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dry_run_is_not_verified(tmp_path):
    backup, fake_s3 = _run_verified_backup(tmp_path, [S3SyncObject("a.txt", 10, S3SyncOutcome.would_download)], [], dry_run=True)

    fake_s3.bucket_accesses["my-bucket"].verify_directory.assert_not_called()
    assert not any("verif" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_verification_that_was_stopped_says_so(tmp_path):
    # awsimple did not attempt the files whose verification had not started when the stop was requested
    backup = make_s3_backup()
    Path(tmp_path, "s3", "my-bucket").mkdir(parents=True)
    for name in ("a.txt", "b.txt"):
        Path(tmp_path, "s3", "my-bucket", name).write_bytes(b"x" * 10)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([_up_to_date("a.txt"), _up_to_date("b.txt")]), "other-bucket": make_sync_result([])})

    def stopped_verify_directory(bucket_name, sync_result):
        backup.request_stop()  # e.g. Stop is pressed during the verification of the first bucket
        return make_verify_result([verified("a.txt"), S3VerifyObject("b.txt", S3VerifyOutcome.not_attempted)])

    fake_s3.verify_directory = stopped_verify_directory

    run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_verify=True), backup=backup)

    fake_s3.bucket_accesses["other-bucket"].verify_directory.assert_not_called()  # the second bucket is not verified
    assert "my-bucket : verified 1 of 2 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos
    assert "verified 1 files in 1 buckets against S3, 0 differ (stopped before all files were verified)" in backup.infos
    assert backup.errors == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_backup_is_verified_and_a_damaged_file_is_found(moto_s3_endpoint, tmp_path):
    """
    The real sync and verification (awsimple's) against a local S3 server: what was just backed up verifies with a hash from S3,
    and a local file that is then damaged (with the size and the modification time it had, so that a sync sees nothing) is an error.
    """
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="verify-bucket")
    s3_client.put_object(Bucket="verify-bucket", Key="plain.txt", Body=b"x" * 1000, ChecksumAlgorithm="CRC64NVME")
    s3_client.put_object(Bucket="verify-bucket", Key="/folder//nested.txt", Body=b"y" * 2000, ChecksumAlgorithm="SHA256")

    backup = run_real_s3_backup(tmp_path, s3_verify=True)

    assert backup.errors == []
    assert backup.warnings == []
    assert "verify-bucket : verified 2 of 2 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos

    nested_file = tmp_path / "s3" / "verify-bucket" / "folder" / "nested.txt"
    nested_stat = nested_file.stat()
    nested_file.write_bytes(b"z" * 2000)
    os.utime(nested_file, (nested_stat.st_mtime, nested_stat.st_mtime))

    second_backup = run_real_s3_backup(tmp_path, s3_verify=True)

    assert "1 buckets, 1 backed up, 0 files synced, 0 excluded" in second_backup.infos  # the sync sees a current file
    assert len(second_backup.errors) == 1
    assert second_backup.errors[0].startswith('verify-bucket : "/folder//nested.txt" is not a copy of the S3 object : the SHA-256 of the local file is ')
    assert "verified 2 files in 1 buckets against S3, 1 differ" in second_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_verification_takes_modification_times_within_ten_seconds_as_the_same(moto_s3_endpoint, tmp_path):
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="mtime-bucket")
    for name in ("in_window.txt", "outside.txt"):
        s3_client.put_object(Bucket="mtime-bucket", Key=name, Body=b"x" * 100, ChecksumAlgorithm="CRC64NVME")
    run_real_s3_backup(tmp_path)
    # local files that are newer than their S3 objects, which a sync leaves alone
    for name, seconds in (("in_window.txt", 8.0), ("outside.txt", 60.0)):
        local_path = tmp_path / "s3" / "mtime-bucket" / name
        mtime = local_path.stat().st_mtime + seconds
        os.utime(local_path, (mtime, mtime))

    backup = run_real_s3_backup(tmp_path, s3_verify=True)

    assert backup.errors == []
    assert len(backup.warnings) == 1
    assert backup.warnings[0].startswith('mtime-bucket : "outside.txt" has the contents of the S3 object, but the local file was modified +60 seconds from the S3 object (')
    assert "mtime-bucket : verified 2 of 2 files against S3 : 0 differ, 1 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_verify_command_line_argument(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bup", "backup_dir", "-s", "--verify"])
    assert arguments().verify is True

    monkeypatch.setattr(sys, "argv", ["bup", "backup_dir", "-s"])
    assert arguments().verify is False


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("verify", [True, False])
def test_verify_argument_is_written_to_the_preferences(verify):
    preferences = MagicMock(detailed_log_directory=None, detailed_log_file_size_limit_mb=None)
    args = MagicMock(path="backup_dir", token=None, profile=None, region=None, dry_run=False, size_only=False, verify=verify, exclude=None, s3=False, dynamodb=False, github=False, aws=False)

    with patch("bup.cli.cli_main.get_preferences", return_value=preferences), patch("bup.cli.cli_main.Balsa"), patch("bup.cli.cli_main.set_detailed_file_logging"):
        cli_main(args)

    assert preferences.s3_verify is verify


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_verify_check_box_loads_and_saves_the_preference(qapp):
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
        automatic_backup=False,
        backup_period=None,
    )
    with patch("bup.gui.preferences_widget.get_gui_preferences", return_value=preferences), patch("bup.gui.preferences_widget.set_detailed_file_logging"):
        preferences_widget = PreferencesWidget()
        assert preferences_widget.s3_verify_check_box.isChecked()

        preferences_widget.s3_verify_check_box.click()

    assert not preferences_widget.s3_verify_check_box.isChecked()
    assert preferences.s3_verify is False
