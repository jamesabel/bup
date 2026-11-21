"""
Tests for what the S3 backup reports as received from S3.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from bup import UITypes
from bup.s3_backup import S3Backup, get_synced_size
from bup.transfer import bytes_per_gb

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


def _make_preferences(tmp_path: Path, dry_run: bool = False, aws_transfer_out_price_per_gb=None) -> MagicMock:
    return MagicMock(
        backup_directory=str(tmp_path),
        dry_run=dry_run,
        s3_size_only=False,
        aws_profile=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_region=None,
        aws_transfer_out_price_per_gb=aws_transfer_out_price_per_gb,
    )


def _run_backup(tmp_path: Path, preferences: MagicMock, file_sizes: dict) -> list:
    """
    Run an S3 backup of "my-bucket" whose (faked) sync downloads the given files.
    :return: the backup's info output
    """
    destination = Path(tmp_path, "s3", "my-bucket")
    destination.mkdir(parents=True)
    sync_stdout = ""
    for file_name, file_size in file_sizes.items():
        Path(destination, file_name).write_bytes(b"x" * file_size)
        sync_stdout += f"download: s3://my-bucket/{file_name} to {destination}{os.sep}{file_name}\n"
    infos = []
    backup = S3Backup(UITypes.cli, infos.append, lambda s: None, lambda s: None)
    with (
        patch("bup.s3_backup.get_preferences", return_value=preferences),
        patch("bup.s3_backup.S3Access") as mock_s3_access,
        patch("bup.s3_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.s3_backup.find_aws_cli", return_value=fake_aws_cli),
        patch("bup.s3_backup.get_bucket_size", return_value=(sum(file_sizes.values()), len(file_sizes))),
        patch.object(S3Backup, "run_stoppable_subprocess", return_value=(0, sync_stdout, "")),
    ):
        mock_s3_access.return_value.bucket_list.return_value = ["my-bucket"]
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return infos


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
def test_downloaded_bytes_and_cost_are_reported(tmp_path):
    infos = _run_backup(tmp_path, _make_preferences(tmp_path), {"a.txt": 1024, "b.txt": 2048})

    assert "my-bucket : received 3.0 KB, approximately less than $0.0001 before any AWS free allowance" in infos
    assert "transfer total : received 3.0 KB, approximately less than $0.0001 before any AWS free allowance" in infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cost_uses_the_price_preference(tmp_path):
    # priced so that the 4 KB downloaded costs a round $2
    infos = _run_backup(tmp_path, _make_preferences(tmp_path, aws_transfer_out_price_per_gb=2.0 * bytes_per_gb / 4096), {"a.txt": 4096})

    assert "my-bucket : received 4.0 KB, approximately $2.00 before any AWS free allowance" in infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_nothing_downloaded_reports_only_a_zero_total(tmp_path):
    infos = _run_backup(tmp_path, _make_preferences(tmp_path), {})

    assert not any(info.startswith("my-bucket : received") for info in infos)
    assert "transfer total : received 0 B" in infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dry_run_reports_no_transfer(tmp_path):
    infos = _run_backup(tmp_path, _make_preferences(tmp_path, dry_run=True), {"a.txt": 1024})

    assert not any("received" in info for info in infos)
