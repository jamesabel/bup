"""
The main window of the GUI: a dialog with a tab per function, which also runs the automatic backup schedule.
"""

from datetime import datetime, timedelta
import ctypes
import os

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QMessageBox
from PyQt5.QtGui import QCloseEvent, QIcon
from PyQt5.QtCore import QTimer, Qt

from bup import __application_name__, __version__, __author__, get_preferences, UITypes
from bup.gui.gui_util import to_positive_int
from bup.gui import PreferencesWidget, RunBackupWidget, LogWidget, TransferWidget, BupAbout, get_icon_path


class BupDialog(QDialog):
    """
    The main window: the Backup, Preferences, Log, Transfer and About tabs.
    """

    def __init__(self):
        super().__init__()

        self.setWindowIcon(QIcon(str(get_icon_path("png"))))

        # set task bar icon (Windows only)
        if os.name == "nt":
            bup_app_id = f"{__author__}.{__application_name__}.{__version__}"  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(bup_app_id)

        self.setWindowTitle(f"{__application_name__} ({__version__})")
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)

        self.setLayout(QVBoxLayout())

        self.tab_widget = QTabWidget()
        self.layout().addWidget(self.tab_widget)

        self.run_backup_widget = RunBackupWidget()
        self.preferences_widget = PreferencesWidget()
        self.log_widget = LogWidget()
        self.transfer_widget = TransferWidget()
        self.about_widget = BupAbout()

        self.tab_widget.addTab(self.run_backup_widget, "Backup")
        self.tab_widget.addTab(self.preferences_widget, "Preferences")
        self.tab_widget.addTab(self.log_widget, "Log")
        self.tab_widget.addTab(self.transfer_widget, "Transfer")
        self.tab_widget.addTab(self.about_widget, "About")

        preferences = get_preferences(UITypes.gui)
        width = to_positive_int(preferences.width)
        height = to_positive_int(preferences.height)
        if width is not None and height is not None:
            self.resize(width, height)  # as it was when bup was last closed

        self.autobackup_timer = QTimer()
        self.autobackup_timer.timeout.connect(self.autobackup_tick)
        self.autobackup_timer.start(1000)  # once a second
        self.tick_count = 0

    def autobackup_tick(self):
        """
        Called once a second: show when the next automatic backup is (or that a backup is running), and start it when it is due.
        A backup is due when the backup period has passed since the most recent backup, or right away if there has not been one.
        """
        if self.preferences_widget.automatic_backup_enable_check_box.isChecked():
            backup_period = self.preferences_widget.automatic_backup_period.value()  # QSpinBox guarantees an int
            if backup_period <= 0:
                self.run_backup_widget.countdown_text.setText("(automatic backup not set)")
            else:
                now = datetime.now()
                backup_period_time_delta = timedelta(hours=backup_period)
                if self.run_backup_widget.most_recent_backup is None:
                    # no backup on record - start one right away
                    if not self.run_backup_widget.run_all.isRunning():
                        if self.run_backup_widget.start():
                            self.run_backup_widget.countdown_text.setText("(starting first automatic backup)")
                        else:
                            self.run_backup_widget.countdown_text.setText("(backup directory not set)")
                else:
                    most_recent_backup = datetime.fromtimestamp(self.run_backup_widget.most_recent_backup)
                    next_backup_date_time = most_recent_backup + backup_period_time_delta
                    next_backup_time_delta = next_backup_date_time - now
                    next_backup_time_delta_second_granularity = timedelta(days=next_backup_time_delta.days, seconds=next_backup_time_delta.seconds)  # don't display fractions of a second
                    self.run_backup_widget.countdown_text.setText(f"{next_backup_date_time.strftime('%m-%d-%Y %H:%M:%S')} (in {str(next_backup_time_delta_second_granularity)})")
                    if next_backup_time_delta.total_seconds() <= 0.0 and not self.run_backup_widget.run_all.isRunning():
                        # timer is up - start the backup
                        if not self.run_backup_widget.start():
                            self.run_backup_widget.countdown_text.setText("(backup directory not set)")

            if self.run_backup_widget.run_all.isRunning():
                ticks = "." * (self.tick_count % 4)
                self.run_backup_widget.countdown_text.setText(f"running {ticks}")
        else:
            self.run_backup_widget.countdown_text.setText("(automatic backup not enabled)")
        self.tick_count += 1

    def closeEvent(self, a0: QCloseEvent) -> None:
        """
        The window is being closed: ask first if a backup is running, then stop the backups and save the state of the GUI.

        :param a0: the close event (the name is the one PyQt5 gives this parameter of QDialog.closeEvent)
        """
        if self.run_backup_widget.run_all.isRunning():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Backup In Progress")
            msg_box.setText("A backup is currently running.")
            msg_box.setInformativeText("Do you want to stop the backup and exit, or cancel and keep running?")
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.addButton("Stop and Exit", QMessageBox.DestructiveRole)
            cancel_button = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.setDefaultButton(cancel_button)
            msg_box.exec_()

            if msg_box.clickedButton() == cancel_button:
                a0.ignore()
                return

        self.autobackup_timer.stop()
        self.run_backup_widget.stop()
        self.run_backup_widget.wait_for_threads(5000)
        self.log_widget.detach()
        self.log_widget.save_state()
        self.run_backup_widget.save_state()
        preferences = get_preferences(UITypes.gui)
        preferences.width = self.width()
        preferences.height = self.height()
