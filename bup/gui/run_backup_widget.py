"""
The GUI's "Backup" tab: the Start and Stop buttons, and for each backup type its exclusions and its output.
"""

import threading
from enum import Enum
from datetime import datetime

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGroupBox, QHBoxLayout, QTextEdit, QSplitter, QLabel
from PyQt5.QtCore import Qt, QThread, QTimer
from PyQt5.QtGui import QTextCursor
from balsa import get_logger

from bup import BackupTypes, S3Backup, DynamoDBBackup, GithubBackup, ExclusionPreferences, UITypes, __application_name__
from bup.gui import get_gui_preferences
from bup.gui.gui_util import get_local_time_string, make_row, to_positive_int

max_text_lines = 1000  # lines kept in a display box (the oldest are dropped)

backup_classes = {BackupTypes.S3: S3Backup, BackupTypes.DynamoDB: DynamoDBBackup, BackupTypes.github: GithubBackup}

log = get_logger(__application_name__)


class RunAll(QThread):
    """
    Runs every backup type at the same time, each in its own thread, and waits for them all. A run that was not stopped is recorded as
    the most recent backup, which is what the automatic backup counts from.
    """

    def __init__(self, widget):
        """
        :param widget: the RunBackupWidget whose backups this runs
        """
        self.widget = widget
        super().__init__()

    def run(self):
        threading.current_thread().name = type(self).__name__  # QThreads otherwise show up in logs as "Dummy-N"
        for backup_type in self.widget.backup_engines:
            self.widget.backup_engines[backup_type].start()
        for backup_type in self.widget.backup_engines:
            self.widget.backup_engines[backup_type].wait()
        if not any(self.widget.backup_engines[backup_type].stop_requested for backup_type in self.widget.backup_engines):
            # a stopped run isn't a completed backup - don't reset the auto-backup countdown
            self.widget.most_recent_backup = int(round(datetime.now().timestamp()))


class DisplayTypes(Enum):
    """
    The boxes of a backup type in the Backup tab. The value is the title of the box.
    """

    exclusions = "Exclusions (one per line)"
    log = "Log"
    warnings = "Warnings"
    errors = "Errors"


class DisplayBox(QGroupBox):
    """
    Display for lines of text that can be appended to.
    """

    def __init__(self, name: str, read_only: bool):
        """
        :param name: the title of the box
        :param read_only: False for a box the user types in (the exclusions)
        """
        super().__init__(name)
        self.setLayout(QVBoxLayout())  # only one widget so orientation doesn't matter
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(read_only)
        self.layout().addWidget(self.text_box)
        self.text = []

    def append_text(self, s):
        """
        Add a line, with the time, at the top (most recent activity first). Only the most recent max_text_lines lines are kept.
        """
        # insert at the top (most recent activity first) with cursor operations so each append is O(1),
        # instead of re-rendering the whole buffer for every line
        line = f"{get_local_time_string()} {s}"
        self.text.append(line)
        cursor = self.text_box.textCursor()
        cursor.movePosition(QTextCursor.Start)
        if len(self.text) == 1:
            cursor.insertText(line)
        else:
            cursor.insertText(f"{line}\n")
        if len(self.text) > max_text_lines:
            self.text.pop(0)  # FIFO
            # the oldest line is the last block - remove it and its preceding newline
            cursor.movePosition(QTextCursor.End)
            cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deletePreviousChar()

    def clear_text(self):
        self.text = []
        self.text_box.setText("")


class BackupWidget(QGroupBox):
    """
    GUI for a particular backup type (e.g. S3, DynamoDB, github).  Status text is read-only, but exclusions are edited here.
    """

    def __init__(self, backup_type: BackupTypes):
        self.backup_type = backup_type
        super().__init__(backup_type.name)
        self.setLayout(QVBoxLayout())

        # debounce exclusion writes so we don't hit the DB on every keystroke
        self.exclusions_save_timer = QTimer(self)
        self.exclusions_save_timer.setSingleShot(True)
        self.exclusions_save_timer.setInterval(500)  # ms
        self.exclusions_save_timer.timeout.connect(self.exclusions)

        self.display_boxes = {}
        self.splitter = QSplitter(Qt.Vertical)
        self.layout().addWidget(self.splitter)
        for display_type in DisplayTypes:
            self.display_boxes[display_type] = DisplayBox(display_type.value, display_type is not DisplayTypes.exclusions)
            self.splitter.addWidget(self.display_boxes[display_type])
            if display_type == DisplayTypes.exclusions:
                # read exclusions into the DB
                exclusions = ExclusionPreferences(self.backup_type.name)
                self.display_boxes[display_type].text_box.setText("\n".join(exclusions.get()))
                self.display_boxes[display_type].text_box.setToolTip(
                    "One name per line. '#' starts a comment (whole line or trailing, e.g. 'my-bucket  # note'). Blank lines and surrounding whitespace are ignored."
                )
                self.display_boxes[display_type].text_box.textChanged.connect(self.exclusions_save_timer.start)

    def flush_exclusions(self):
        """
        Write out any pending (debounced) exclusion edits immediately.
        """
        if self.exclusions_save_timer.isActive():
            self.exclusions_save_timer.stop()
            self.exclusions()

    def exclusions(self):
        """
        write exclusions out to the DB
        """
        exclusions = ExclusionPreferences(self.backup_type.name)
        line_list = []
        for line in self.display_boxes[DisplayTypes.exclusions].text_box.toPlainText().splitlines():
            line = line.strip()
            if len(line) > 0:
                line_list.append(line)
        exclusions.set(line_list)


