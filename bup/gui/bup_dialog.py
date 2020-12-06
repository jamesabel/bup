from datetime import datetime, timedelta
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtCore import QTimer

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
        self.preferences_widget = PreferencesWidget()

        self.tab_widget.addTab(self.run_backup_widget, "Backup")
        self.tab_widget.addTab(self.preferences_widget, "Preferences")

        preferences = get_preferences(UITypes.gui)
        width = preferences.width
        height = preferences.height
        if width is not None and width > 0 and height is not None and height > 0:
            self.resize(preferences.width, preferences.height)

        self.autobackup_timer = QTimer()
        self.autobackup_timer.timeout.connect(self.autobackup_tick)
        self.autobackup_timer.start(1000)  # once a second

    def autobackup_tick(self):
        if self.preferences_widget.automatic_backup_enable_check_box.isChecked():
            try:
                backup_period = int(self.preferences_widget.automatic_backup_period.text())
            except ValueError:
                backup_period = None
            if backup_period is None:
                self.run_backup_widget.countdown_text.setText("(automatic backup not set)")
            else:
                now = datetime.now()
                backup_period_time_delta = timedelta(hours=backup_period)
                if self.run_backup_widget.most_recent_backup is None:
                    # first time run
                    self.run_backup_widget.start()
                else:
                    most_recent_backup = datetime.fromtimestamp(self.run_backup_widget.most_recent_backup)
                    next_backup_date_time = most_recent_backup + backup_period_time_delta
                    next_backup_time_delta = next_backup_date_time - now
                    next_backup_time_delta_second_granularity = timedelta(days=next_backup_time_delta.days, seconds=next_backup_time_delta.seconds)  # don't display fractions of a second
                    self.run_backup_widget.countdown_text.setText(f"{next_backup_date_time.strftime('%m-%d-%Y %H:%M:%S')} (in {str(next_backup_time_delta_second_granularity)})")
                    if next_backup_time_delta.total_seconds() <= 0.0:
                        # timer is up - start the backup
                        self.run_backup_widget.start()
        else:
            self.run_backup_widget.countdown_text.setText(f"(automatic backup not enabled)")



    def closeEvent(self, close_event: QCloseEvent) -> None:
        self.run_backup_widget.save_state()
        preferences = get_preferences(UITypes.gui)
        preferences.width = self.width()
        preferences.height = self.height()
