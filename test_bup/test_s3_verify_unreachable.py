"""
Tests for the optional verification of the S3 backup when S3 can no longer be reached part way through it (e.g. the internet
connection drops): the verification ends there with one error that says so, and not with an error for every file that is left.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import re
import threading
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import boto3
from awsimple import S3SyncObject, S3SyncOutcome, S3VerifyObject, S3VerifyOutcome
from botocore.client import BaseClient
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from bup.s3_backup import S3Backup, get_s3_unreachable_reason, verify_failures_before_reachability_check

from .s3_sync_fakes import FakeS3, make_preferences, make_s3_backup, make_sync_result, make_verify_result, run_real_s3_backup, run_s3_backup, verified

metadata_failure = "could not get the metadata of the S3 object (Could not connect to the endpoint URL)"


def _no_connectivity() -> EndpointConnectionError:
    return EndpointConnectionError(endpoint_url="https://s3.invalid/")


def _failed(key: str) -> S3VerifyObject:
    return S3VerifyObject(key, S3VerifyOutcome.failed, reason=metadata_failure)


def _run_verified_backup(tmp_path: Path, verify_objects: Dict[str, List[S3VerifyObject]], reachable: bool, backup: S3Backup = None):
    """
    Run an S3 backup with the verification on, of buckets whose objects are all up to date and whose (faked) verification has the
    given objects.
    :param verify_objects: the objects of the verification of each bucket, by bucket name
    :param reachable: False if S3 does not answer when the backup checks that it can be reached
    :return: (the backup, the fake S3)
    """
    sync_results = {}
    for bucket_name, bucket_verify_objects in verify_objects.items():
        Path(tmp_path, "s3", bucket_name).mkdir(parents=True)
        for verify_object in bucket_verify_objects:
            Path(tmp_path, "s3", bucket_name, verify_object.key).write_bytes(b"x" * 10)  # so that the check of the bucket's size finds everything
        sync_results[bucket_name] = make_sync_result([S3SyncObject(verify_object.key, 10, S3SyncOutcome.up_to_date) for verify_object in bucket_verify_objects])
    fake_s3 = FakeS3(sync_results)
    for bucket_name, bucket_verify_objects in verify_objects.items():
        fake_s3.verify_results[bucket_name] = make_verify_result(bucket_verify_objects)

    def s3_access(*args, **kwargs):
        access = fake_s3(*args, **kwargs)
        if args:
            # the access of a bucket: S3 is reached for the sync and its check, and (if not reachable) no longer once the verification has started
            real_verify_directory = access.verify_directory.side_effect

            def verify_directory(*verify_args, **verify_kwargs):
                if not reachable:
                    access.client.head_bucket.side_effect = _no_connectivity()
                return real_verify_directory(*verify_args, **verify_kwargs)

            access.verify_directory.side_effect = verify_directory
        return access

    return run_s3_backup(tmp_path, s3_access, make_preferences(tmp_path, s3_verify=True), backup=backup), fake_s3


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_s3_unreachable_reason():
    s3_client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")

    with patch.object(BaseClient, "_make_api_call", return_value={}):
        assert get_s3_unreachable_reason(s3_client, "my-bucket") is None
    # access denied is an answer from S3
    with patch.object(BaseClient, "_make_api_call", side_effect=ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket")):
        assert get_s3_unreachable_reason(s3_client, "my-bucket") is None
    with patch.object(BaseClient, "_make_api_call", side_effect=_no_connectivity()):
        assert get_s3_unreachable_reason(s3_client, "my-bucket") == 'Could not connect to the endpoint URL: "https://s3.invalid/"'
    # nothing can be asked of S3 without credentials either (e.g. temporary credentials that ran out)
    with patch.object(BaseClient, "_make_api_call", side_effect=NoCredentialsError()):
        assert get_s3_unreachable_reason(s3_client, "my-bucket") == "Unable to locate credentials"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_verification_ends_with_one_error_when_s3_can_no_longer_be_reached(tmp_path):
    failed_keys = [f"failed_{index}.txt" for index in range(8)]
    verify_objects = {
        "first-bucket": [verified("a.txt"), verified("b.txt")] + [_failed(key) for key in failed_keys],
        "second-bucket": [verified("c.txt")],
    }

    backup, fake_s3 = _run_verified_backup(tmp_path, verify_objects, reachable=False)

    reason = 'Could not connect to the endpoint URL: "https://s3.invalid/"'
    assert backup.errors == [f"first-bucket : S3 could not be reached during the verification, which ended there : 8 of 10 files were not verified : {reason}"]
    assert backup.error_count == 1
    # the verification was told to stop as soon as S3 was found to be unreachable, which leaves the files that follow not attempted
    first_result = fake_s3.verify_results["first-bucket"]
    assert first_result.get_count(S3VerifyOutcome.failed) == verify_failures_before_reachability_check
    assert first_result.get_count(S3VerifyOutcome.not_attempted) == len(failed_keys) - verify_failures_before_reachability_check
    assert "first-bucket : verified 2 of 10 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos
    fake_s3.bucket_accesses["second-bucket"].verify_directory.assert_not_called()
    assert "verified 2 files in 1 buckets against S3, 0 differ (S3 could not be reached, so the verification ended : 1 more buckets were not verified)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_files_that_fail_while_s3_can_be_reached_are_each_an_error_and_the_verification_goes_on(tmp_path):
    # e.g. access to these objects is denied: S3 answers, so every file is still verified
    failed_keys = [f"failed_{index}.txt" for index in range(verify_failures_before_reachability_check + 1)]
    verify_objects = {"first-bucket": [_failed(key) for key in failed_keys] + [verified("a.txt")], "second-bucket": [verified("c.txt")]}

    backup, fake_s3 = _run_verified_backup(tmp_path, verify_objects, reachable=True)

    assert backup.errors == [f'first-bucket : "{key}" could not be verified : {metadata_failure}' for key in failed_keys]
    first_bucket_client = fake_s3.bucket_accesses["first-bucket"].client
    assert first_bucket_client.head_bucket.call_count == 1  # one check that S3 can be reached, for the failures that came one after the other
    fake_s3.bucket_accesses["second-bucket"].verify_directory.assert_called_once()
    assert "verified 6 files in 2 buckets against S3, 0 differ, 4 could not be verified" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_failures_that_end_a_bucket_are_checked_for_s3_being_unreachable(tmp_path):
    # fewer failures than are checked during a verification, but nothing was verified after them
    verify_objects = {"first-bucket": [verified("a.txt"), _failed("last.txt")], "second-bucket": [verified("c.txt")]}

    backup, fake_s3 = _run_verified_backup(tmp_path, verify_objects, reachable=False)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("first-bucket : S3 could not be reached during the verification, which ended there : 1 of 2 files were not verified : ")
    fake_s3.bucket_accesses["second-bucket"].verify_directory.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_failure_that_is_followed_by_a_verified_file_is_not_checked_for_s3_being_unreachable(tmp_path):
    verify_objects = {"first-bucket": [_failed("first.txt"), verified("a.txt")]}

    backup, fake_s3 = _run_verified_backup(tmp_path, verify_objects, reachable=False)  # (it would not be, if it was asked)

    assert backup.errors == [f'first-bucket : "first.txt" could not be verified : {metadata_failure}']
    fake_s3.bucket_accesses["first-bucket"].client.head_bucket.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_verification_that_raises_is_an_error_and_the_other_buckets_are_verified(tmp_path):
    # awsimple puts what fails for one object in its result, but not everything (e.g. credentials that are no longer there)
    backup = make_s3_backup()
    verify_objects = {"first-bucket": [verified("a.txt")], "second-bucket": [verified("c.txt")]}
    with patch.object(FakeS3, "verify_directory", side_effect=[NoCredentialsError(), make_verify_result([verified("c.txt")])]):
        _run_verified_backup(tmp_path, verify_objects, reachable=True, backup=backup)

    assert backup.errors == ["first-bucket : could not verify the files against S3 : Unable to locate credentials"]
    assert "second-bucket : verified 1 of 1 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos
    assert "verified 1 files in 2 buckets against S3, 0 differ" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_request_during_a_verification_stops_it(tmp_path):
    # the verification has a stop event of its own, which a stop of the backup has to reach
    backup = make_s3_backup()
    verify_objects = {"first-bucket": [verified("a.txt"), verified("b.txt"), verified("c.txt")]}
    stopping_fake_s3_verify_directory = FakeS3.verify_directory

    def verify_directory(fake_s3, bucket_name, sync_result):
        backup.request_stop()  # e.g. Stop is pressed during the verification
        return stopping_fake_s3_verify_directory(fake_s3, bucket_name, sync_result)

    with patch.object(FakeS3, "verify_directory", verify_directory):
        _unused_backup, fake_s3 = _run_verified_backup(tmp_path, verify_objects, reachable=True, backup=backup)

    # the first file was under way, and the others were not started
    assert "first-bucket : verified 1 of 3 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos
    assert "verified 1 files in 1 buckets against S3, 0 differ (stopped before all files were verified)" in backup.infos
    assert backup.errors == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_verification_ends_when_the_connection_drops(moto_s3_endpoint, tmp_path):
    """
    The real sync and verification (awsimple's) against a local S3 server, with every request failing to connect from part way
    through the verification of the first bucket on.
    """
    object_count = 30
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    for bucket_name in ("a-drop-bucket", "b-later-bucket"):
        s3_client.create_bucket(Bucket=bucket_name)
    for index in range(object_count):
        s3_client.put_object(Bucket="a-drop-bucket", Key=f"{index:02}.txt", Body=b"x" * 100, ChecksumAlgorithm="CRC64NVME")
    s3_client.put_object(Bucket="b-later-bucket", Key="later.txt", Body=b"y" * 100, ChecksumAlgorithm="CRC64NVME")

    real_make_api_call = BaseClient._make_api_call
    real_verify_backup = S3Backup.verify_backup
    lock = threading.Lock()
    verifying = threading.Event()
    connection_dropped = threading.Event()
    metadata_request_count = 0

    def make_api_call(client, operation_name, api_params):
        nonlocal metadata_request_count
        with lock:
            if verifying.is_set() and operation_name == "HeadObject":
                metadata_request_count += 1
                if metadata_request_count > 5:
                    connection_dropped.set()
            if connection_dropped.is_set():
                raise EndpointConnectionError(endpoint_url=moto_s3_endpoint)
        return real_make_api_call(client, operation_name, api_params)

    def verify_backup(backup, buckets):
        verifying.set()
        real_verify_backup(backup, buckets)

    with patch.object(BaseClient, "_make_api_call", make_api_call), patch.object(S3Backup, "verify_backup", verify_backup):
        backup = run_real_s3_backup(tmp_path, s3_verify=True)

    assert "2 buckets, 2 backed up, 31 files synced, 0 excluded" in backup.infos  # the backup itself was done before the connection dropped
    assert len(backup.errors) == 1
    error = re.fullmatch(
        r"a-drop-bucket : S3 could not be reached during the verification, which ended there : (\d+) of 30 files were not verified : Could not connect to .*", backup.errors[0]
    )
    assert error is not None
    assert int(error.group(1)) >= object_count - 5
    assert not any(info.startswith("b-later-bucket : verified") for info in backup.infos)
    assert any(info.endswith("(S3 could not be reached, so the verification ended : 1 more buckets were not verified)") for info in backup.infos)
