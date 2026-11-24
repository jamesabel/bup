"""
Tests for how the GUI acknowledges that the user stopped a backup: it says so, and does not go on as if the backup were running.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty backup history of its own.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from bup import BackupTypes, BupBase, UITypes
from bup.gui.status_line import status_emitter


class _Backup(BupBase):
    """
    A backup that runs until it is asked to stop, or ends right away.
    """

    def __init__(self, backup_type: BackupTypes, until_stopped: bool):
        super().__init__(UITypes.gui, lambda s: None, lambda s: None, lambda s: None)
        self.backup_type = backup_type
        self.until_stopped = until_stopped
        self.is_running_backup = threading.Event()

    def run_backup(self):
        self.is_running_backup.set()
        try:
            if self.until_stopped:
                assert self.stop_event.wait(60.0)
        finally:
            self.is_running_backup.clear()  # so that a test that starts it again waits for that run, not this one


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def statuses(qapp):
    """
    :return: the messages sent to the status line, in order
    """
    messages = []
    status_emitter.status_signal.connect(messages.append)
    yield messages
    status_emitter.status_signal.disconnect(messages.append)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def make_run_backup_widget(qapp):
    """
    :return: a function that makes the Backup tab, with backups that run until they are stopped (or that end right away), and its
      stand-in preferences
    """
    preferences = MagicMock(backup_directory="a_backup_directory", most_recent_backup=None)
    widgets = []
    with (
        patch("bup.gui.run_backup_widget.get_gui_preferences", return_value=preferences),
        patch("bup.gui.run_backup_widget.ExclusionPreferences"),
    ):
        from bup.gui.run_backup_widget import RunBackupWidget

        def make(until_stopped: bool):
            with patch("bup.gui.run_backup_widget.backup_classes", {backup_type: lambda *args, backup_type=backup_type: _Backup(backup_type, until_stopped) for backup_type in BackupTypes}):
                widgets.append(RunBackupWidget())
            return widgets[-1], preferences

        yield make
        for widget in widgets:
            widget.stop()
            assert widget.run_all.wait(10000)


def _start(widget):
    """
    Start the backups, and wait until every one of them that runs until it is stopped is running.
    """
    assert widget.start()
    for backup_engine in widget.backup_engines.values():
        if backup_engine.until_stopped:  # one that ends right away may already have
            assert backup_engine.is_running_backup.wait(10.0)


def _wait_for_end(qapp, widget):
    """
    Wait for the backups to end, and for the GUI to have heard that they have.
    """
    assert widget.run_all.wait(10000)
    qapp.processEvents()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_is_acknowledged_right_away_and_when_the_backup_has_stopped(qapp, make_run_backup_widget, statuses):
    widget, _unused_preferences = make_run_backup_widget(until_stopped=True)
    _start(widget)

    widget.stop_button.click()

    assert statuses == ["Stop requested. The backup is stopping, which can take a while."]
    _wait_for_end(qapp, widget)
    assert len(statuses) == 2
    assert statuses[1].startswith("Backup stopped at ")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stopped_backup_is_not_started_again_by_the_automatic_backup_but_is_not_a_completed_backup(qapp, make_run_backup_widget):
    widget, preferences = make_run_backup_widget(until_stopped=True)
    _start(widget)
    before = int(time.time())

    widget.stop_button.click()
    _wait_for_end(qapp, widget)

    # the automatic backup counts from the stop (it starts a backup when the backup period has passed since most_recent_backup) ...
    assert widget.most_recent_backup >= before
    # ... but the next bup still has a backup to do: what is saved is the most recent backup that completed, and there is none
    widget.save_state()
    assert preferences.most_recent_backup is None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_completed_backup_is_saved_as_the_most_recent_and_says_nothing_about_a_stop(qapp, make_run_backup_widget, statuses):
    widget, preferences = make_run_backup_widget(until_stopped=False)
    before = int(time.time())

    _start(widget)
    _wait_for_end(qapp, widget)

    assert statuses == []
    assert widget.most_recent_backup >= before
    widget.save_state()
    assert preferences.most_recent_backup == widget.most_recent_backup


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_most_recent_completed_backup_is_kept_when_a_later_backup_is_stopped(qapp, make_run_backup_widget):
    widget, preferences = make_run_backup_widget(until_stopped=True)
    preferences.most_recent_backup = 1000
    widget.restore_state()
    _start(widget)

    widget.stop_button.click()
    _wait_for_end(qapp, widget)

    widget.save_state()
    assert preferences.most_recent_backup == 1000


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_without_a_running_backup_has_nothing_to_acknowledge(qapp, make_run_backup_widget, statuses):
    widget, _unused_preferences = make_run_backup_widget(until_stopped=True)

    widget.stop_button.click()

    assert statuses == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_starting_again_takes_the_stop_out_of_the_status_line(qapp, make_run_backup_widget, statuses):
    widget, _unused_preferences = make_run_backup_widget(until_stopped=True)
    _start(widget)
    widget.stop_button.click()
    _wait_for_end(qapp, widget)

    _start(widget)

    assert statuses[-1] == ""
    assert not any(backup_engine.stop_requested for backup_engine in widget.backup_engines.values())


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_start_leaves_the_status_line_alone_if_it_does_not_say_stopped(qapp, make_run_backup_widget, statuses):
    # e.g. it says that a backup was cut short by a crash, and the automatic backup starts a second after bup does
    widget, _unused_preferences = make_run_backup_widget(until_stopped=True)

    _start(widget)

    assert statuses == []
