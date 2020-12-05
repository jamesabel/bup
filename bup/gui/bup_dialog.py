from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget
from PyQt5.QtGui import QCloseEvent

from bup import __application_name__, __version__, get_preferences, UITypes
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

        preferences = get_preferences(UITypes.gui)
        width = preferences.width
        height = preferences.height
        if width is not None and width > 0 and height is not None and height > 0:
            self.resize(preferences.width, preferences.height)

    def closeEvent(self, close_event: QCloseEvent) -> None:
        self.run_backup_widget.save_layout_dimensions()
        preferences = get_preferences(UITypes.gui)
        preferences.width = self.width()
        preferences.height = self.height()
