import logging
import threading

import pytest

from bup import __application_name__
from bup.gui.log_widget import LogWidget

logger = logging.getLogger(__application_name__)


@pytest.fixture
def log_widget(qapp):
    original_level = logger.level
    logger.setLevel(logging.INFO)  # balsa isn't initialized in tests, so set the level the GUI would normally have
    widget = LogWidget()
    yield widget
    widget.detach()
    logger.setLevel(original_level)


def test_log_record_is_displayed(log_widget):
    logger.info('aws s3 sync s3://my-bucket "C:\\backup\\s3\\my-bucket"')
    text = log_widget.log_text_box.toPlainText()
    assert 'aws s3 sync s3://my-bucket "C:\\backup\\s3\\my-bucket"' in text
    assert "INFO" in text
    assert "test_log_widget.py" in text  # the format includes the originating file and line


def test_log_record_from_worker_thread_is_displayed(qapp, log_widget):
    # backups log from worker QThreads - the record crosses to the GUI thread via a queued signal, delivered by the event loop
    worker = threading.Thread(target=lambda: logger.info("from worker thread"), name="worker")
    worker.start()
    worker.join()
    qapp.processEvents()
    assert "from worker thread" in log_widget.log_text_box.toPlainText()


def test_clear_button(log_widget):
    logger.info("some log line")
    assert "some log line" in log_widget.log_text_box.toPlainText()
    log_widget.clear_button.click()
    assert log_widget.log_text_box.toPlainText() == ""


def test_detach_stops_capture(log_widget):
    log_widget.detach()
    logger.info("after detach")
    assert "after detach" not in log_widget.log_text_box.toPlainText()
