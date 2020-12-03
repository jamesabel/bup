from enum import Enum

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGroupBox, QHBoxLayout, QTextEdit

from bup import BackupTypes, BupBase, S3Backup, DynamoDBBackup, GithubBackup
from bup.gui import get_preferences

max_text_lines = 100

backup_classes = {BackupTypes.S3: S3Backup, BackupTypes.DynamoDB: DynamoDBBackup, BackupTypes.github: GithubBackup}


class DisplayTypes(Enum):
    exclusions = "Exclusions (one per line)"
    log = "Log"
    warnings = "Warnings"
    errors = "Errors"


class DisplayBox(QGroupBox):
    def __init__(self, name: str, read_only: bool):
        super().__init__(name)
        self.setLayout(QVBoxLayout())
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(read_only)
        self.layout().addWidget(self.text_box)
        self.text = []

    def append_text(self, s):
        self.text.append(s)
        if len(self.text) > max_text_lines:
            self.text.pop(0)  # FIFO
        self.text_box.setText("\n".join(self.text))

    def clear_text(self):
        self.text = []
        self.text_box.setText("")


class BackupWidget(QGroupBox):
    def __init__(self, backup_type: BackupTypes):
        super().__init__(backup_type.name)
        self.backup_engine = None  # set after init
        self.setLayout(QVBoxLayout())

        self.display_boxes = {}
        for display_type in DisplayTypes:
            self.display_boxes[display_type] = DisplayBox(display_type.value, display_type is not DisplayTypes.exclusions)
            self.layout().addWidget(self.display_boxes[display_type])


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
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause)
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

            self.backup_engines[backup_type] = backup_classes[backup_type](preferences.backup_directory,
                                                                           self.backup_status[backup_type].display_boxes[DisplayTypes.log].append_text,
                                                                           self.backup_status[backup_type].display_boxes[DisplayTypes.warnings].append_text,
                                                                           self.backup_status[backup_type].display_boxes[DisplayTypes.errors].append_text,
                                                                           aws_profile = preferences.aws_profile)
            self.backup_status[backup_type].backup_engine = self.backup_engines[backup_type]
            self.status_layout.addWidget(self.backup_status[backup_type])

        # add all the widgets to the top level layout
        self.top_level_layout.addWidget(self.controls_widget)
        self.top_level_layout.addWidget(self.status_widget)

    def start(self):
        for backup_type in self.backup_engines:
            self.backup_engines[backup_type].run()

    def pause(self):
        pass

    def stop(self):
        for backup_type in self.backup_engines:
            self.backup_engines[backup_type].terminate()
