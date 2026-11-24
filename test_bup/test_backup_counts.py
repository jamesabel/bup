"""
Tests for what each backup counts for the backup history: the buckets, tables or repositories it found, backed up and excluded, and
the files of the S3 backup.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from awsimple import S3SyncObject, S3SyncOutcome

from bup import BackupTypes, BupBase, UITypes
from bup.backup_history import BackupCounts, BackupHistory, BackupStatus, get_backup_history
from bup.dynamodb_backup import DynamoDBBackup
from bup.github_backup import GithubBackup
from bup.transfer import TransferRecord

from .s3_sync_fakes import FakeS3, downloaded, make_preferences, make_sync_result, run_s3_backup

no_transfer = TransferRecord(None, "transfer total", 0)

# the history table as bup 0.17.0 made it, which had no counts
history_table_0_17_0 = (
    "CREATE TABLE backup_runs ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, backup_type TEXT, ui_type TEXT NOT NULL, pid INTEGER NOT NULL, process_start REAL NOT NULL, "
    "started REAL NOT NULL, ended REAL, status TEXT NOT NULL, received_bytes INTEGER NOT NULL DEFAULT 0, read_units REAL NOT NULL DEFAULT 0.0, cost REAL, "
    "error_count INTEGER NOT NULL DEFAULT 0, warning_count INTEGER NOT NULL DEFAULT 0, errors TEXT NOT NULL DEFAULT '[]')"
)


def _get_recorded_counts() -> BackupCounts:
    """
    :return: the counts of the one backup run in the backup history
    """
    (backup_run,) = get_backup_history().get_runs()
    return backup_run.counts


def _write_local_file(tmp_path: Path, bucket_name: str, relative_path: str, size: int):
    file_path = Path(tmp_path, "s3", bucket_name, relative_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x" * size)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_run_has_no_counts_until_they_are_recorded(tmp_path):
    history = BackupHistory(Path(tmp_path, "backup_history.db"))

    history.start(BackupTypes.S3, UITypes.gui, started=1000.0)

    (backup_run,) = history.get_runs()
    assert backup_run.counts == BackupCounts(None, None, None, None, None)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_counts_are_on_record(tmp_path):
    history = BackupHistory(Path(tmp_path, "backup_history.db"))
    run_id = history.start(BackupTypes.S3, UITypes.gui, started=1000.0)

    history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=1005.0, counts=BackupCounts(found=12, backed_up=10, excluded=2, files=123456, files_synced=7))

    (backup_run,) = history.get_runs()
    assert backup_run.counts == BackupCounts(found=12, backed_up=10, excluded=2, files=123456, files_synced=7)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_history_of_a_bup_that_had_no_counts_is_kept_and_gains_them(tmp_path):
    path = Path(tmp_path, "backup_history.db")
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(history_table_0_17_0)
        connection.execute(
            "INSERT INTO backup_runs (backup_type, ui_type, pid, process_start, started, ended, status, received_bytes) VALUES ('S3', 'gui', 1, 900.0, 1000.0, 1005.0, 'completed', 2048)"
        )
    connection.close()

    history = BackupHistory(path)

    # the run that was recorded without counts is as it was
    (old_run,) = history.get_runs()
    assert (old_run.backup_type, old_run.status, old_run.started, old_run.ended, old_run.received_bytes) == (BackupTypes.S3, BackupStatus.completed, 1000.0, 1005.0, 2048)
    assert old_run.counts == BackupCounts()
    # and a new run has its counts
    run_id = history.start(BackupTypes.DynamoDB, UITypes.cli, started=2000.0)
    history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=2001.0, counts=BackupCounts(found=3, backed_up=2, excluded=1))
    assert history.get_runs()[0].counts == BackupCounts(found=3, backed_up=2, excluded=1)
    # opening the history again changes nothing (the columns are only added once)
    assert [backup_run.counts for backup_run in BackupHistory(path).get_runs()] == [BackupCounts(found=3, backed_up=2, excluded=1), BackupCounts()]


class _CountingBackup(BupBase):
    """
    A backup that counts what it is given, as a backup does as it goes.
    """

    backup_type = BackupTypes.S3

    def __init__(self, found: int):
        super().__init__(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)
        self.found = found

    def run_backup(self):
        self.counts.found = self.found
        # what a run has counted is on record from its first report of a transfer on, in case it never gets to its end
        self.transfer_out(TransferRecord(BackupTypes.S3, "my-bucket", 10))
        self.found_on_record_during_the_run = get_backup_history().get_runs()[0].counts.found
        self.counts.backed_up = self.found


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_records_its_counts_as_it_goes_and_at_its_end():
    backup = _CountingBackup(3)

    backup.run()

    assert backup.found_on_record_during_the_run == 3
    assert _get_recorded_counts() == BackupCounts(found=3, backed_up=3)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_new_run_of_a_backup_starts_its_counts_again(qapp):
    backup = _CountingBackup(3)
    backup.start()
    assert backup.wait(10000)
    backup.found = 1

    backup.start()

    assert backup.wait(10000)
    assert [backup_run.counts.found for backup_run in get_backup_history().get_runs()] == [1, 3]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_backup_counts_buckets_and_files(tmp_path):
    # two files of one bucket and one of the other are in the backup already, and this run downloads two files
    _write_local_file(tmp_path, "bucket-a", "a.txt", 10)
    _write_local_file(tmp_path, "bucket-a", "folder/b.txt", 20)
    _write_local_file(tmp_path, "bucket-b", "c.txt", 30)
    fake_s3 = FakeS3(
        {
            "bucket-a": make_sync_result([downloaded("a.txt", 10), S3SyncObject("folder/b.txt", 20, S3SyncOutcome.up_to_date)]),
            "bucket-b": make_sync_result([downloaded("c.txt", 30)]),
            "excluded-bucket": make_sync_result([]),
        }
    )

    backup = run_s3_backup(tmp_path, fake_s3, exclusions=["excluded-bucket", "no-such-bucket"])

    assert backup.errors == []
    # an exclusion that is not a bucket is not an excluded bucket
    assert _get_recorded_counts() == BackupCounts(found=3, backed_up=2, excluded=1, files=3, files_synced=2)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_bucket_with_a_failed_object_is_not_counted_as_backed_up_but_its_files_are_counted(tmp_path):
    _write_local_file(tmp_path, "my-bucket", "a.txt", 10)
    failed = S3SyncObject("b.txt", 20, S3SyncOutcome.failed, "connection lost")
    fake_s3 = FakeS3({"my-bucket": make_sync_result([S3SyncObject("a.txt", 10, S3SyncOutcome.up_to_date), failed])})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert len(backup.errors) == 1
    assert _get_recorded_counts() == BackupCounts(found=1, backed_up=0, excluded=0, files=1, files_synced=0)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_dry_run_counts_what_it_found_but_backs_up_nothing(tmp_path):
    fake_s3 = FakeS3({"my-bucket": make_sync_result([S3SyncObject("a.txt", 10, S3SyncOutcome.would_download)]), "excluded-bucket": make_sync_result([])})

    run_s3_backup(tmp_path, fake_s3, make_preferences(tmp_path, dry_run=True), exclusions=["excluded-bucket"])

    assert _get_recorded_counts() == BackupCounts(found=2, backed_up=None, excluded=1, files=None, files_synced=None)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_backup_that_could_not_list_the_buckets_has_no_counts(tmp_path):
    from botocore.exceptions import NoCredentialsError

    fake_s3 = MagicMock()
    fake_s3.return_value.bucket_list.side_effect = NoCredentialsError()

    run_s3_backup(tmp_path, fake_s3)

    assert _get_recorded_counts() == BackupCounts()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("dry_run,expected", [(False, BackupCounts(found=3, backed_up=1, excluded=1)), (True, BackupCounts(found=3, backed_up=None, excluded=1))])
def test_dynamodb_backup_counts_tables(tmp_path, dry_run, expected):
    from botocore.exceptions import ClientError

    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=dry_run, aws_profile=None, aws_access_key_id=None, aws_secret_access_key=None, aws_region=None)
    list_access = MagicMock()
    list_access.get_table_names.return_value = ["good_table", "failing_table", "excluded_table"]
    good_table = MagicMock()
    good_table.scan_table_cached.return_value = [{"id": 1}]
    failing_table = MagicMock()
    failing_table.scan_table_cached.side_effect = ClientError({"Error": {"Code": "500", "Message": "failed"}}, "Scan")
    tables = {"good_table": good_table, "failing_table": failing_table}
    backup = DynamoDBBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)

    with (
        patch("bup.dynamodb_backup.get_preferences", return_value=preferences),
        patch("bup.dynamodb_backup.DynamoDBAccess", side_effect=lambda *args, **kwargs: tables[args[0]] if args else list_access),
        patch("bup.dynamodb_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.dynamodb_backup.dynamodb_to_json", return_value="{}"),
        patch("bup.dynamodb_backup.DynamoDBScanMeter"),
        patch.object(DynamoDBBackup, "scan_transfer_out"),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = ["excluded_table"]
        backup.run()

    assert _get_recorded_counts() == expected


def _make_github_repo(owner_and_name: str) -> MagicMock:
    github_repo = MagicMock()
    github_repo.__str__.return_value = owner_and_name
    return github_repo


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("dry_run,expected", [(False, BackupCounts(found=4, backed_up=2, excluded=1)), (True, BackupCounts(found=4, backed_up=None, excluded=1))])
def test_github_backup_counts_repositories(tmp_path, dry_run, expected):
    from bup.github_backup import RepoOutcomes

    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=dry_run, github_token="test_token")
    gh = MagicMock()
    gh.repositories.return_value = [_make_github_repo(name) for name in ("owner/pulled", "owner/cloned", "owner/failed", "owner/excluded")]
    outcomes = {"owner/pulled": RepoOutcomes.pulled, "owner/cloned": RepoOutcomes.cloned, "owner/failed": RepoOutcomes.failed}
    backup = GithubBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)

    with (
        patch("bup.github_backup.get_preferences", return_value=preferences),
        patch("bup.github_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.github_backup.github3.login", return_value=gh),
        patch.object(GithubBackup, "backup_repo", side_effect=lambda github_repo, backup_dir: outcomes[str(github_repo)]),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = ["excluded"]
        backup.run()

    assert _get_recorded_counts() == expected
