from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget
from PyQt5.QtGui import QCloseEvent

from bup import __application_name__, __version__
from bup.gui import PreferencesWidget, RunBackupWidget


class BupDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{__application_name__} ({__version__})")

        self.setLayout(QVBoxLayout())

        self.tab_widget = QTabWidget()
        self.layout().addWidget(self.tab_widget)

        self.run_backup_widget = RunBackupWidget()

        self.tab_widget.addTab(self.run_backup_widget, "Backup")
        self.tab_widget.addTab(PreferencesWidget(), "Preferences")

    def closeEvent(self, close_event: QCloseEvent) -> None:
        self.run_backup_widget.save_layout_dimensions()
