"""
Tests for what each backup counts for the backup history: the buckets, tables or repositories it found, backed up and excluded, the
files of the S3 backup with their total size, dates and hash, the items of the DynamoDB tables and the branches of the GitHub
repositories.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

import dataclasses
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from awsimple import S3SyncObject, S3SyncOutcome

from bup import BackupTypes, BupBase, UITypes
from bup.backup_history import BackupCounts, BackupHistory, BackupStatus, get_backup_history
from bup.dynamodb_backup import DynamoDBBackup
from bup.github_backup import GithubBackup
from bup.s3_backup import get_dir_summary
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


def _write_local_file(tmp_path: Path, bucket_name: str, relative_path: str, size: int, mtime: Optional[float] = None):
    file_path = Path(tmp_path, "s3", bucket_name, relative_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(file_path, (mtime, mtime))


def _get_first_counts(counts: BackupCounts) -> tuple:
    """
    :return: (found, backed up, excluded, files, files synced) of the counts
    """
    return dataclasses.astuple(counts)[:5]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_run_has_no_counts_until_they_are_recorded(tmp_path):
    history = BackupHistory(Path(tmp_path, "backup_history.db"))

    history.start(BackupTypes.S3, UITypes.gui, started=1000.0)

    (backup_run,) = history.get_runs()
    assert backup_run.counts == BackupCounts()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_counts_are_on_record(tmp_path):
    history = BackupHistory(Path(tmp_path, "backup_history.db"))
    run_id = history.start(BackupTypes.S3, UITypes.gui, started=1000.0)

    counts = BackupCounts(
        found=12,
        backed_up=10,
        excluded=2,
        files=123456,
        files_synced=7,
        size=5 * 1024**4,  # more than 32 bits
        oldest_file_mtime=1262304000.25,
        newest_file_mtime=1795442590.75,
        files_hash="0f" * 32,
        items=98765,
        branches=43,
    )
    history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=1005.0, counts=counts)

    (backup_run,) = history.get_runs()
    assert backup_run.counts == counts
    assert backup_run.counts is not counts


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


# the history table as bup 0.18.0 to 0.21.0 had it: with the counts, and without the size, dates and hash of the files, the items and the branches
history_table_0_21_0 = history_table_0_17_0[:-1] + ", found_count INTEGER, backed_up_count INTEGER, excluded_count INTEGER, file_count INTEGER, synced_file_count INTEGER)"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_history_of_a_bup_that_had_only_the_counts_is_kept_and_gains_the_other_figures(tmp_path):
    path = Path(tmp_path, "backup_history.db")
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(history_table_0_21_0)
        connection.execute(
            "INSERT INTO backup_runs (backup_type, ui_type, pid, process_start, started, ended, status, found_count, backed_up_count, excluded_count, file_count, synced_file_count) "
            "VALUES ('S3', 'gui', 1, 900.0, 1000.0, 1005.0, 'completed', 5, 4, 1, 300, 20)"
        )
    connection.close()

    history = BackupHistory(path)

    # the run that was recorded with only the counts is as it was
    (old_run,) = history.get_runs()
    old_counts = BackupCounts(found=5, backed_up=4, excluded=1, files=300, files_synced=20)
    assert old_run.counts == old_counts
    # and a new run has every figure, each as what it is (a hash is text, a time has its fraction)
    new_counts = BackupCounts(
        found=5, backed_up=4, excluded=1, files=301, files_synced=1, size=4096, oldest_file_mtime=1000.5, newest_file_mtime=2000.5, files_hash="12345678", items=7, branches=9
    )
    run_id = history.start(BackupTypes.S3, UITypes.cli, started=2000.0)
    history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=2001.0, counts=new_counts)
    assert [backup_run.counts for backup_run in BackupHistory(path).get_runs()] == [new_counts, old_counts]


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
    assert _get_first_counts(_get_recorded_counts()) == (3, 2, 1, 3, 2)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_bucket_with_a_failed_object_is_not_counted_as_backed_up_but_its_files_are_counted(tmp_path):
    _write_local_file(tmp_path, "my-bucket", "a.txt", 10)
    failed = S3SyncObject("b.txt", 20, S3SyncOutcome.failed, "connection lost")
    fake_s3 = FakeS3({"my-bucket": make_sync_result([S3SyncObject("a.txt", 10, S3SyncOutcome.up_to_date), failed])})

    backup = run_s3_backup(tmp_path, fake_s3)

    assert len(backup.errors) == 1
    assert _get_first_counts(_get_recorded_counts()) == (1, 0, 0, 1, 0)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_backup_sums_up_the_files_of_its_buckets(tmp_path):
    _write_local_file(tmp_path, "bucket-a", "a.txt", 10, mtime=1262304000.0)
    _write_local_file(tmp_path, "bucket-a", "folder/b.txt", 20, mtime=1700000000.9)
    _write_local_file(tmp_path, "bucket-b", "c.txt", 30, mtime=1500000000.0)
    _write_local_file(tmp_path, "excluded-bucket", "d.txt", 40, mtime=1000000000.0)  # from before the bucket was excluded: not part of what this run backs up
    fake_s3 = FakeS3(
        {
            "bucket-a": make_sync_result([S3SyncObject("a.txt", 10, S3SyncOutcome.up_to_date), S3SyncObject("folder/b.txt", 20, S3SyncOutcome.up_to_date)]),
            "bucket-b": make_sync_result([S3SyncObject("c.txt", 30, S3SyncOutcome.up_to_date)]),
            "empty-bucket": make_sync_result([]),
            "excluded-bucket": make_sync_result([]),
        }
    )

    backup = run_s3_backup(tmp_path, fake_s3, exclusions=["excluded-bucket"])

    assert backup.errors == []
    counts = _get_recorded_counts()
    assert (counts.files, counts.size) == (3, 60)
    assert (counts.oldest_file_mtime, counts.newest_file_mtime) == (pytest.approx(1262304000.0, abs=1.0), pytest.approx(1700000000.9, abs=1.0))
    # the hash is of every file's path in its bucket, size and modification time (in whole seconds), and of the buckets in order
    bucket_a_hash = _sha256("a.txt\x0010\x001262304000\nfolder/b.txt\x0020\x001700000000\n")
    bucket_b_hash = _sha256("c.txt\x0030\x001500000000\n")
    expected_hash = _sha256(f"\nbucket-a\n{bucket_a_hash}")
    expected_hash = _sha256(f"{expected_hash}\nbucket-b\n{bucket_b_hash}")
    expected_hash = _sha256(f"{expected_hash}\nempty-bucket\n{_sha256('')}")
    assert counts.files_hash == expected_hash


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_backup_of_the_same_files_has_the_same_hash_from_run_to_run(tmp_path):
    _write_local_file(tmp_path, "my-bucket", "a.txt", 10, mtime=1262304000.0)
    sync_results = {"my-bucket": make_sync_result([S3SyncObject("a.txt", 10, S3SyncOutcome.up_to_date)])}

    run_s3_backup(tmp_path, FakeS3(sync_results))
    run_s3_backup(tmp_path, FakeS3(sync_results))
    _write_local_file(tmp_path, "my-bucket", "a.txt", 10, mtime=1262304060.0)  # the file is downloaded again, a minute later
    run_s3_backup(tmp_path, FakeS3(sync_results))

    changed_hash, second_hash, first_hash = [backup_run.counts.files_hash for backup_run in get_backup_history().get_runs()]
    assert first_hash is not None
    assert second_hash == first_hash
    assert changed_hash != first_hash


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dir_summary_of_a_directory_without_files(tmp_path):
    Path(tmp_path, "empty_folder").mkdir()

    summary = get_dir_summary(tmp_path)

    assert (summary.size, summary.file_count, summary.oldest_mtime, summary.newest_mtime) == (0, 0, None, None)
    assert summary.files_hash == _sha256("")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize(
    "relative_path,size,mtime,same",
    [
        ("folder/a.txt", 10, 1262304000.0, True),
        ("folder/a.txt", 10, 1262304000.7, True),  # the same second
        ("folder/a.txt", 11, 1262304000.0, False),
        ("folder/a.txt", 10, 1262304001.0, False),
        ("folder/b.txt", 10, 1262304000.0, False),
        ("a.txt", 10, 1262304000.0, False),
    ],
)
def test_dir_summary_hash_is_of_path_size_and_modification_time(tmp_path, relative_path, size, mtime, same):
    _write_local_file(tmp_path, "one", "folder/a.txt", 10, mtime=1262304000.0)
    _write_local_file(tmp_path, "one", "z.txt", 5, mtime=1262304000.0)
    _write_local_file(tmp_path, "other", "z.txt", 5, mtime=1262304000.0)  # written in another order
    _write_local_file(tmp_path, "other", relative_path, size, mtime=mtime)

    one_hash = get_dir_summary(Path(tmp_path, "s3", "one")).files_hash
    other_hash = get_dir_summary(Path(tmp_path, "s3", "other")).files_hash

    assert (one_hash == other_hash) is same


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
@pytest.mark.parametrize("dry_run,expected", [(False, BackupCounts(found=4, backed_up=2, excluded=1, items=3)), (True, BackupCounts(found=4, backed_up=None, excluded=1))])
def test_dynamodb_backup_counts_tables_and_their_items(tmp_path, dry_run, expected):
    from botocore.exceptions import ClientError

    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=dry_run, aws_profile=None, aws_access_key_id=None, aws_secret_access_key=None, aws_region=None)
    list_access = MagicMock()
    list_access.get_table_names.return_value = ["good_table", "failing_table", "excluded_table", "other_table"]
    good_table = MagicMock()
    good_table.scan_table_cached.return_value = [{"id": 1}, {"id": 2}]
    other_table = MagicMock()
    other_table.scan_table_cached.return_value = [{"id": 3}]
    failing_table = MagicMock()
    failing_table.scan_table_cached.side_effect = ClientError({"Error": {"Code": "500", "Message": "failed"}}, "Scan")
    tables = {"good_table": good_table, "failing_table": failing_table, "other_table": other_table}
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
@pytest.mark.parametrize("dry_run,expected", [(False, BackupCounts(found=4, backed_up=2, excluded=1, branches=0)), (True, BackupCounts(found=4, backed_up=None, excluded=1))])
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


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_github_backup_counts_the_branches_of_the_repositories_it_backed_up(tmp_path):
    from bup.backup_types import get_backup_type_directory

    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=False, github_token="test_token")
    branch_counts = {"owner/pulled": 3, "owner/cloned": 2, "owner/failed": 5, "owner/branches_not_listed": 0}
    github_repos = [_make_github_repo(name) for name in branch_counts]
    for github_repo in github_repos:
        github_repo.branches.return_value = [MagicMock() for _unused_index in range(branch_counts[str(github_repo)])]
    gh = MagicMock()
    gh.repositories.return_value = github_repos
    # the repository that is pulled has a local repository already
    Path(get_backup_type_directory(str(tmp_path), BackupTypes.github), "owner", "pulled").mkdir(parents=True)
    backup = GithubBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)

    with (
        patch("bup.github_backup.get_preferences", return_value=preferences),
        patch("bup.github_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.github_backup.github3.login", return_value=gh),
        patch.object(GithubBackup, "pull_repo", return_value=True) as mock_pull_repo,
        patch.object(GithubBackup, "clone_repo", side_effect=lambda repo_owner_and_name, *args: repo_owner_and_name == "owner/cloned"),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()

    assert mock_pull_repo.call_count == 1
    assert _get_recorded_counts() == BackupCounts(found=4, backed_up=2, excluded=0, branches=5)
