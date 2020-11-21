from enum import Enum

from PyQt5.QtWidgets import QApplication, QDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QLabel
from balsa import Balsa
from ismain import is_main

from bup import __application_name__, __author__, __version__


class BackupTypes(Enum):
    S3 = 0
    DynamoDB = 1
    github = 2


class StatusWidget(QGroupBox):
    def __init__(self, name: str):
        super().__init__(name)


class BupGUI(QDialog):
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


def gui_main():
    app = QApplication([])
    bup_gui = BupGUI()
    bup_gui.show()
    app.exec_()


if is_main():
    balsa = Balsa(__application_name__, __author__)
    balsa.init_logger()
    gui_main()
