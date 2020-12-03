from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget

from bup import __application_name__, __version__
from bup.gui import PreferencesWidget, RunBackupWidget


class BupDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{__application_name__} ({__version__})")

        self.setLayout(QVBoxLayout())

        self.tab_widget = QTabWidget()
        self.layout().addWidget(self.tab_widget)

        self.tab_widget.addTab(RunBackupWidget(), "Backup")
        self.tab_widget.addTab(PreferencesWidget(), "Preferences")