class RunBackupWidget(QWidget):
    """
    "Backup" tab - starts and stops the backups, and shows each backup type's exclusions, output, warnings and errors.
    """

    def __init__(self):
        super().__init__()

        self.most_recent_backup = None

        self.top_level_layout = QVBoxLayout()
        self.setLayout(self.top_level_layout)

        # controls across the top
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.countdown_text = QLabel()
        self.controls_widget = make_row(self.start_button, self.stop_button, "Next backup:", self.countdown_text)

        # status
        self.status_widget = QGroupBox("Status")
        self.status_layout = QHBoxLayout()
        self.status_widget.setLayout(self.status_layout)
        self.backup_status = {}
        self.backup_engines = {}
        self.run_all = RunAll(self)
        self._backup_directory_error_logged = False

        for backup_type in BackupTypes:
            self.backup_status[backup_type] = BackupWidget(backup_type)
            display_boxes = self.backup_status[backup_type].display_boxes
            self.backup_engines[backup_type] = backup_classes[backup_type](
                UITypes.gui, display_boxes[DisplayTypes.log].append_text, display_boxes[DisplayTypes.warnings].append_text, display_boxes[DisplayTypes.errors].append_text
            )

            self.status_layout.addWidget(self.backup_status[backup_type])

        # add all the widgets to the top level layout
        self.top_level_layout.addWidget(self.controls_widget)
        self.top_level_layout.addWidget(self.status_widget)

        self.restore_state()

    def start(self) -> bool:
        """
        Start a backup of every backup type.

        :return: True if it was started, False if it can not be (no backup directory is set)
        """
        preferences = get_gui_preferences()
        if preferences.backup_directory is None:
            # the auto-backup timer may retry every second - only log the first failure, not one per tick
            if not self._backup_directory_error_logged:
                log.error("backup directory not set")
                self._backup_directory_error_logged = True
            return False
        self._backup_directory_error_logged = False
        self.run_all.start()
        return True

    def stop(self):
        """
        Ask every backup to stop (see BupBase.request_stop()).
        """
        for backup_type in self.backup_engines:
            self.backup_engines[backup_type].request_stop()

    def wait_for_threads(self, timeout_ms: int = 5000):
        """
        Wait for a running backup to end (e.g. after stop(), on exit), and terminate its threads if it has not ended in time.
        """
        if self.run_all.isRunning():
            if not self.run_all.wait(timeout_ms):
                for backup_type in self.backup_engines:
                    self.backup_engines[backup_type].terminate()
                self.run_all.terminate()

    def get_layout_key(self, backup_type: BackupTypes, display_type: DisplayTypes, height_width: str):
        """
        :param height_width: "height" or "width"
        :return: the name of the preference that the height or width of a display box is saved as
        """
        return f"{backup_type.name}_{display_type.name}_{height_width}"

    def save_state(self):
        """
        Save the exclusions, the sizes of the display boxes and the time of the most recent backup, for the next time bup is run.
        """
        preferences = get_gui_preferences()
        for backup_type in BackupTypes:
            self.backup_status[backup_type].flush_exclusions()
        for backup_type in BackupTypes:
            for display_type in DisplayTypes:
                setattr(preferences, self.get_layout_key(backup_type, display_type, "height"), self.backup_status[backup_type].display_boxes[display_type].height())
                setattr(preferences, self.get_layout_key(backup_type, display_type, "width"), self.backup_status[backup_type].display_boxes[display_type].width())
        preferences.most_recent_backup = self.most_recent_backup

    def restore_state(self):
        """
        Restore what save_state() saved.
        """
        preferences = get_gui_preferences()
        for backup_type in BackupTypes:
            for display_type in DisplayTypes:
                height = to_positive_int(getattr(preferences, self.get_layout_key(backup_type, display_type, "height"), None))
                width = to_positive_int(getattr(preferences, self.get_layout_key(backup_type, display_type, "width"), None))
                # make sure all windows come up as visible, even if not set or the user has reduced them to zero
                if height is not None and width is not None:
                    self.backup_status[backup_type].display_boxes[display_type].resize(width, height)

        self.most_recent_backup = preferences.most_recent_backup
