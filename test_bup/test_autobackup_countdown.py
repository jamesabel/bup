"""
Tests for what the main window shows next to "Next backup:" once a second, and for when the automatic backup is started.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import re
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from PyQt5.QtWidgets import QCheckBox, QLabel, QSpinBox, QWidget

from bup.gui.bup_dialog import BupDialog


def _make_run_backup_widget(parent=None) -> QWidget:
    widget = QWidget(parent)
    widget.countdown_text = QLabel(parent=widget)
    widget.most_recent_backup = None
    widget.start = MagicMock(return_value=True)
    widget.run_all = MagicMock()
    widget.run_all.isRunning.return_value = False
    widget.run_all.stop_requested = False
    return widget


def _make_preferences_widget(parent=None) -> QWidget:
    widget = QWidget(parent)
    widget.automatic_backup_enable_check_box = QCheckBox(parent=widget)
    widget.automatic_backup_enable_check_box.setChecked(True)
    widget.automatic_backup_period = QSpinBox(parent=widget)
    widget.automatic_backup_period.setValue(1)  # hours
    return widget


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def dialog(qapp):
    """
    The main window with the automatic backup enabled (every hour), and stand-ins for the tabs it reads and starts the backup with.
    """
    with (
        patch("bup.gui.bup_dialog.ctypes"),
        patch("bup.gui.bup_dialog.get_icon_path", return_value=""),
        patch("bup.gui.bup_dialog.get_preferences", return_value=MagicMock(width=800, height=600)),
        patch("bup.gui.bup_dialog.RunBackupWidget", side_effect=_make_run_backup_widget),
        patch("bup.gui.bup_dialog.PreferencesWidget", side_effect=_make_preferences_widget),
        patch("bup.gui.bup_dialog.LogWidget", side_effect=QWidget),
        patch("bup.gui.bup_dialog.BupAbout", side_effect=QWidget),
    ):
        bup_dialog = BupDialog()
        bup_dialog.autobackup_timer.stop()  # the tests tick
        yield bup_dialog


def _tick(dialog) -> str:
    dialog.autobackup_tick()
    return dialog.run_backup_widget.countdown_text.text()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_not_enabled(dialog):
    dialog.preferences_widget.automatic_backup_enable_check_box.setChecked(False)

    assert _tick(dialog) == "(automatic backup not enabled)"
    dialog.run_backup_widget.start.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_period_not_set(dialog):
    dialog.preferences_widget.automatic_backup_period.setValue(0)

    assert _tick(dialog) == "(automatic backup not set)"
    dialog.run_backup_widget.start.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_first_backup_is_started_right_away(dialog):
    assert _tick(dialog) == "(starting first automatic backup)"
    dialog.run_backup_widget.start.assert_called_once()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_first_backup_can_not_be_started_without_a_backup_directory(dialog):
    dialog.run_backup_widget.start.return_value = False

    assert _tick(dialog) == "(backup directory not set)"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_time_of_the_next_backup_and_how_long_until_then(dialog):
    most_recent_backup = int(datetime.now().timestamp()) - 600  # ten minutes ago, and the period is an hour
    dialog.run_backup_widget.most_recent_backup = most_recent_backup

    text = _tick(dialog)

    next_backup = datetime.fromtimestamp(most_recent_backup + 3600).strftime("%m-%d-%Y %H:%M:%S")
    assert re.fullmatch(re.escape(next_backup) + r" \(in 0:(49:5\d|50:00)\)", text)
    dialog.run_backup_widget.start.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_that_is_due_can_not_be_started_without_a_backup_directory(dialog):
    dialog.run_backup_widget.most_recent_backup = int(datetime.now().timestamp()) - 7200
    dialog.run_backup_widget.start.return_value = False

    assert _tick(dialog) == "(backup directory not set)"
    dialog.run_backup_widget.start.assert_called_once()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize("most_recent_backup_age", [None, 600, 7200])
def test_running_backup_is_shown_with_ticks_and_is_not_started_again(dialog, most_recent_backup_age):
    if most_recent_backup_age is not None:
        dialog.run_backup_widget.most_recent_backup = int(datetime.now().timestamp()) - most_recent_backup_age
    dialog.run_backup_widget.run_all.isRunning.return_value = True

    assert [_tick(dialog) for _unused_tick in range(5)] == ["running ", "running .", "running ..", "running ...", "running "]
    dialog.run_backup_widget.start.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backup_that_was_asked_to_stop_is_shown_as_stopping(dialog):
    dialog.run_backup_widget.run_all.isRunning.return_value = True
    dialog.run_backup_widget.run_all.stop_requested = True

    assert _tick(dialog) == "stopping "
