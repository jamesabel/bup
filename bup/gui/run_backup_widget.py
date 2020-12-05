from enum import Enum
from datetime import datetime

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGroupBox, QHBoxLayout, QTextEdit, QSplitter
from PyQt5.QtCore import Qt
from balsa import get_logger

from bup import BackupTypes, S3Backup, DynamoDBBackup, GithubBackup, ExclusionPreferences, UITypes, __application_name__
from bup.gui import get_gui_preferences

max_text_lines = 100

backup_classes = {BackupTypes.S3: S3Backup, BackupTypes.DynamoDB: DynamoDBBackup, BackupTypes.github: GithubBackup}

log = get_logger(__application_name__)


def get_local_time_string() -> str:
    return datetime.now().astimezone().isoformat()


class DisplayTypes(Enum):
    exclusions = "Exclusions (one per line)"
    log = "Log"
    warnings = "Warnings"
    errors = "Errors"


class DisplayBox(QGroupBox):
    """
    Display for lines of text that can be appended to.
    """

    def __init__(self, name: str, read_only: bool):
        super().__init__(name)
        self.setLayout(QVBoxLayout())  # only one widget so orientation doesn't matter
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(read_only)
        self.layout().addWidget(self.text_box)
        self.text = []

    def append_text(self, s):
        self.text.append(f"{get_local_time_string()} {s}")
        if len(self.text) > max_text_lines:
            self.text.pop(0)  # FIFO
        self.text_box.setText("\n".join(reversed(self.text)))

    def clear_text(self):
        self.text = []
        self.text_box.setText("")


class BackupWidget(QGroupBox):
    """
    GUI for a particular backup type (e.g. S3, DynamoDB, github).  Status is read-only, but exclusions are edited here.
    """

    def __init__(self, backup_type: BackupTypes):
        self.backup_type = backup_type
        super().__init__(backup_type.name)
        self.setLayout(QVBoxLayout())

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
                self.display_boxes[display_type].text_box.textChanged.connect(self.exclusions)
            else:
                self.display_boxes[display_type].text_box.setReadOnly(True)

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
    def __init__(self):
        super().__init__()

        self.top_level_layout = QVBoxLayout()
        self.setLayout(self.top_level_layout)

        # controls across the top
        self.controls_widget = QWidget()
        self.controls_layout = QHBoxLayout()
        self.controls_widget.setLayout(self.controls_layout)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)

        self.controls_layout.addWidget(self.start_button)
        self.controls_layout.addWidget(self.stop_button)

        # status
        self.status_widget = QGroupBox("Status")
        self.status_layout = QHBoxLayout()
        self.status_widget.setLayout(self.status_layout)
        self.backup_status = {}
        self.backup_engines = {}

        for backup_type in BackupTypes:
            self.backup_status[backup_type] = BackupWidget(backup_type)
            self.backup_status[backup_type].setLayout(QHBoxLayout())

            display_boxes = self.backup_status[backup_type].display_boxes
            self.backup_engines[backup_type] = backup_classes[backup_type](
                UITypes.gui, display_boxes[DisplayTypes.log].append_text, display_boxes[DisplayTypes.warnings].append_text, display_boxes[DisplayTypes.errors].append_text
            )

            self.status_layout.addWidget(self.backup_status[backup_type])

        # add all the widgets to the top level layout
        self.top_level_layout.addWidget(self.controls_widget)
        self.top_level_layout.addWidget(self.status_widget)

        self.set_layout_dimensions()

    def start(self):
        preferences = get_gui_preferences()
        if preferences.backup_directory is None:
            log.error("backup directory not set")
        else:
            for backup_type in self.backup_engines:
                self.backup_engines[backup_type].start()

    def stop(self):
        for backup_type in self.backup_engines:
            self.backup_engines[backup_type].terminate()

    def get_layout_key(self, backup_type: BackupTypes, display_type: DisplayTypes, height_width: str):
        return f"{backup_type.name}_{display_type.name}_{height_width}"

    def save_layout_dimensions(self):
        preferences = get_gui_preferences()
        for backup_type in BackupTypes:
            for display_type in DisplayTypes:
                setattr(preferences, self.get_layout_key(backup_type, display_type, "height"), self.backup_status[backup_type].display_boxes[display_type].height())
                setattr(preferences, self.get_layout_key(backup_type, display_type, "width"), self.backup_status[backup_type].display_boxes[display_type].width())

    def set_layout_dimensions(self):
        preferences = get_gui_preferences()
        for backup_type in BackupTypes:
            for display_type in DisplayTypes:

                height = int(getattr(preferences, self.get_layout_key(backup_type, display_type, "height"), 0))
                width = int(getattr(preferences, self.get_layout_key(backup_type, display_type, "width"), 0))
                # make sure all windows come up as visible, even if the user has reduced them to zero
                if height > 0 and width > 0:
                    self.backup_status[backup_type].display_boxes[display_type].resize(width, height)
