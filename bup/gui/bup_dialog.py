from enum import Enum

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QTextEdit

from bup import __application_name__, __version__

max_text_lines = 100


class BackupTypes(Enum):
    S3 = 0
    DynamoDB = 1
    github = 2


class DisplayTypes(Enum):
    log = "Log"
    warnings = "Warnings"
    errors = "Errors"


class DisplayBox(QGroupBox):
    def __init__(self, name: str):
        super().__init__(name)
        self.setLayout(QVBoxLayout())
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)
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


class StatusWidget(QGroupBox):
    def __init__(self, name: str):
        super().__init__(name)
        self.setLayout(QVBoxLayout())

        self.display_boxes = {}
        for display_type in DisplayTypes:
            self.display_boxes[display_type] = DisplayBox(display_type.value)
            self.layout().addWidget(self.display_boxes[display_type])


class BupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__application_name__} ({__version__})")

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
        for backup_type in BackupTypes:
            self.backup_status[backup_type] = StatusWidget(backup_type.name)
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
