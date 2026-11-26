"""
The main window of the GUI: a dialog with a tab per function and a status line, which also runs the automatic backup schedule.
"""

from datetime import datetime, timedelta
import ctypes
import os
from typing import Optional

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QMessageBox, QLabel
from PyQt5.QtGui import QCloseEvent, QIcon
from PyQt5.QtCore import QTimer, Qt

from bup import __application_name__, __version__, __author__, get_preferences, UITypes
from bup.backup_history import get_interrupted_message, mark_interrupted_backups
from bup.gui.gui_util import to_positive_int
from bup.gui.status_line import status_emitter
from bup.gui import PreferencesWidget, RunBackupWidget, LogWidget, TransferWidget, HistoryWidget, BupAbout, get_icon_path


class BupDialog(QDialog):
    """
    The main window: the Backup, Preferences, Log, Transfer, History and About tabs, and below them the status line, which says
    so if a backup was cut short the last time bup ran (e.g. by a system crash).
    """

    def __init__(self):
        """
        Make the main window with its tabs, as it was when bup was last closed, and start the timer of the automatic backup.
        """
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

        # A backup that was running when bup or the system died is still on record as running. Find those before the History tab
        # reads the history, so that it shows them as not finished, and tell the user in the status line.
        interrupted_message = get_interrupted_message(mark_interrupted_backups())

        self.run_backup_widget = RunBackupWidget()
        self.preferences_widget = PreferencesWidget()
        self.log_widget = LogWidget()
        self.transfer_widget = TransferWidget()
        self.history_widget = HistoryWidget()
        self.about_widget = BupAbout()

        self.tab_widget.addTab(self.run_backup_widget, "Backup")
        self.tab_widget.addTab(self.preferences_widget, "Preferences")
        self.tab_widget.addTab(self.log_widget, "Log")
        self.tab_widget.addTab(self.transfer_widget, "Transfer")
        self.tab_widget.addTab(self.history_widget, "History")
        self.tab_widget.addTab(self.about_widget, "About")

        self.status_line = QLabel(interrupted_message)
        self.status_line.setWordWrap(True)
        self.layout().addWidget(self.status_line)
        status_emitter.status_signal.connect(self.status_line.setText)  # what the tabs have to say (e.g. that a backup was stopped)

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
        """
        if self.preferences_widget.automatic_backup_enable_check_box.isChecked():
            countdown_text = self.start_backup_if_due()
            if self.run_backup_widget.run_all.isRunning() or countdown_text is None:
                # a backup that was asked to stop is still running until it gets to where it stops - say that it is on its way out
                activity = "stopping" if self.run_backup_widget.run_all.stop_requested else "running"
                countdown_text = f"{activity} {'.' * (self.tick_count % 4)}"
        else:
            countdown_text = "(automatic backup not enabled)"
        self.run_backup_widget.countdown_text.setText(countdown_text)
        self.tick_count += 1

    def start_backup_if_due(self) -> Optional[str]:
        """
        Start the automatic backup if it is due and no backup is running. A backup is due when the backup period has passed since the
        most recent backup ended (completed or stopped by the user), or right away if there has not been one.

        :return: what to show as the next backup while no backup is running: when it is, or why there is none. None if there has
          not been a backup and one is running, which is all there is to show.
        """
        run_backup_widget = self.run_backup_widget
        backup_period = self.preferences_widget.automatic_backup_period.value()  # hours (QSpinBox guarantees an int)
        if backup_period <= 0:
            return "(automatic backup not set)"

        if run_backup_widget.most_recent_backup is None:
            # no backup on record - start one right away
            if run_backup_widget.run_all.isRunning():
                return None
            return "(starting first automatic backup)" if run_backup_widget.start() else "(backup directory not set)"

        next_backup = datetime.fromtimestamp(run_backup_widget.most_recent_backup) + timedelta(hours=backup_period)
        time_left = next_backup - datetime.now()
        if time_left.total_seconds() <= 0.0 and not run_backup_widget.run_all.isRunning() and not run_backup_widget.start():
            return "(backup directory not set)"  # the timer is up, but the backup can not be started
        time_left_to_the_second = timedelta(days=time_left.days, seconds=time_left.seconds)  # don't display fractions of a second
        return f"{next_backup.strftime('%m-%d-%Y %H:%M:%S')} (in {time_left_to_the_second})"

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
