"""
Tests for the S3 backup syncing each bucket with awsimple's S3Access.sync_to_directory().
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import logging
import os
from pathlib import Path

import boto3
import pytest
from awsimple import S3SyncObject, S3SyncOutcome
from botocore.exceptions import ClientError, NoCredentialsError

from bup import __application_name__
from bup.s3_backup import is_folder_marker, log_synced_object, max_keys_to_list

from .s3_sync_fakes import FakeS3, downloaded, make_preferences, make_s3_backup, make_sync_result, run_real_s3_backup, run_s3_backup


def _write_local_file(tmp_path: Path, bucket_name: str, relative_path: str, size: int):
    file_path = Path(tmp_path, "s3", bucket_name, relative_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x" * size)


def _up_to_date(key: str, size: int) -> S3SyncObject:
    return S3SyncObject(key, size, S3SyncOutcome.up_to_date)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_is_folder_marker():
    assert is_folder_marker(S3SyncObject("folder/", 0, S3SyncOutcome.skipped))
    assert not is_folder_marker(S3SyncObject("folder/a.txt", 0, S3SyncOutcome.skipped))


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_log_synced_object_logs_downloads_only(caplog):
    with caplog.at_level(logging.INFO, logger=__application_name__):
        log_synced_object("my-bucket", downloaded("folder/a.txt", 10))
        log_synced_object("my-bucket", S3SyncObject("b.txt", 20, S3SyncOutcome.would_download))
        log_synced_object("my-bucket", _up_to_date("c.txt", 30))
    messages = [record.getMessage() for record in caplog.records]
    assert messages == ["my-bucket : downloaded : folder/a.txt (10 bytes)", "my-bucket : would download : b.txt (20 bytes)"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_bucket_list_failure_surfaces_error(tmp_path):
    fake_s3 = FakeS3({})
    backup = make_s3_backup()

    def failing_s3_access(*args, **kwargs):
        s3_access = fake_s3(*args, **kwargs)
        s3_access.bucket_list.side_effect = NoCredentialsError()
        return s3_access

    run_s3_backup(tmp_path, failing_s3_access, backup=backup)

    assert len(backup.errors) == 1
    assert "could not list S3 buckets" in backup.errors[0]
    assert backup.error_count == 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_excluded_bucket_is_not_synced(tmp_path):
    fake_s3 = FakeS3({"excluded-bucket": make_sync_result([]), "backed-up-bucket": make_sync_result([])})

    backup = run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, dry_run=True), exclusions=["excluded-bucket"])

    assert list(fake_s3.bucket_accesses) == ["backed-up-bucket"]
    sync_call = fake_s3.bucket_accesses["backed-up-bucket"].sync_to_directory.call_args
    assert sync_call.args == (Path(tmp_path, "s3", "backed-up-bucket"),)
    assert sync_call.kwargs["dry_run"] is True
    assert sync_call.kwargs["size_only"] is False  # off by default
    assert "excluding excluded-bucket" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_size_only_preference_is_given_to_the_sync(tmp_path):
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])})

    run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_size_only=True))

    sync_kwargs = fake_s3.bucket_accesses["my-bucket"].sync_to_directory.call_args.kwargs
    assert sync_kwargs["size_only"] is True
    assert sync_kwargs["dry_run"] is False


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_bucket_is_accessed_in_its_own_region(tmp_path):
    # the preferences give one region, but a bucket can be in any region
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])}, bucket_region="eu-west-1")

    run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, aws_region="us-west-2"))

    assert fake_s3.bucket_access_kwargs["my-bucket"]["region_name"] == "eu-west-1"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_bucket_of_unknown_region_is_accessed_in_the_region_of_the_preferences(tmp_path):
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])})

    def s3_access_without_bucket_region(*args, **kwargs):
        s3_access = fake_s3(*args, **kwargs)
        s3_access.client.head_bucket.side_effect = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket")
        return s3_access

    run_s3_backup(tmp_path, s3_access_without_bucket_region, make_preferences(tmp_path, aws_region="us-west-2"))

    assert fake_s3.bucket_access_kwargs["my-bucket"]["region_name"] == "us-west-2"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_synced_file_count_in_summary(tmp_path, caplog):
    _write_local_file(tmp_path, "my-bucket", "a.txt", 10)
    _write_local_file(tmp_path, "my-bucket", "b.txt", 20)
    _write_local_file(tmp_path, "my-bucket", "c.txt", 30)
    fake_s3 = FakeS3({"my-bucket": make_sync_result([downloaded("a.txt", 10), downloaded("b.txt", 20), _up_to_date("c.txt", 30)])})

    with caplog.at_level(logging.INFO, logger=__application_name__):
        backup = run_s3_backup(tmp_path, fake_s3)

    assert "1 buckets, 1 backed up, 2 files synced, 0 excluded" in backup.infos
    assert backup.errors == []
    assert backup.warnings == []
    # the result of the verification only goes to the application log
    result_line = "my-bucket : match (synced=2, not_backed_up=0, failed=0, s3_count=3, local_count=3; s3_total_size=60, backed_up_size=60, local_size=60)"
    assert result_line in [record.getMessage() for record in caplog.records]
    assert result_line not in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_synced_file_count_in_dry_run_summary(tmp_path):
    sync_objects = [S3SyncObject("a.txt", 10, S3SyncOutcome.would_download), _up_to_date("b.txt", 20)]
    fake_s3 = FakeS3({"my-bucket": make_sync_result(sync_objects)})

    backup = run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, dry_run=True))

    assert "dry run my-bucket" in backup.infos
    assert "my-bucket : 1 files would be synced" in backup.infos
    assert "1 buckets, 1 dry run, 1 files would be synced, 0 excluded" in backup.infos
    assert backup.errors == []  # a dry run is not verified (b.txt has no local file here)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_failed_sync_surfaces_error_and_skips_verification(tmp_path):
    access_denied = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListObjectsV2")
    fake_s3 = FakeS3({"denied-bucket": access_denied, "my-bucket": make_sync_result([])})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("could not sync denied-bucket : ")
    # the backup goes on with the other buckets
    assert "2 buckets, 1 backed up, 0 files synced, 0 excluded" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_object_that_could_not_be_downloaded_is_an_error(tmp_path):
    _write_local_file(tmp_path, "my-bucket", "a.txt", 10)
    sync_objects = [downloaded("a.txt", 10), S3SyncObject("b.txt", 20, S3SyncOutcome.failed, reason="connection lost")]
    fake_s3 = FakeS3({"my-bucket": make_sync_result(sync_objects)})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert backup.errors == ['my-bucket : S3 object "b.txt" could not be backed up : connection lost']
    assert "1 buckets, 0 backed up, 1 files synced, 0 excluded" in backup.infos  # a bucket with a failure is not counted as backed up


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_folder_markers_only_go_to_the_log(tmp_path, caplog):
    _write_local_file(tmp_path, "my-bucket", "folder/a.txt", 10)
    sync_objects = [S3SyncObject("folder/", 0, S3SyncOutcome.skipped, reason='the key ends with "/" (a folder marker, not a file)'), _up_to_date("folder/a.txt", 10)]
    fake_s3 = FakeS3({"my-bucket": make_sync_result(sync_objects)})

    with caplog.at_level(logging.INFO, logger=__application_name__):
        backup = run_s3_backup(tmp_path, fake_s3)

    assert backup.warnings == []
    assert backup.errors == []
    assert any("1 S3 objects are folder markers" in record.getMessage() and "folder/" in record.getMessage() for record in caplog.records)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_object_the_sync_skips_is_a_warning_with_the_reason(tmp_path):
    reason = "storage class GLACIER has to be restored before it can be read"
    fake_s3 = FakeS3({"my-bucket": make_sync_result([S3SyncObject("archive.zip", 1000, S3SyncOutcome.skipped, reason=reason)])})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert backup.warnings == [f'my-bucket : S3 object "archive.zip" not backed up : {reason}']
    assert backup.errors == []  # it is reported as what it is, and is not also a verification error


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_only_the_first_objects_are_named(tmp_path):
    sync_objects = [S3SyncObject(f"{index}.zip", 1, S3SyncOutcome.skipped, reason="archived") for index in range(max_keys_to_list + 3)]
    fake_s3 = FakeS3({"my-bucket": make_sync_result(sync_objects)})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert len(backup.warnings) == max_keys_to_list + 1
    assert backup.warnings[-1] == "my-bucket : 3 more S3 objects not backed up"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_missing_local_files_surface_error(tmp_path):
    # the sync says the object is backed up, but the local backup does not have it
    fake_s3 = FakeS3({"my-bucket": make_sync_result([_up_to_date("a.txt", 100)])})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("my-bucket : not all files backed up (")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_request_reaches_the_sync_and_ends_the_backup(tmp_path):
    backup = make_s3_backup()
    _write_local_file(tmp_path, "first-bucket", "a.txt", 10)

    def stopped_sync(dest_dir, **kwargs):
        backup.request_stop()  # e.g. the user presses Stop during the sync
        assert kwargs["stop_event"].is_set()  # the backup's stop request is the event the sync was given
        return make_sync_result([downloaded("a.txt", 10), S3SyncObject("b.txt", 20, S3SyncOutcome.not_attempted)])

    fake_s3 = FakeS3({"first-bucket": stopped_sync, "second-bucket": make_sync_result([])})

    run_s3_backup(tmp_path, fake_s3, backup=backup)

    assert list(fake_s3.bucket_accesses) == ["first-bucket"]
    assert backup.errors == []  # what was not attempted is not a failure, and a stopped sync is not verified
    assert "2 buckets, 0 backed up, 1 files synced, 0 excluded" in backup.infos
    assert [(transfer_record.name, transfer_record.received_bytes) for transfer_record in backup.transfer_records] == [("first-bucket", 10)]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_sync_end_to_end_including_no_redownload(moto_s3_endpoint, tmp_path):
    """
    The real sync against a local S3 server: the first backup downloads every object (also those whose keys start with "/" or have
    "//" in them), a folder marker is not a file, and a second backup downloads nothing since the objects are already backed up.
    """
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="e2e-bucket")
    s3_client.put_object(Bucket="e2e-bucket", Key="plain.txt", Body=b"x" * 1000)
    s3_client.put_object(Bucket="e2e-bucket", Key="/temp/leading.txt", Body=b"x" * 2000)
    s3_client.put_object(Bucket="e2e-bucket", Key="folder//doubled.txt", Body=b"x" * 4000)
    s3_client.put_object(Bucket="e2e-bucket", Key="folder/sub folder/nested.txt", Body=b"x" * 8000)
    s3_client.put_object(Bucket="e2e-bucket", Key="empty folder/", Body=b"")

    backup = run_real_s3_backup(tmp_path)

    destination = tmp_path / "s3" / "e2e-bucket"
    local_files = [destination / "plain.txt", destination / "temp" / "leading.txt", destination / "folder" / "doubled.txt", destination / "folder" / "sub folder" / "nested.txt"]
    assert [local_file.stat().st_size for local_file in local_files] == [1000, 2000, 4000, 8000]
    assert not (destination / "empty folder").exists()
    assert backup.errors == []
    assert backup.warnings == []
    assert "1 buckets, 1 backed up, 4 files synced, 0 excluded" in backup.infos
    assert [(transfer_record.name, transfer_record.received_bytes, transfer_record.region) for transfer_record in backup.transfer_records] == [("e2e-bucket", 15000, "us-east-1")]

    modification_times = [local_file.stat().st_mtime_ns for local_file in local_files]

    second_backup = run_real_s3_backup(tmp_path)

    assert second_backup.errors == []
    assert second_backup.warnings == []
    assert "1 buckets, 1 backed up, 0 files synced, 0 excluded" in second_backup.infos
    assert second_backup.transfer_records == []
    # untouched files prove the sync didn't download them again
    assert [local_file.stat().st_mtime_ns for local_file in local_files] == modification_times


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.skipif(os.name != "nt", reason="file names that only differ in case are the same file on Windows")
def test_real_sync_does_not_download_a_file_again_whose_local_name_differs_in_case(moto_s3_endpoint, tmp_path):
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="case-bucket")
    s3_client.put_object(Bucket="case-bucket", Key="static/vendor/select2.js", Body=b"x" * 100)
    run_real_s3_backup(tmp_path)
    destination = tmp_path / "s3" / "case-bucket"
    os.rename(destination / "static" / "vendor", destination / "static" / "Vendor")  # e.g. the directory was made by an earlier backup

    backup = run_real_s3_backup(tmp_path)

    assert "1 buckets, 1 backed up, 0 files synced, 0 excluded" in backup.infos
    assert backup.warnings == []
    assert backup.errors == []
    assert os.listdir(destination / "static") == ["Vendor"]  # the local name is left as it is


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_dry_run_downloads_nothing(moto_s3_endpoint, tmp_path):
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="dry-run-bucket")
    s3_client.put_object(Bucket="dry-run-bucket", Key="folder/a.txt", Body=b"x" * 100)

    backup = run_real_s3_backup(tmp_path, dry_run=True)

    assert "dry-run-bucket : 1 files would be synced" in backup.infos
    assert backup.errors == []
    assert backup.transfer_records == []
    assert os.listdir(tmp_path / "s3" / "dry-run-bucket") == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("dry_run,s3_size_only", [(0, 1), (1, 0), (None, None)])
def test_bool_preferences_as_the_preferences_database_gives_them(tmp_path, dry_run, s3_size_only):
    # the preferences database gives a bool preference as an int (and None if it was never set), and awsimple checks the types of its arguments
    fake_s3 = FakeS3({"my-bucket": make_sync_result([])})

    backup = run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, dry_run=dry_run, s3_size_only=s3_size_only))

    sync_kwargs = fake_s3.bucket_accesses["my-bucket"].sync_to_directory.call_args.kwargs
    assert sync_kwargs["dry_run"] is bool(dry_run)
    assert sync_kwargs["size_only"] is bool(s3_size_only)
    assert backup.errors == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_backup_with_bool_preferences_as_the_preferences_database_gives_them(moto_s3_endpoint, tmp_path):
    # with the real awsimple, whose sync and verification check the types of their arguments
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="int-preferences-bucket")
    s3_client.put_object(Bucket="int-preferences-bucket", Key="a.txt", Body=b"x" * 100, ChecksumAlgorithm="CRC64NVME")

    dry_run_backup = run_real_s3_backup(tmp_path, dry_run=1, s3_size_only=0, s3_verify=1)
    assert dry_run_backup.errors == []
    assert "int-preferences-bucket : 1 files would be synced" in dry_run_backup.infos

    backup = run_real_s3_backup(tmp_path, dry_run=0, s3_size_only=1, s3_verify=1)
    assert backup.errors == []
    assert "1 buckets, 1 backed up, 1 files synced, 0 excluded" in backup.infos
    assert "verified 1 files in 1 buckets against S3, 0 differ" in backup.infos
