"""
Tests for the GUI's History tab, and for the History tab and the status line of the main window.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QCheckBox, QLabel, QSpinBox, QWidget

from bup import BackupTypes, BupBase, UITypes, backup_history
from bup.backup_history import BackupStatus, format_time, get_backup_history
from bup.gui.history_widget import HistoryWidget, columns
from bup.gui.status_line import status_emitter
from bup.transfer import TransferRecord

no_transfer = TransferRecord(None, "transfer total", 0)


def _row_text(history_widget: HistoryWidget, row: int) -> dict:
    return {column_name: history_widget.table.item(row, column).text() for column, column_name in enumerate(columns)}


def _record_cut_short_backups(monkeypatch, started: float = 1795442590.0):
    """
    Leave the history as a GUI that died in the middle of a backup leaves it.
    """
    for backup_type in BackupTypes:
        get_backup_history().start(backup_type, UITypes.gui, started=started)
    monkeypatch.setattr("bup.backup_history.is_process_running", lambda pid, process_start: False)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_no_history_yet(qapp):
    history_widget = HistoryWidget()

    assert history_widget.table.rowCount() == 0
    assert history_widget.status_label.isHidden()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_runs_are_shown_most_recent_first(qapp):
    history = get_backup_history()
    started = datetime(2026, 11, 20, 12, 0, 0).timestamp()
    run_id = history.start(BackupTypes.DynamoDB, UITypes.cli, started=started)
    transfer_total = TransferRecord(BackupTypes.DynamoDB, "transfer total", 2048 * 3725, 12.5, 0.25)
    history.update(run_id, BackupStatus.completed_with_errors, transfer_total, 2, 1, ["first error", "second error"], ended=started + 3725.0)
    history.start(BackupTypes.github, UITypes.gui, started=datetime(2026, 11, 21, 8, 30, 15).timestamp())

    history_widget = HistoryWidget()

    assert history_widget.table.rowCount() == 2
    assert _row_text(history_widget, 0) == {
        "Started": "2026-11-21 08:30:15",
        "Ended": "",
        "Duration": "",
        "Backup": "github",
        "Run from": "GUI",
        "Status": "running",
        "Received": "0 B",
        "Average rate": "",
        "Read units": "",
        "Approx. cost": "",
        "Errors": "0",
        "Warnings": "0",
        "Error details": "",
    }
    assert _row_text(history_widget, 1) == {
        "Started": "2026-11-20 12:00:00",
        "Ended": "13:02:05",  # on the day it started
        "Duration": "1:02:05",
        "Backup": "DynamoDB",
        "Run from": "CLI",
        "Status": "completed with errors",
        "Received": "7.3 MB",
        "Average rate": "2.0 KB/s",
        "Read units": "12.5",
        "Approx. cost": "$0.2500",
        "Errors": "2",
        "Warnings": "1",
        "Error details": "first error",
    }
    # every error is in the tool tip
    assert history_widget.table.item(1, columns.index("Error details")).toolTip() == "first error\nsecond error"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_end_has_its_date_when_it_is_not_the_day_the_backup_started(qapp):
    history = get_backup_history()
    started = datetime(2026, 11, 20, 23, 50, 0).timestamp()
    run_id = history.start(BackupTypes.S3, UITypes.gui, started=started)
    history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=started + 20 * 60)

    row_text = _row_text(HistoryWidget(), 0)

    assert (row_text["Started"], row_text["Ended"], row_text["Duration"]) == ("2026-11-20 23:50:00", "2026-11-21 00:10:00", "0:20:00")
    assert row_text["Average rate"] == ""  # nothing was received


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_shows_up_as_it_runs_and_ends(qapp):
    history_widget = HistoryWidget()
    statuses = []

    class Backup(BupBase):
        backup_type = BackupTypes.S3

        def run_backup(self):
            statuses.append(_row_text(history_widget, 0)["Status"])
            self.transfer_out(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5))

    Backup(UITypes.gui, lambda s: None, lambda s: None, lambda s: None).run()

    assert statuses == ["running"]
    assert history_widget.table.rowCount() == 1
    row_text = _row_text(history_widget, 0)
    assert (row_text["Backup"], row_text["Status"], row_text["Received"], row_text["Approx. cost"]) == ("S3", "completed", "2.0 KB", "$0.5000")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_history_is_read_again_when_the_tab_is_shown(qapp):
    history_widget = HistoryWidget()
    get_backup_history().start(BackupTypes.S3, UITypes.cli)  # as another bup (e.g. a CLI run) does, which this one gets no signal for
    assert history_widget.table.rowCount() == 0

    history_widget.show()
    qapp.processEvents()

    assert history_widget.table.rowCount() == 1
    history_widget.hide()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_unreadable_history_is_reported_in_place_of_the_runs(qapp):
    history_path = backup_history.get_backup_history_path()
    history_path.parent.mkdir(parents=True)
    history_path.write_bytes(b"this is not a SQLite database, and is long enough to not look like an empty one" * 10)

    history_widget = HistoryWidget()

    assert history_widget.table.rowCount() == 0
    assert not history_widget.status_label.isHidden()
    assert history_widget.status_label.text().startswith("Backup history not available")


def _make_stand_in_run_backup_widget() -> QWidget:
    widget = QWidget()
    widget.countdown_text = QLabel(parent=widget)
    widget.most_recent_backup = None
    widget.run_all = MagicMock()
    widget.run_all.isRunning.return_value = False
    return widget


def _make_stand_in_preferences_widget() -> QWidget:
    widget = QWidget()
    widget.automatic_backup_enable_check_box = QCheckBox(parent=widget)
    widget.automatic_backup_period = QSpinBox(parent=widget)
    return widget


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def make_bup_dialog(qapp):
    """
    :return: a function that makes the main window as starting bup does, with stand-ins for the tabs that are not about the history
    """
    preferences = MagicMock(width=800, height=600)
    dialogs = []
    with (
        patch("bup.gui.bup_dialog.ctypes"),
        patch("bup.gui.bup_dialog.get_icon_path", return_value=""),
        patch("bup.gui.bup_dialog.get_preferences", return_value=preferences),
        patch("bup.gui.bup_dialog.RunBackupWidget", side_effect=_make_stand_in_run_backup_widget),
        patch("bup.gui.bup_dialog.PreferencesWidget", side_effect=_make_stand_in_preferences_widget),
        patch("bup.gui.bup_dialog.LogWidget", side_effect=QWidget),
        patch("bup.gui.bup_dialog.BupAbout", side_effect=QWidget),
    ):
        from bup.gui.bup_dialog import BupDialog

        def make():
            dialogs.append(BupDialog())
            return dialogs[-1]

        yield make
        for dialog in dialogs:
            dialog.autobackup_timer.stop()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_main_window_has_the_history_tab(make_bup_dialog):
    dialog = make_bup_dialog()

    tab_names = [dialog.tab_widget.tabText(tab) for tab in range(dialog.tab_widget.count())]
    assert tab_names == ["Backup", "Preferences", "Log", "Transfer", "History", "About"]
    assert dialog.tab_widget.widget(tab_names.index("History")) is dialog.history_widget


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_status_line_is_empty_when_no_backup_was_cut_short(make_bup_dialog):
    history = get_backup_history()
    run_id = history.start(BackupTypes.S3, UITypes.gui, started=1000.0)
    history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended=1005.0)

    dialog = make_bup_dialog()

    assert dialog.status_line.text() == ""


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_status_line_says_a_backup_was_cut_short_when_bup_is_started_again(make_bup_dialog, monkeypatch):
    started = 1795442590.0
    _record_cut_short_backups(monkeypatch, started)

    dialog = make_bup_dialog()

    assert dialog.status_line.text().startswith(f"The S3, DynamoDB, github backup started {format_time(started)} did not finish: ")
    assert "crashed" in dialog.status_line.text()
    # and the History tab has them as not finished
    history_table = dialog.history_widget.table
    assert [history_table.item(row, columns.index("Status")).text() for row in range(history_table.rowCount())] == ["did not finish"] * len(BackupTypes)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_status_line_says_it_only_the_first_time_bup_is_started_again(make_bup_dialog, monkeypatch):
    _record_cut_short_backups(monkeypatch)
    make_bup_dialog()

    dialog = make_bup_dialog()

    assert dialog.status_line.text() == ""
    assert dialog.history_widget.table.item(0, columns.index("Status")).text() == "did not finish"  # still in the history


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_main_window_shows_the_status_in_its_status_line(make_bup_dialog):
    dialog = make_bup_dialog()

    status_emitter.status_signal.emit("Backup stopped at 2026-11-24 10:00:00.")

    assert dialog.status_line.text() == "Backup stopped at 2026-11-24 10:00:00."


def _tick_while_running(dialog, stop_requested: bool) -> str:
    """
    :return: what is shown for the next backup while a backup is running, with the automatic backup enabled
    """
    dialog.preferences_widget.automatic_backup_enable_check_box.setChecked(True)
    dialog.preferences_widget.automatic_backup_period.setValue(1)
    dialog.run_backup_widget.most_recent_backup = int(time.time())
    dialog.run_backup_widget.run_all.isRunning.return_value = True
    dialog.run_backup_widget.run_all.stop_requested = stop_requested
    dialog.autobackup_tick()
    return dialog.run_backup_widget.countdown_text.text()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_running_backup_is_shown_as_running(make_bup_dialog):
    assert _tick_while_running(make_bup_dialog(), stop_requested=False).startswith("running")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_that_was_asked_to_stop_is_not_shown_as_running(make_bup_dialog):
    text = _tick_while_running(make_bup_dialog(), stop_requested=True)

    assert text.startswith("stopping")
    assert "running" not in text
