"""
Tests for the backup history database (bup/backup_history.py).
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

import os
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from bup import BackupTypes, UITypes, backup_history
from bup.backup_history import BackupHistory, BackupStatus, get_backup_history, get_interrupted_message, is_process_running, mark_interrupted_backups, max_recorded_errors
from bup.transfer import TransferRecord

no_transfer = TransferRecord(None, "transfer total", 0)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def history() -> BackupHistory:
    return get_backup_history()


def _process_is_gone(monkeypatch):
    # as if every process that recorded a backup has since died (e.g. the system crashed)
    monkeypatch.setattr("bup.backup_history.is_process_running", lambda pid, process_start: False)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_history_is_a_sqlite_database_in_its_own_file(history):
    assert backup_history.get_backup_history_path().is_file()
    assert history.get_runs() == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_started_backup_is_on_record_as_running(history):
    run_id = history.start(BackupTypes.S3, UITypes.gui, started=1000.0)

    (backup_run,) = history.get_runs()
    assert backup_run.run_id == run_id
    assert backup_run.backup_type is BackupTypes.S3
    assert backup_run.ui_type is UITypes.gui
    assert backup_run.pid == os.getpid()
    assert backup_run.started == 1000.0
    assert backup_run.ended is None
    assert backup_run.status is BackupStatus.running
    assert (backup_run.received_bytes, backup_run.read_units, backup_run.cost) == (0, 0.0, None)
    assert (backup_run.error_count, backup_run.warning_count, backup_run.errors) == (0, 0, ())
    assert backup_run.duration is None
    assert backup_run.average_rate is None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_ended_backup_has_its_statistics_on_record(history):
    run_id = history.start(BackupTypes.DynamoDB, UITypes.cli, started=1000.0)

    transfer_total = TransferRecord(BackupTypes.DynamoDB, "transfer total", 4096, 12.5, 0.25)
    history.update(run_id, BackupStatus.completed_with_errors, transfer_total, 2, 3, ["first error", "second error"], ended=1008.0)

    (backup_run,) = history.get_runs()
    assert backup_run.status is BackupStatus.completed_with_errors
    assert backup_run.ended == 1008.0
    assert backup_run.duration == 8.0
    assert backup_run.received_bytes == 4096
    assert backup_run.average_rate == 512.0
    assert backup_run.read_units == 12.5
    assert backup_run.cost == 0.25
    assert backup_run.error_count == 2
    assert backup_run.warning_count == 3
    assert backup_run.errors == ("first error", "second error")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_every_error_is_counted_but_only_so_many_messages_are_kept(history):
    run_id = history.start(BackupTypes.S3, UITypes.cli)
    errors = [f"error {error_number}" for error_number in range(max_recorded_errors + 5)]

    history.update(run_id, BackupStatus.completed_with_errors, no_transfer, len(errors), 0, errors, ended=2000.0)

    (backup_run,) = history.get_runs()
    assert backup_run.error_count == max_recorded_errors + 5
    assert backup_run.errors == tuple(errors[:max_recorded_errors])


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_runs_are_most_recent_first_and_limited(history):
    for started in (1000.0, 3000.0, 2000.0):
        history.start(BackupTypes.github, UITypes.cli, started=started)

    assert [backup_run.started for backup_run in history.get_runs()] == [3000.0, 2000.0, 1000.0]
    assert [backup_run.started for backup_run in history.get_runs(limit=2)] == [3000.0, 2000.0]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_history_persists(history):
    history.start(BackupTypes.S3, UITypes.gui, started=1000.0)

    assert [backup_run.started for backup_run in get_backup_history().get_runs()] == [1000.0]  # as the next bup reads it


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_this_process_is_running():
    assert is_process_running(os.getpid(), psutil.Process().create_time())


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_a_later_process_with_the_same_pid_is_not_the_process():
    # e.g. after a restart of the system, something else has the pid that bup had
    assert not is_process_running(os.getpid(), psutil.Process().create_time() - 3600.0)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_a_process_that_has_ended_is_not_running():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process_start = psutil.Process(process.pid).create_time()
    process.wait(60.0)

    assert not is_process_running(process.pid, process_start)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_this_process_is_running_is_not_interrupted(history):
    history.start(BackupTypes.S3, UITypes.cli)

    assert history.mark_interrupted() == []
    assert [backup_run.status for backup_run in history.get_runs()] == [BackupStatus.running]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_of_a_process_that_died_is_marked_interrupted(history, monkeypatch):
    ended_run_id = history.start(BackupTypes.github, UITypes.gui, started=1000.0)
    history.update(ended_run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=1005.0)
    cut_short_run_id = history.start(BackupTypes.S3, UITypes.gui, started=2000.0)
    # it had received something and had an error before it was cut short
    history.update(cut_short_run_id, BackupStatus.running, TransferRecord(BackupTypes.S3, "transfer total", 2048, cost=0.5), 1, 0, ["an error"])
    _process_is_gone(monkeypatch)

    (interrupted_run,) = history.mark_interrupted()

    assert interrupted_run.run_id == cut_short_run_id
    assert interrupted_run.status is BackupStatus.interrupted
    cut_short_run, ended_run = history.get_runs()
    assert cut_short_run == interrupted_run
    assert cut_short_run.ended is None  # when it was cut short is not known
    assert (cut_short_run.received_bytes, cut_short_run.cost, cut_short_run.error_count, cut_short_run.errors) == (2048, 0.5, 1, ("an error",))
    assert ended_run.status is BackupStatus.completed


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_interrupted_backup_is_only_reported_once(history, monkeypatch):
    history.start(BackupTypes.S3, UITypes.gui)
    _process_is_gone(monkeypatch)

    assert len(mark_interrupted_backups()) == 1
    assert mark_interrupted_backups() == []  # the next time bup is started


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_unreadable_history_has_no_interrupted_backups():
    history_path = backup_history.get_backup_history_path()
    history_path.parent.mkdir(parents=True)
    history_path.write_bytes(b"this is not a SQLite database, and is long enough to not look like an empty one" * 10)

    assert mark_interrupted_backups() == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_no_message_without_interrupted_backups():
    assert get_interrupted_message([]) == ""


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_message_names_the_interrupted_backups_and_when_they_started(history, monkeypatch):
    started = 1795442590.0
    for backup_type in (BackupTypes.github, BackupTypes.S3):
        history.start(backup_type, UITypes.gui, started=started)
    _process_is_gone(monkeypatch)

    message = get_interrupted_message(history.mark_interrupted())

    assert message.startswith(f"The S3, github backup started {backup_history.format_time(started)} did not finish: ")
    assert "crashed" in message
    assert "\n" not in message  # it is for a status line


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_time_is_local_date_and_time_to_the_second():
    assert len(backup_history.format_time(1795442590.25)) == len("2026-11-23 14:05:09")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_of_a_killed_bup_is_found_by_the_next_one(history):
    # another process records that it has started a backup (as a bup that is running one has), and is then killed in the middle of it
    project_root = Path(__file__).resolve().parent.parent
    script = (
        "import sys, time; from pathlib import Path; from bup import BackupTypes, UITypes; from bup.backup_history import BackupHistory; "
        "BackupHistory(Path(sys.argv[1])).start(BackupTypes.S3, UITypes.cli); print('started', flush=True); time.sleep(600)"
    )
    process = subprocess.Popen([sys.executable, "-c", script, str(history.path)], stdout=subprocess.PIPE, text=True, cwd=project_root, env={**os.environ, "PYTHONPATH": str(project_root)})
    try:
        assert process.stdout.readline().strip() == "started"
        (running_run,) = history.get_runs()
        assert history.mark_interrupted() == []  # it is still running its backup
    finally:
        # the python.exe of a Windows virtual environment runs the real Python as a process of its own, which is the one to end
        for child_process in psutil.Process(process.pid).children(recursive=True):
            child_process.kill()
            child_process.wait(60.0)
        process.kill()
        process.wait(60.0)
        process.stdout.close()

    (interrupted_run,) = history.mark_interrupted()

    assert interrupted_run.run_id == running_run.run_id
    assert [(backup_run.backup_type, backup_run.status) for backup_run in history.get_runs()] == [(BackupTypes.S3, BackupStatus.interrupted)]
