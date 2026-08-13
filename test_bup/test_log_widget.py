import logging
import threading
from pathlib import Path

import pytest

from bup import __application_name__
from bup.gui.log_widget import LogWidget, LogSources

logger = logging.getLogger(__application_name__)


@pytest.fixture
def log_widget(qapp):
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
