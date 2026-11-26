"""
The GUI's "Log" tab: the application log, in a pane per log source.
"""

import logging

from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QGroupBox, QSplitter
from balsa import get_logger

from bup import __application_name__
from bup.log_routing import LogSources, get_log_source, log_line_format
from bup.gui import get_gui_preferences
from bup.gui.gui_util import make_row

log = get_logger(__application_name__)

max_log_lines = 10000  # lines kept in a log pane (the oldest are dropped)

minimum_pane_height = 50  # pixels


class QtLogEmitter(QObject):
    """
    Has the signal that carries log lines to the GUI thread (a logging.Handler is not a QObject, so it can not have one itself).
    """

    log_line_signal = pyqtSignal(str, str)  # (LogSources value, formatted log line)


class QtLogHandler(logging.Handler):
    """
    logging handler that forwards formatted log records to the GUI via a Qt signal
    (backups log from worker QThreads, and Qt widgets may only be touched from the GUI thread - the signal connection handles the thread hop)
    """

    def __init__(self):
        """
        Make the handler, whose emitter.log_line_signal is what to connect to.
        """
        super().__init__()
        self.emitter = QtLogEmitter()
        self.setFormatter(logging.Formatter(log_line_format))

    def emit(self, record: logging.LogRecord):
        """
        Send a log record on its way to the GUI thread (called by logging, in the thread that logged the record).
        """
        self.emitter.log_line_signal.emit(get_log_source(record).value, self.format(record))


class LogPane(QGroupBox):
    """
    One log source's pane - a titled, read-only, monospaced, non-wrapping text view with FIFO line trimming.
    """

    def __init__(self, name: str):
        """
        :param name: the title of the pane
        """
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
    "Log" tab - detailed application log (e.g. every S3 object a sync downloads), fed by all log records of this application's logger,
    with a separate pane per backup type plus one for the rest of the application.
    """

    def __init__(self):
        """
        Make the tab with its panes, at the heights they had when bup was last closed, and start capturing log records.
        """
        super().__init__()
        self.setLayout(QVBoxLayout())

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.controls_widget = make_row(self.clear_button)

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

        self.restore_state()

    def get_pane_height_key(self, log_source: LogSources) -> str:
        """
        :return: the name of the preference that the height of a log source's pane is saved as
        """
        return f"log_pane_{log_source.name}_height"

    def save_state(self):
        """
        Save the heights of the panes, for the next time bup is run.
        """
        preferences = get_gui_preferences()
        for log_source, pane_height in zip(LogSources, self.splitter.sizes()):
            setattr(preferences, self.get_pane_height_key(log_source), pane_height)

    def restore_state(self):
        """
        Restore the heights of the panes that save_state() saved.
        """
        preferences = get_gui_preferences()
        pane_heights = []
        for log_source in LogSources:
            pane_height = getattr(preferences, self.get_pane_height_key(log_source))
            # make sure every pane comes up visible, even if not set or the user has collapsed it to zero
            if pane_height is None or int(pane_height) < minimum_pane_height:
                pane_height = minimum_pane_height
            pane_heights.append(int(pane_height))
        self.splitter.setSizes(pane_heights)

    def append_log_line(self, log_source_value: str, line: str):
        """
        Add a log line to the pane of its log source. Connected to the log handler's signal, so it runs in the GUI thread.
        """
        self.log_panes[LogSources(log_source_value)].text_box.appendPlainText(line)

    def clear(self):
        """
        Empty every pane.
        """
        for log_pane in self.log_panes.values():
            log_pane.text_box.clear()

    def detach(self):
        """
        Stop capturing log records. Call before the widget is destroyed so the handler doesn't write into a dead widget.
        """
        logging.getLogger(__application_name__).removeHandler(self.log_handler)
