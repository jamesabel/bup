from unittest.mock import patch, MagicMock

import pytest

from bup import BackupTypes


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
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_mock_engine():
    engine = MagicMock()
    engine.start = MagicMock()
    engine.wait = MagicMock()
    engine.terminate = MagicMock()
    return engine


@pytest.fixture
def patched_run_backup_widget(qapp):
    mock_prefs = _make_mock_prefs()

    mock_engines = {bt: _make_mock_engine() for bt in BackupTypes}

    def mock_backup_class_factory(backup_type):
        def factory(ui_type, info_cb, warn_cb, err_cb):
            return mock_engines[backup_type]
        return factory

    mock_classes = {bt: mock_backup_class_factory(bt) for bt in BackupTypes}

    with patch("bup.gui.run_backup_widget.get_gui_preferences", return_value=mock_prefs), \
         patch("bup.gui.run_backup_widget.backup_classes", mock_classes), \
         patch("bup.gui.run_backup_widget.ExclusionPreferences"):
        from bup.gui.run_backup_widget import RunBackupWidget
        widget = RunBackupWidget()
        yield widget, mock_prefs, mock_engines


def test_creation(patched_run_backup_widget):
    widget, _, _ = patched_run_backup_widget
    assert widget.start_button is not None
    assert widget.stop_button is not None
    for bt in BackupTypes:
        assert bt in widget.backup_status


def test_start_without_backup_dir(patched_run_backup_widget):
    widget, mock_prefs, mock_engines = patched_run_backup_widget
    mock_prefs.backup_directory = None
    with patch.object(widget.run_all, "start") as mock_start:
        widget.start()
        mock_start.assert_not_called()


def test_start_with_backup_dir(patched_run_backup_widget):
    widget, mock_prefs, _ = patched_run_backup_widget
    mock_prefs.backup_directory = "/tmp/backup"
    with patch.object(widget.run_all, "start") as mock_start:
        widget.start()
        mock_start.assert_called_once()
    assert widget.most_recent_backup is not None


def test_stop(patched_run_backup_widget):
    widget, _, mock_engines = patched_run_backup_widget
    widget.stop()
    for bt in BackupTypes:
        mock_engines[bt].terminate.assert_called_once()
