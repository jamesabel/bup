"""
Tests for the optional verification of every local file of the S3 backup against the metadata of its S3 object.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import base64
import hashlib
import os
import sys
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

import boto3
import pytest
from awscrt import checksums
from awsimple import S3ObjectMetadata, S3SyncObject, S3SyncOutcome, get_file_crc64nvme
from botocore.exceptions import ClientError

from bup import arguments
from bup.cli.cli_main import cli_main
from bup.gui.preferences_widget import PreferencesWidget
from bup.s3_backup import max_keys_to_list
from bup.s3_verify import get_s3_object_hash, verify_local_file

from .s3_sync_fakes import FakeS3, downloaded, make_preferences, make_s3_backup, make_sync_result, run_s3_backup

s3_mtime = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
contents = b"the contents of the S3 object"


def _to_base64(hex_string: str) -> str:
    # an S3 native checksum as S3 gives it
    return base64.b64encode(bytes.fromhex(hex_string)).decode()


def _make_metadata(key: str = "a.txt", size: int = len(contents), metadata_sha512: Optional[str] = None, checksums: Optional[dict] = None, mtime: datetime = s3_mtime) -> S3ObjectMetadata:
    checksums = {} if checksums is None else checksums
    return S3ObjectMetadata("my-bucket", key, size, mtime, "etag", None, "url", metadata_sha512, None, None, "FULL_OBJECT" if checksums else None, checksums)


def _write_file(file_path: Path, data: bytes = contents, mtime: datetime = s3_mtime) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(data)
    os.utime(file_path, (mtime.timestamp(), mtime.timestamp()))
    return file_path


def _sha512(data: bytes = contents) -> str:
    return hashlib.sha512(data).hexdigest()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_file_that_is_a_copy_of_the_s3_object(tmp_path):
    local_path = _write_file(tmp_path / "a.txt")

    verification = verify_local_file(local_path, _make_metadata(metadata_sha512=_sha512()))

    assert verification.problems == []
    assert verification.mtime_difference is None
    assert verification.hash_name == "SHA-512"
    assert verification.s3_has_hash


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize(
    "hash_name,checksum_field,hex_hash",
    [
        ("SHA-256", "ChecksumSHA256", hashlib.sha256(contents).hexdigest()),
        ("SHA-1", "ChecksumSHA1", hashlib.sha1(contents).hexdigest()),
        ("CRC32C", "ChecksumCRC32C", f"{checksums.crc32c(contents):08x}"),
        ("CRC32", "ChecksumCRC32", f"{zlib.crc32(contents):08x}"),
    ],
)
def test_each_native_checksum_of_s3_is_compared(tmp_path, hash_name, checksum_field, hex_hash):
    local_path = _write_file(tmp_path / "a.txt")

    same = verify_local_file(local_path, _make_metadata(checksums={checksum_field: _to_base64(hex_hash)}))
    assert same.problems == []
    assert same.hash_name == hash_name

    other_hash = "00" * (len(hex_hash) // 2)
    differs = verify_local_file(local_path, _make_metadata(checksums={checksum_field: _to_base64(other_hash)}))
    assert differs.problems == [f"the {hash_name} of the local file is {hex_hash} but the S3 object's is {other_hash}"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_crc64nvme_of_s3_is_compared(tmp_path):
    local_path = _write_file(tmp_path / "a.txt")
    crc64nvme = get_file_crc64nvme(local_path)

    assert verify_local_file(local_path, _make_metadata(checksums={"ChecksumCRC64NVME": _to_base64(crc64nvme)})).hash_name == "CRC64NVME"

    _write_file(local_path, b"x" * len(contents))  # the same size and modification time, but not the contents
    verification = verify_local_file(local_path, _make_metadata(checksums={"ChecksumCRC64NVME": _to_base64(crc64nvme)}))
    assert len(verification.problems) == 1
    assert verification.problems[0].startswith("the CRC64NVME of the local file is ")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_strongest_hash_of_s3_is_used():
    crc32 = _to_base64(f"{zlib.crc32(contents):08x}")
    sha256 = _to_base64(hashlib.sha256(contents).hexdigest())

    assert get_s3_object_hash(_make_metadata(metadata_sha512=_sha512(), checksums={"ChecksumCRC32": crc32, "ChecksumSHA256": sha256}))[0] == "SHA-512"
    assert get_s3_object_hash(_make_metadata(checksums={"ChecksumCRC32": crc32, "ChecksumSHA256": sha256}))[0] == "SHA-256"
    assert get_s3_object_hash(_make_metadata(checksums={"ChecksumCRC32": crc32}))[0] == "CRC32"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_object_without_a_hash_of_its_whole_contents(tmp_path):
    local_path = _write_file(tmp_path / "a.txt")
    # the checksum of an object uploaded in parts can be of its parts ("-<number of parts>"), which is not a hash of the file
    composite = {"ChecksumSHA256": f"{_to_base64(hashlib.sha256(contents).hexdigest())}-3"}

    for s3_object_metadata in (_make_metadata(), _make_metadata(checksums=composite)):
        assert get_s3_object_hash(s3_object_metadata) is None
        verification = verify_local_file(local_path, s3_object_metadata)
        assert verification.problems == []  # the size and the modification time are the S3 object's
        assert verification.hash_name is None
        assert not verification.s3_has_hash


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_size_that_differs(tmp_path):
    local_path = _write_file(tmp_path / "a.txt", contents + b"more")

    verification = verify_local_file(local_path, _make_metadata(metadata_sha512=_sha512()))

    assert verification.problems == [f"the local file is {len(contents) + 4} bytes but the S3 object is {len(contents)} bytes"]
    assert verification.hash_name is None  # the hash would only say it again


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_no_local_file(tmp_path):
    verification = verify_local_file(tmp_path / "missing.txt", _make_metadata(metadata_sha512=_sha512()))

    assert len(verification.problems) == 1
    assert verification.problems[0].startswith(f'no local file "{tmp_path / "missing.txt"}"')
    assert verification.mtime_difference is None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_mtime_that_differs(tmp_path):
    local_path = _write_file(tmp_path / "a.txt", mtime=datetime(2026, 11, 20, 12, 1, 0, tzinfo=timezone.utc))

    verification = verify_local_file(local_path, _make_metadata(metadata_sha512=_sha512()))

    assert verification.problems == []  # the contents are the S3 object's
    assert verification.mtime_difference == "the local file was modified +60 seconds from the S3 object (2026-11-20T12:00:00+00:00)"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_mtime_within_the_tolerance_is_the_same(tmp_path):
    local_path = _write_file(tmp_path / "a.txt", mtime=datetime(2026, 11, 20, 12, 0, 1, tzinfo=timezone.utc))

    assert verify_local_file(local_path, _make_metadata(metadata_sha512=_sha512())).mtime_difference is None


def _run_verified_backup(tmp_path: Path, fake_s3: FakeS3, sync_objects: list, **preferences):
    """
    Run an S3 backup of "my-bucket" with the verification on, where every object of the (faked) sync has the contents and the
    modification time of the S3 object as its local file, unless the test made the local file itself.
    """
    for sync_object in sync_objects:
        local_path = Path(tmp_path, "s3", "my-bucket", sync_object.key)
        if sync_object.outcome in (S3SyncOutcome.downloaded, S3SyncOutcome.up_to_date) and not local_path.exists():
            _write_file(local_path)
    fake_s3.sync_results["my-bucket"] = make_sync_result(sync_objects)
    return run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_verify=True, **preferences))


def _fake_s3_with_metadata(*keys: str) -> FakeS3:
    fake_s3 = FakeS3({})
    fake_s3.object_metadata = {key: _make_metadata(key, metadata_sha512=_sha512()) for key in keys}
    return fake_s3


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_is_not_verified_against_s3_unless_the_preference_is_set(tmp_path):
    _write_file(Path(tmp_path, "s3", "my-bucket", "a.txt"))
    fake_s3 = FakeS3({"my-bucket": make_sync_result([downloaded("a.txt", len(contents))])})

    backup = run_s3_backup(tmp_path, fake_s3)

    fake_s3.bucket_accesses["my-bucket"].get_s3_object_metadata.assert_not_called()
    assert not any("verif" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_every_local_file_is_verified_after_the_backup(tmp_path):
    fake_s3 = _fake_s3_with_metadata("new.txt", "folder/old.txt")
    sync_objects = [
        downloaded("new.txt", len(contents)),
        S3SyncObject("folder/old.txt", len(contents), S3SyncOutcome.up_to_date),
        S3SyncObject("folder/", 0, S3SyncOutcome.skipped, reason="a folder marker"),  # not a file, so there is nothing to verify
    ]

    backup = _run_verified_backup(tmp_path, fake_s3, sync_objects)

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
    fake_s3 = _fake_s3_with_metadata("good.txt", "damaged.txt")
    _write_file(Path(tmp_path, "s3", "my-bucket", "damaged.txt"), b"x" * len(contents))  # the size and the modification time of the S3 object
    sync_objects = [S3SyncObject("good.txt", len(contents), S3SyncOutcome.up_to_date), S3SyncObject("damaged.txt", len(contents), S3SyncOutcome.up_to_date)]

    backup = _run_verified_backup(tmp_path, fake_s3, sync_objects)

    assert backup.errors == [f'my-bucket : "damaged.txt" is not a copy of the S3 object : the SHA-512 of the local file is {_sha512(b"x" * len(contents))} but the S3 object\'s is {_sha512()}']
    assert backup.error_count == 1
    assert "verified 2 files in 1 buckets against S3, 1 differ" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_mtime_that_differs_is_a_warning(tmp_path):
    fake_s3 = _fake_s3_with_metadata("a.txt")
    _write_file(Path(tmp_path, "s3", "my-bucket", "a.txt"), mtime=datetime(2026, 11, 20, 13, 0, 0, tzinfo=timezone.utc))

    backup = _run_verified_backup(tmp_path, fake_s3, [S3SyncObject("a.txt", len(contents), S3SyncOutcome.up_to_date)])

    assert backup.errors == []
    assert backup.warnings == ['my-bucket : "a.txt" has the contents of the S3 object, but the local file was modified +3600 seconds from the S3 object (2026-11-20T12:00:00+00:00)']
    assert any("1 have a different modification time" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_objects_without_a_hash_in_s3_are_counted(tmp_path):
    fake_s3 = FakeS3({})
    fake_s3.object_metadata = {"a.txt": _make_metadata("a.txt")}

    backup = _run_verified_backup(tmp_path, fake_s3, [S3SyncObject("a.txt", len(contents), S3SyncOutcome.up_to_date)])

    assert backup.errors == []
    assert backup.warnings == []
    assert "my-bucket : verified 1 of 1 files against S3 : 0 differ, 0 have a different modification time, 1 have no hash in S3 (size and modification time only)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_metadata_that_can_not_be_read_is_an_error(tmp_path):
    fake_s3 = FakeS3({})
    fake_s3.object_metadata = {"a.txt": ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")}

    backup = _run_verified_backup(tmp_path, fake_s3, [S3SyncObject("a.txt", len(contents), S3SyncOutcome.up_to_date)])

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith('my-bucket : "a.txt" is not a copy of the S3 object : could not get the metadata of the S3 object (')


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_only_the_first_files_that_differ_are_named(tmp_path):
    keys = [f"{index}.txt" for index in range(max_keys_to_list + 2)]
    fake_s3 = _fake_s3_with_metadata(*keys)
    for key in keys:
        _write_file(Path(tmp_path, "s3", "my-bucket", key), b"x" * len(contents))

    backup = _run_verified_backup(tmp_path, fake_s3, [S3SyncObject(key, len(contents), S3SyncOutcome.up_to_date) for key in keys])

    assert len(backup.errors) == max_keys_to_list + 1
    assert backup.errors[-1] == "my-bucket : 2 more local files are not a copy of their S3 object"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dry_run_is_not_verified(tmp_path):
    fake_s3 = _fake_s3_with_metadata("a.txt")

    backup = _run_verified_backup(tmp_path, fake_s3, [S3SyncObject("a.txt", len(contents), S3SyncOutcome.would_download)], dry_run=True)

    fake_s3.bucket_accesses["my-bucket"].get_s3_object_metadata.assert_not_called()
    assert not any("verif" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_request_ends_the_verification(tmp_path):
    fake_s3 = _fake_s3_with_metadata("a.txt")
    backup = make_s3_backup()
    _write_file(Path(tmp_path, "s3", "my-bucket", "a.txt"))
    fake_s3.sync_results["my-bucket"] = make_sync_result([S3SyncObject("a.txt", len(contents), S3SyncOutcome.up_to_date)])

    with patch.object(backup, "verify_bucket", side_effect=lambda *args: backup.request_stop() or (1, 0)) as mock_verify_bucket:
        fake_s3.sync_results["other-bucket"] = make_sync_result([])
        run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, s3_verify=True), backup=backup)

    assert mock_verify_bucket.call_count == 1  # the second bucket is not verified
    assert "verified 1 files in 1 buckets against S3, 0 differ (stopped before all files were verified)" in backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_file_is_not_verified_once_a_stop_is_requested(tmp_path):
    backup = make_s3_backup()
    backup.request_stop()
    bucket_access = MagicMock()

    assert backup.verify_object(bucket_access, tmp_path, S3SyncObject("a.txt", 1, S3SyncOutcome.up_to_date)) is None
    bucket_access.get_s3_object_metadata.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def moto_s3_endpoint(monkeypatch, tmp_path):
    """
    A local in-memory S3 server, with the environment set up so boto3 and awsimple talk to it and not real AWS.
    """
    from moto.server import ThreadedMotoServer

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


def _run_real_verified_backup(backup_directory: Path):
    backup = make_s3_backup()
    with (
        patch("bup.s3_backup.get_preferences", return_value=make_preferences(backup_directory, s3_verify=True)),
        patch("bup.s3_backup.ExclusionPreferences") as mock_exclusions,
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return backup


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_real_backup_is_verified_and_a_damaged_file_is_found(moto_s3_endpoint, tmp_path):
    """
    The real sync and verification against a local S3 server: what was just backed up verifies with a hash from S3, and a local
    file that is then damaged (with the size and the modification time it had, so that a sync sees nothing) is an error.
    """
    s3_client = boto3.client("s3", endpoint_url=moto_s3_endpoint)
    s3_client.create_bucket(Bucket="verify-bucket")
    s3_client.put_object(Bucket="verify-bucket", Key="plain.txt", Body=b"x" * 1000, ChecksumAlgorithm="CRC64NVME")
    s3_client.put_object(Bucket="verify-bucket", Key="/folder//nested.txt", Body=b"y" * 2000, ChecksumAlgorithm="SHA256")

    backup = _run_real_verified_backup(tmp_path)

    assert backup.errors == []
    assert backup.warnings == []
    assert "verify-bucket : verified 2 of 2 files against S3 : 0 differ, 0 have a different modification time, 0 have no hash in S3 (size and modification time only)" in backup.infos

    nested_file = tmp_path / "s3" / "verify-bucket" / "folder" / "nested.txt"
    nested_stat = nested_file.stat()
    nested_file.write_bytes(b"z" * 2000)
    os.utime(nested_file, (nested_stat.st_mtime, nested_stat.st_mtime))

    second_backup = _run_real_verified_backup(tmp_path)

    assert "1 buckets, 1 backed up, 0 files synced, 0 excluded" in second_backup.infos  # the sync sees a current file
    assert len(second_backup.errors) == 1
    assert second_backup.errors[0].startswith('verify-bucket : "/folder//nested.txt" is not a copy of the S3 object : the SHA-256 of the local file is ')
    assert "verified 2 files in 1 buckets against S3, 1 differ" in second_backup.infos


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
