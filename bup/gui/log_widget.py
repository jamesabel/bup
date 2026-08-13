import logging
from enum import Enum

from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QGroupBox, QSplitter
from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)

max_log_lines = 10000

log_line_format = "%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(threadName)s %(message)s"


class LogSources(Enum):
    s3 = "AWS S3"
    dynamodb = "DynamoDB"
    github = "GitHub"
    application = "Application"


# records are routed to a pane by the source file they were logged from (all of bup logs to the same application logger)
log_sources_by_filename = {
    "s3_backup.py": LogSources.s3,
    "aws_cli.py": LogSources.s3,
    "dynamodb_backup.py": LogSources.dynamodb,
    "github_backup.py": LogSources.github,
}


def get_log_source(record: logging.LogRecord) -> LogSources:
    return log_sources_by_filename.get(record.filename, LogSources.application)


class QtLogEmitter(QObject):
    log_line_signal = pyqtSignal(str, str)  # (LogSources value, formatted log line)


class QtLogHandler(logging.Handler):
    """
    logging handler that forwards formatted log records to the GUI via a Qt signal
    (backups log from worker QThreads, and Qt widgets may only be touched from the GUI thread - the signal connection handles the thread hop)
    """

    def __init__(self):
        super().__init__()
        self.emitter = QtLogEmitter()
        self.setFormatter(logging.Formatter(log_line_format))

    def emit(self, record: logging.LogRecord):
        self.emitter.log_line_signal.emit(get_log_source(record).value, self.format(record))


class LogPane(QGroupBox):
    """
    One log source's pane - a titled, read-only, monospaced, non-wrapping text view with FIFO line trimming.
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.setLayout(QVBoxLayout())
        self.text_box = QPlainTextEdit()
        self.text_box.setReadOnly(True)
        self.text_box.setMaximumBlockCount(max_log_lines)  # FIFO - drops the oldest lines
        self.text_box.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text_box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.layout().addWidget(self.text_box)


class LogWidget(QWidget):
    """
    "Log" tab - detailed application log (e.g. the full AWS CLI command lines), fed by all log records of this application's logger,
    with a separate pane per backup type plus one for the rest of the application.
    """

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        self.controls_widget = QWidget()
        self.controls_layout = QHBoxLayout()
        self.controls_widget.setLayout(self.controls_layout)
        self.clear_button = QPushButton("Clear")
        self.controls_layout.addWidget(self.clear_button)
        self.controls_layout.addStretch()
        self.clear_button.clicked.connect(self.clear)

        self.splitter = QSplitter(Qt.Vertical)
        self.log_panes = {}
        for log_source in LogSources:
            self.log_panes[log_source] = LogPane(log_source.value)
            self.splitter.addWidget(self.log_panes[log_source])

        self.layout().addWidget(self.controls_widget)
        self.layout().addWidget(self.splitter)

        self.log_handler = QtLogHandler()
        self.log_handler.setLevel(logging.DEBUG)  # display everything the logger's own level lets through (e.g. DEBUG with the verbose preference)
        self.log_handler.emitter.log_line_signal.connect(self.append_log_line)
        logging.getLogger(__application_name__).addHandler(self.log_handler)

    def append_log_line(self, log_source_value: str, line: str):
        self.log_panes[LogSources(log_source_value)].text_box.appendPlainText(line)

    def clear(self):
        for log_pane in self.log_panes.values():
            log_pane.text_box.clear()

    def detach(self):
        """
        Stop capturing log records. Call before the widget is destroyed so the handler doesn't write into a dead widget.
        """
        logging.getLogger(__application_name__).removeHandler(self.log_handler)
