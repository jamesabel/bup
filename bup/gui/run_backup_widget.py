from enum import Enum
from datetime import datetime

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGroupBox, QHBoxLayout, QTextEdit

from bup import BackupTypes, S3Backup, DynamoDBBackup, GithubBackup
from bup import get_preferences, ExclusionPreferences

max_text_lines = 100

backup_classes = {BackupTypes.S3: S3Backup, BackupTypes.DynamoDB: DynamoDBBackup, BackupTypes.github: GithubBackup}


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
        self.setLayout(QVBoxLayout())
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(read_only)
        self.layout().addWidget(self.text_box)
        self.text = []

    def append_text(self, s):
        self.text.append(f"{get_local_time_string()} {s}")
        if len(self.text) > max_text_lines:
            self.text.pop(0)  # FIFO
        self.text_box.setText(f"\n".join(reversed(self.text)))

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
        self.backup_engine = None  # set after init
        self.setLayout(QVBoxLayout())

        self.display_boxes = {}
        for display_type in DisplayTypes:
            self.display_boxes[display_type] = DisplayBox(display_type.value, display_type is not DisplayTypes.exclusions)
            self.layout().addWidget(self.display_boxes[display_type])
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
        self.controls_layout.addWidget(self.pause_button)
        self.controls_layout.addWidget(self.stop_button)

        # status
        self.status_widget = QGroupBox("Status")
        self.status_layout = QHBoxLayout()
        self.status_widget.setLayout(self.status_layout)
        self.backup_status = {}
        self.backup_engines = {}

        preferences = get_preferences()

        for backup_type in BackupTypes:
            self.backup_status[backup_type] = BackupWidget(backup_type)
            self.backup_status[backup_type].setLayout(QHBoxLayout())

            self.backup_engines[backup_type] = backup_classes[backup_type](self.backup_status[backup_type].display_boxes[DisplayTypes.log].append_text,
                                                                           self.backup_status[backup_type].display_boxes[DisplayTypes.warnings].append_text,
                                                                           self.backup_status[backup_type].display_boxes[DisplayTypes.errors].append_text,
                                                                           )

            self.backup_status[backup_type].backup_engine = self.backup_engines[backup_type]
            self.status_layout.addWidget(self.backup_status[backup_type])

        # add all the widgets to the top level layout
        self.top_level_layout.addWidget(self.controls_widget)
        self.top_level_layout.addWidget(self.status_widget)

    def start(self):
        for backup_type in self.backup_engines:
            self.backup_engines[backup_type].start()

    def stop(self):
        for backup_type in self.backup_engines:
            self.backup_engines[backup_type].terminate()
