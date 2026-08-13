import logging

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton
from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)

max_log_lines = 10000

log_line_format = "%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(threadName)s %(message)s"


class QtLogEmitter(QObject):
    log_line_signal = pyqtSignal(str)


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
        self.emitter.log_line_signal.emit(self.format(record))


class LogWidget(QWidget):
    """
    "Log" tab - detailed application log (e.g. the full AWS CLI command lines), fed by all log records of this application's logger
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

        self.log_text_box = QPlainTextEdit()
        self.log_text_box.setReadOnly(True)
        self.log_text_box.setMaximumBlockCount(max_log_lines)  # FIFO - drops the oldest lines
        self.log_text_box.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_text_box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.clear_button.clicked.connect(self.log_text_box.clear)

        self.layout().addWidget(self.controls_widget)
        self.layout().addWidget(self.log_text_box)

        self.log_handler = QtLogHandler()
        self.log_handler.setLevel(logging.DEBUG)  # display everything the logger's own level lets through (e.g. DEBUG with the verbose preference)
        self.log_handler.emitter.log_line_signal.connect(self.log_text_box.appendPlainText)
        logging.getLogger(__application_name__).addHandler(self.log_handler)

    def detach(self):
        """
        Stop capturing log records. Call before the widget is destroyed so the handler doesn't write into a dead widget.
        """
        logging.getLogger(__application_name__).removeHandler(self.log_handler)
