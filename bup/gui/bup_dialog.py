from enum import Enum
from pathlib import Path

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QGroupBox, QTextEdit, QTabWidget

from bup import __application_name__, __version__, BupBase, S3Backup, DynamoDBBackup, GithubBackup, BackupTypes
from bup.gui import PreferencesWidget, BupPreferences, RunBackupWidget


class BupDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{__application_name__} ({__version__})")

        self.setLayout(QVBoxLayout())

        self.tab_widget = QTabWidget()
        self.layout().addWidget(self.tab_widget)

        self.tab_widget.addTab(RunBackupWidget(), "Backup")
        self.tab_widget.addTab(PreferencesWidget(), "Preferences")
