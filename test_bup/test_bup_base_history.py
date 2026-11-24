"""
Tests for how a backup records its run in the backup history (BupBase).
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

import logging
import time

import pytest

from bup import BackupTypes, BupBase, UITypes, backup_history
from bup.backup_history import BackupRun, BackupStatus, get_backup_history
from bup.transfer import TransferRecord


class _Backup(BupBase):
    """
    A backup that does what it is given to do.
    """

    backup_type = BackupTypes.S3

    def __init__(self, ui_type: UITypes = UITypes.cli, action=lambda backup: None):
        super().__init__(ui_type, lambda s: None, lambda s: None, lambda s: None)
        self.action = action

    def run_backup(self):
        self.action(self)


def _run(backup: _Backup) -> BackupRun:
    """
    Run a backup in its thread, to its end.
    :return: its record in the backup history
    """
    backup.start()
    assert backup.wait(10000)
    return _get_run()


def _get_run() -> BackupRun:
    (backup_run,) = get_backup_history().get_runs()
    return backup_run


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_completed_backup_is_recorded():
    before = time.time()

    backup_run = _run(_Backup())

    after = time.time()
    assert backup_run.status is BackupStatus.completed
    assert backup_run.backup_type is BackupTypes.S3
    assert backup_run.ui_type is UITypes.cli
    assert before <= backup_run.started <= backup_run.ended <= after
    assert (backup_run.received_bytes, backup_run.error_count, backup_run.warning_count, backup_run.errors) == (0, 0, 0, ())


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_is_on_record_as_running_while_it_runs():
    seen = []

    backup_run = _run(_Backup(action=lambda backup: seen.append(_get_run())))

    assert seen[0].status is BackupStatus.running
    assert seen[0].ended is None
    assert backup_run.run_id == seen[0].run_id  # the same record, completed
    assert backup_run.status is BackupStatus.completed


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_errors_and_warnings_are_recorded():
    def action(backup: _Backup):
        backup.warning_out("a warning")
        backup.error_out("first error")
        backup.error_out("second error")

    backup_run = _run(_Backup(action=action))

    assert backup_run.status is BackupStatus.completed_with_errors
    assert backup_run.error_count == 2
    assert backup_run.warning_count == 1
    assert backup_run.errors == ("first error", "second error")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_errors_of_a_gui_backup_are_recorded_before_they_are_delivered(qapp):
    # in the GUI an error is delivered to the caller through a signal, in the GUI thread - which has not run here by the time the
    # backup's thread ends and records the run
    delivered = []
    backup = _Backup(UITypes.gui, action=lambda backup: backup.error_out("an error"))
    backup.caller_error_out = delivered.append

    backup_run = _run(backup)

    assert delivered == []
    assert backup_run.status is BackupStatus.completed_with_errors
    assert backup_run.errors == ("an error",)
    qapp.processEvents()
    assert delivered == ["an error"]
    assert backup.error_count == 1  # counted once


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_a_new_run_starts_its_counts_again():
    backup = _Backup(action=lambda backup: backup.error_out("an error"))
    _run(backup)
    backup.action = lambda backup: None

    backup.start()
    assert backup.wait(10000)

    most_recent_run, first_run = get_backup_history().get_runs()
    assert first_run.status is BackupStatus.completed_with_errors
    assert most_recent_run.status is BackupStatus.completed
    assert most_recent_run.errors == ()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stopped_backup_is_recorded_as_stopped():
    backup_run = _run(_Backup(action=lambda backup: backup.request_stop()))

    assert backup_run.status is BackupStatus.stopped
    assert backup_run.ended is not None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_exception_is_recorded_as_failed_and_still_raised():
    def action(backup: _Backup):
        raise RuntimeError("it broke")

    backup = _Backup(action=action)

    with pytest.raises(RuntimeError, match="it broke"):
        backup.run()

    backup_run = _get_run()
    assert backup_run.status is BackupStatus.failed
    assert backup_run.ended is not None
    assert backup_run.error_count == 1
    assert backup_run.errors == ("RuntimeError : it broke",)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_transfers_are_recorded_as_they_are_reported():
    seen = []

    def action(backup: _Backup):
        backup.transfer_out(TransferRecord(BackupTypes.S3, "bucket-a", 1024, cost=0.25, region="us-east-1"))
        seen.append(_get_run())  # on record while the backup is still running, in case it never gets to its end
        backup.transfer_out(TransferRecord(BackupTypes.S3, "bucket-b", 2048, cost=0.5, region="us-east-1"))

    backup_run = _run(_Backup(action=action))

    assert (seen[0].status, seen[0].received_bytes, seen[0].cost) == (BackupStatus.running, 1024, 0.25)
    assert (backup_run.status, backup_run.received_bytes, backup_run.cost) == (BackupStatus.completed, 3072, 0.75)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_runs_without_a_history_it_can_not_write(monkeypatch, tmp_path, caplog):
    not_a_directory = tmp_path / "a_file"
    not_a_directory.write_text("in the way")
    monkeypatch.setattr("bup.backup_history.get_backup_history_path", lambda: not_a_directory / "backup_history.db")
    ran = []

    def action(backup: _Backup):
        backup.transfer_out(TransferRecord(BackupTypes.S3, "bucket-a", 1024))
        ran.append(True)

    backup = _Backup(action=action)
    with caplog.at_level(logging.WARNING):
        backup.run()

    assert ran == [True]
    assert backup.history_run_id is None
    assert [record.levelname for record in caplog.records] == ["WARNING"]  # said once, not for every update
    assert "could not record the backup in the backup history" in caplog.text


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_goes_on_if_the_history_can_no_longer_be_written(monkeypatch, tmp_path, caplog):
    def action(backup: _Backup):
        not_a_directory = tmp_path / "a_file"
        not_a_directory.write_text("in the way")
        monkeypatch.setattr("bup.backup_history.get_backup_history_path", lambda: not_a_directory / "backup_history.db")

    backup = _Backup(action=action)
    with caplog.at_level(logging.WARNING):
        backup.run()

    assert "could not update the backup history" in caplog.text


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_history_change_is_signalled(qapp):
    changes = []

    def on_change():
        changes.append(_get_run().status)

    backup_history.history_emitter.changed_signal.connect(on_change)
    try:
        _Backup().run()
    finally:
        backup_history.history_emitter.changed_signal.disconnect(on_change)

    assert changes == [BackupStatus.running, BackupStatus.completed]
