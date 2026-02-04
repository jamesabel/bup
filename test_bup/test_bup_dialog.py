from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QWidget, QLabel, QCheckBox, QSpinBox, QMessageBox


def _make_mock_prefs(**overrides):
    defaults = dict(
        backup_directory="/tmp/backup",
        aws_profile="default",
        aws_access_key_id="AKID",
        aws_secret_access_key="SECRET",
        aws_region="us-east-1",
        github_token="ghp_token",
        verbose=False,
        dry_run=False,
        automatic_backup=False,
        backup_period=None,
        most_recent_backup=None,
        width=800,
        height=600,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_fake_run_backup_widget(parent=None):
    """Create a real QWidget stand-in for RunBackupWidget."""
    w = QWidget(parent)
    w.countdown_text = QLabel(parent=w)
    w.most_recent_backup = None
    w.save_state = MagicMock()
    w.stop = MagicMock()
    w.wait_for_threads = MagicMock()
    w.run_all = MagicMock()
    w.run_all.isRunning.return_value = False
    return w


def _make_fake_preferences_widget(parent=None):
    """Create a real QWidget stand-in for PreferencesWidget."""
    w = QWidget(parent)
    w.automatic_backup_enable_check_box = QCheckBox(parent=w)
    w.automatic_backup_period = QSpinBox(parent=w)
    return w


def _make_fake_about_widget(parent=None):
    return QWidget(parent)


@pytest.fixture
def mock_bup_dialog(qapp):
    mock_prefs = _make_mock_prefs()

    with patch("bup.gui.bup_dialog.ctypes") as mock_ctypes, \
         patch("bup.gui.bup_dialog.get_icon_path", return_value=MagicMock(__str__=lambda self: "")), \
         patch("bup.gui.bup_dialog.get_preferences", return_value=mock_prefs), \
         patch("bup.gui.bup_dialog.RunBackupWidget", side_effect=_make_fake_run_backup_widget), \
         patch("bup.gui.bup_dialog.PreferencesWidget", side_effect=_make_fake_preferences_widget), \
         patch("bup.gui.bup_dialog.BupAbout", side_effect=_make_fake_about_widget):
        mock_ctypes.windll = MagicMock()
        from bup.gui.bup_dialog import BupDialog
        dialog = BupDialog()
        yield dialog, mock_prefs


def test_creation(mock_bup_dialog):
    dialog, _ = mock_bup_dialog
    assert dialog.tab_widget.count() == 3
    assert dialog.autobackup_timer is not None


def test_window_title(mock_bup_dialog):
    dialog, _ = mock_bup_dialog
    assert "bup" in dialog.windowTitle().lower()


def test_autobackup_tick_disabled(mock_bup_dialog):
    dialog, _ = mock_bup_dialog
    # automatic_backup_enable_check_box is unchecked by default
    dialog.autobackup_tick()
    assert "not enabled" in dialog.run_backup_widget.countdown_text.text()


def test_close_event_saves_state(mock_bup_dialog):
    dialog, mock_prefs = mock_bup_dialog
    event = QCloseEvent()
    dialog.closeEvent(event)
    dialog.run_backup_widget.save_state.assert_called_once()
    # width and height should have been written to preferences
    assert mock_prefs.width is not None
    assert mock_prefs.height is not None


def test_close_event_cancel_when_running(mock_bup_dialog):
    dialog, mock_prefs = mock_bup_dialog
    dialog.run_backup_widget.run_all.isRunning.return_value = True
    event = QCloseEvent()
    cancel_button = MagicMock()
    stop_button = MagicMock()
    mock_msg_box = MagicMock()
    mock_msg_box.addButton.side_effect = [stop_button, cancel_button]
    mock_msg_box.clickedButton.return_value = cancel_button
    with patch("bup.gui.bup_dialog.QMessageBox", return_value=mock_msg_box):
        dialog.closeEvent(event)
    assert not event.isAccepted()
    dialog.run_backup_widget.save_state.assert_not_called()


def test_close_event_stop_and_exit_when_running(mock_bup_dialog):
    dialog, mock_prefs = mock_bup_dialog
    dialog.run_backup_widget.run_all.isRunning.return_value = True
    event = QCloseEvent()
    cancel_button = MagicMock()
    stop_button = MagicMock()
    mock_msg_box = MagicMock()
    mock_msg_box.addButton.side_effect = [stop_button, cancel_button]
    mock_msg_box.clickedButton.return_value = stop_button
    with patch("bup.gui.bup_dialog.QMessageBox", return_value=mock_msg_box) as mock_cls:
        mock_cls.Warning = QMessageBox.Warning
        mock_cls.DestructiveRole = QMessageBox.DestructiveRole
        mock_cls.RejectRole = QMessageBox.RejectRole
        dialog.closeEvent(event)
    dialog.run_backup_widget.stop.assert_called_once()
    dialog.run_backup_widget.wait_for_threads.assert_called_once_with(5000)
    dialog.run_backup_widget.save_state.assert_called_once()
