import logging
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from bup import __application_name__
from bup.gui.log_widget import LogWidget, LogSources, minimum_pane_height

logger = logging.getLogger(__application_name__)


@pytest.fixture
def mock_gui_preferences():
    preferences = MagicMock(**{f"log_pane_{log_source.name}_height": None for log_source in LogSources})
    with patch("bup.gui.log_widget.get_gui_preferences", return_value=preferences):
        yield preferences


@pytest.fixture
def log_widget(qapp, mock_gui_preferences):
    original_level = logger.level
    logger.setLevel(logging.INFO)  # balsa isn't initialized in tests, so set the level the GUI would normally have
    widget = LogWidget()
    yield widget
    widget.detach()
    logger.setLevel(original_level)


def _emit_record_from_file(file_name: str, message: str):
    """
    Send a log record through the application logger as if it came from the given source file.
    """
    pathname = str(Path("bup", file_name).absolute())
    record = logger.makeRecord(logger.name, logging.INFO, pathname, 1, message, (), None)
    logger.handle(record)


def _pane_text(log_widget: LogWidget, log_source: LogSources) -> str:
    return log_widget.log_panes[log_source].text_box.toPlainText()


def test_s3_records_route_to_s3_pane(log_widget):
    _emit_record_from_file("s3_backup.py", 'aws s3 sync s3://my-bucket "C:\\backup\\s3\\my-bucket"')
    _emit_record_from_file("aws_cli.py", "AWS CLI 1.46.0 is up to date (latest: 1.46.0)")
    s3_text = _pane_text(log_widget, LogSources.s3)
    assert "aws s3 sync s3://my-bucket" in s3_text
    assert "AWS CLI 1.46.0 is up to date" in s3_text  # aws_cli.py records belong to the S3 pane too
    assert "INFO" in s3_text
    assert "s3_backup.py" in s3_text  # the format includes the originating file and line
    assert "aws s3 sync" not in _pane_text(log_widget, LogSources.github)
    assert "aws s3 sync" not in _pane_text(log_widget, LogSources.application)


def test_github_records_route_to_github_pane(log_widget):
    _emit_record_from_file("github_backup.py", "cloning my-repo")
    assert "cloning my-repo" in _pane_text(log_widget, LogSources.github)
    assert "cloning my-repo" not in _pane_text(log_widget, LogSources.s3)
    assert "cloning my-repo" not in _pane_text(log_widget, LogSources.application)


def test_dynamodb_records_route_to_dynamodb_pane(log_widget):
    _emit_record_from_file("dynamodb_backup.py", "exporting my-table")
    assert "exporting my-table" in _pane_text(log_widget, LogSources.dynamodb)
    assert "exporting my-table" not in _pane_text(log_widget, LogSources.application)


def test_backup_engine_messages_route_by_backup_type(log_widget):
    # info_out/warning_out/error_out messages are logged from bup_base.py, so they can't be routed by source file -
    # BupBase stamps each record with its backup type instead (e.g. the "git pull ..." lines from the GitHub backup)
    from bup import GithubBackup, UITypes

    backup = GithubBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)
    backup.info_out('git pull "owner/repo" branch:"main"')
    assert "git pull" in _pane_text(log_widget, LogSources.github)
    assert "git pull" not in _pane_text(log_widget, LogSources.application)
    assert "git pull" not in _pane_text(log_widget, LogSources.s3)


def test_other_records_route_to_application_pane(log_widget):
    logger.info("backup directory not set")  # logged from this test file, which is not a backup module
    assert "backup directory not set" in _pane_text(log_widget, LogSources.application)
    assert "backup directory not set" not in _pane_text(log_widget, LogSources.s3)
    assert "backup directory not set" not in _pane_text(log_widget, LogSources.github)


def test_log_record_from_worker_thread_is_displayed(qapp, log_widget):
    # backups log from worker QThreads - the record crosses to the GUI thread via a queued signal, delivered by the event loop
    worker = threading.Thread(target=lambda: logger.info("from worker thread"), name="worker")
    worker.start()
    worker.join()
    qapp.processEvents()
    assert "from worker thread" in _pane_text(log_widget, LogSources.application)


def test_clear_button_clears_all_panes(log_widget):
    _emit_record_from_file("s3_backup.py", "s3 line")
    _emit_record_from_file("github_backup.py", "github line")
    log_widget.clear_button.click()
    for log_source in LogSources:
        assert _pane_text(log_widget, log_source) == ""


def test_detach_stops_capture(log_widget):
    log_widget.detach()
    logger.info("after detach")
    for log_source in LogSources:
        assert "after detach" not in _pane_text(log_widget, log_source)


def test_save_state_writes_pane_heights(log_widget, mock_gui_preferences):
    with patch.object(log_widget.splitter, "sizes", return_value=[110, 120, 130, 140]):
        log_widget.save_state()
    assert mock_gui_preferences.log_pane_s3_height == 110
    assert mock_gui_preferences.log_pane_dynamodb_height == 120
    assert mock_gui_preferences.log_pane_github_height == 130
    assert mock_gui_preferences.log_pane_application_height == 140


def test_restore_state_applies_saved_pane_heights(log_widget, mock_gui_preferences):
    mock_gui_preferences.log_pane_s3_height = 150
    mock_gui_preferences.log_pane_dynamodb_height = 60
    mock_gui_preferences.log_pane_github_height = 250
    mock_gui_preferences.log_pane_application_height = 90
    with patch.object(log_widget.splitter, "setSizes") as mock_set_sizes:
        log_widget.restore_state()
    mock_set_sizes.assert_called_once_with([150, 60, 250, 90])


def test_restore_state_makes_every_pane_visible(log_widget, mock_gui_preferences):
    # unset or collapsed-to-zero panes come back at the minimum height so none are invisible
    mock_gui_preferences.log_pane_s3_height = 0
    mock_gui_preferences.log_pane_dynamodb_height = None
    mock_gui_preferences.log_pane_github_height = 10
    mock_gui_preferences.log_pane_application_height = 300
    with patch.object(log_widget.splitter, "setSizes") as mock_set_sizes:
        log_widget.restore_state()
    mock_set_sizes.assert_called_once_with([minimum_pane_height, minimum_pane_height, minimum_pane_height, 300])
