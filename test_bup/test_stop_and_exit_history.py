"""
Tests for what the backup history says about backups that are ended because bup is closed ("Stop and Exit").
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

from unittest.mock import MagicMock, patch

import pytest

from bup import BackupTypes, BupBase, UITypes
from bup.backup_history import BackupStatus, get_backup_history, mark_interrupted_backups
from bup.transfer import TransferRecord


class _Backup(BupBase):
    """
    A backup whose thread the test stands in for: the test says if it is running, and nothing is really terminated.
    """

    def __init__(self, backup_type: BackupTypes, running: bool):
        super().__init__(UITypes.gui, lambda s: None, lambda s: None, lambda s: None)
        self.backup_type = backup_type
        self.running = running
        self.terminate = MagicMock()
        self.wait = MagicMock(return_value=True)

    def isRunning(self) -> bool:
        return self.running


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def make_run_backup_widget(qapp):
    """
    :return: a function that makes the Backup tab with the given backup engines, in the middle of a backup that does not end in time
    """
    with (
        patch("bup.gui.run_backup_widget.get_gui_preferences", return_value=MagicMock(most_recent_backup=None)),
        patch("bup.gui.run_backup_widget.ExclusionPreferences"),
    ):
        from bup.gui.run_backup_widget import RunBackupWidget

        def make(engines: dict) -> RunBackupWidget:
            with patch("bup.gui.run_backup_widget.backup_classes", {backup_type: lambda *args, engine=engine: engine for backup_type, engine in engines.items()}):
                widget = RunBackupWidget()
            widget.run_all = MagicMock()
            widget.run_all.isRunning.return_value = True
            widget.run_all.wait.return_value = False  # the backups did not end within the wait
            return widget

        yield make


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_ended_on_exit_is_recorded_as_stopped_not_as_cut_short(make_run_backup_widget, monkeypatch):
    # S3 and github are still running when the wait is over, DynamoDB got to its end by itself
    engines = {backup_type: _Backup(backup_type, running=backup_type is not BackupTypes.DynamoDB) for backup_type in BackupTypes}
    for engine in engines.values():
        engine.record_start()
    engines[BackupTypes.S3].transfer_out(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5))
    engines[BackupTypes.DynamoDB].record_history(BackupStatus.completed, 2000.0)
    widget = make_run_backup_widget(engines)

    widget.stop()
    widget.wait_for_threads(1)

    engines[BackupTypes.S3].terminate.assert_called_once()
    engines[BackupTypes.github].terminate.assert_called_once()
    engines[BackupTypes.DynamoDB].terminate.assert_not_called()
    runs = {backup_run.backup_type: backup_run for backup_run in get_backup_history().get_runs()}
    assert runs[BackupTypes.S3].status is BackupStatus.stopped
    assert runs[BackupTypes.S3].ended is not None
    assert runs[BackupTypes.S3].received_bytes == 2048  # what it had received is kept
    assert runs[BackupTypes.github].status is BackupStatus.stopped
    assert (runs[BackupTypes.DynamoDB].status, runs[BackupTypes.DynamoDB].ended) == (BackupStatus.completed, 2000.0)  # left as it recorded itself

    # the next bup (this process is gone by then) has nothing to report in its status line
    monkeypatch.setattr("bup.backup_history.is_process_running", lambda pid, process_start: False)
    assert mark_interrupted_backups() == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backups_that_end_in_time_are_not_terminated(make_run_backup_widget):
    engines = {backup_type: _Backup(backup_type, running=True) for backup_type in BackupTypes}
    widget = make_run_backup_widget(engines)
    widget.run_all.wait.return_value = True

    widget.wait_for_threads(1)

    for engine in engines.values():
        engine.terminate.assert_not_called()
    widget.run_all.terminate.assert_not_called()
    assert get_backup_history().get_runs() == []  # nothing recorded on their behalf
