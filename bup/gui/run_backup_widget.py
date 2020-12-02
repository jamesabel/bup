from enum import Enum

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QGroupBox, QHBoxLayout, QTextEdit

from bup import BackupTypes, BupBase, backup_classes, __application_name__, __author__
from bup.gui import BupPreferences

max_text_lines = 100


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

    def append_text(self, s: str):
        self.text.append(s)
        if len(self.text) > max_text_lines:
            self.text.pop(0)  # FIFO
        self.text_box.setText("\n".join(self.text))

    def clear_text(self):
        self.text = []
        self.text_box.setText("")


class BackupWidget(QGroupBox):
    def __init__(self, backup_type: BackupTypes, backup_engine: BupBase):
        super().__init__(backup_type.name)
        self.backup_engine = backup_engine
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
        preferences = BupPreferences(__application_name__, __author__)
        for backup_type in BackupTypes:
            # todo: fill in options here
            #engine = backup_classes[backup_type](preferences.backup_directory, preferences.aws_profile)
            #self.backup_engines[backup_type] = print

            self.backup_status[backup_type] = BackupWidget(backup_type, lambda x:x)  # todo: pass in the backup engine
            self.backup_status[backup_type].setLayout(QHBoxLayout())
            self.status_layout.addWidget(self.backup_status[backup_type])

        # add all the widgets to the top level layout
        self.top_level_layout.addWidget(self.controls_widget)
        self.top_level_layout.addWidget(self.status_widget)

    def start(self):
        pass

    def pause(self):
        pass

    def stop(self):
        pass
