"""
The GUI's "History" tab: the backup runs on record - when each started and ended, how it ended, what it received and its errors.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List

from PyQt5.QtGui import QShowEvent
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from balsa import get_logger

from bup import __application_name__
from bup.backup_history import BackupRun, format_time, get_backup_history, history_emitter
from bup.transfer import format_size, format_cost

log = get_logger(__application_name__)

max_history_rows = 1000  # the most recent runs shown (the database keeps them all)

columns = ["Started", "Ended", "Duration", "Backup", "Run from", "Status", "Received", "Average rate", "Read units", "Approx. cost", "Errors", "Warnings", "Error details"]

history_note = (
    "One row per backup type each time it is run, from the GUI or the command line, most recent first. A backup that did not finish "
    "was cut short: bup was closed or crashed, or the system crashed or was shut down, while it was running. Costs are approximate "
    "(see the Transfer tab)."
)


def format_end_time(started: float, ended: float) -> str:
    """
    :param started: when a backup run started (epoch seconds)
    :param ended: when it ended (epoch seconds)
    :return: when it ended in local time: only the time of day if that is on the day it started (its row has that date already)
    """
    if datetime.fromtimestamp(ended).date() == datetime.fromtimestamp(started).date():
        return datetime.fromtimestamp(ended).time().isoformat(timespec="seconds")
    return format_time(ended)


def get_row_text(backup_run: BackupRun) -> List[str]:
    """
    :return: the text of each column of a backup run's row, in the order of the columns
    """
    duration = backup_run.duration
    average_rate = backup_run.average_rate
    return [
        format_time(backup_run.started),
        "" if backup_run.ended is None else format_end_time(backup_run.started, backup_run.ended),
        "" if duration is None else str(timedelta(seconds=round(duration))),
        "" if backup_run.backup_type is None else backup_run.backup_type.name,
        backup_run.ui_type.name.upper(),
        backup_run.status.value,
        format_size(backup_run.received_bytes),
        "" if average_rate is None or backup_run.received_bytes == 0 else f"{format_size(round(average_rate))}/s",
        f"{backup_run.read_units:g}" if backup_run.read_units > 0.0 else "",
        "" if backup_run.cost is None else format_cost(backup_run.cost),
        str(backup_run.error_count),
        str(backup_run.warning_count),
        backup_run.errors[0] if backup_run.errors else "",
    ]


class HistoryWidget(QWidget):
    """
    "History" tab - the backup runs in the backup history, most recent first. It is read again whenever a backup of this bup writes
    to the history, and whenever the tab is shown (another bup, e.g. a CLI run, may have written to it).
    """

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        self.note_label = QLabel(history_note)
        self.note_label.setWordWrap(True)
        self.layout().addWidget(self.note_label)

        self.status_label = QLabel()  # says so if the history can't be shown (and is otherwise not there)
        self.status_label.setVisible(False)
        self.layout().addWidget(self.status_label)

        # every column is as wide as its contents, except the error details on the far right, which take up the remaining width
        # (an error message can be long - all of it is in the tool tip)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(len(columns) - 1, QHeaderView.Stretch)
        self.layout().addWidget(self.table)

        self.reload()
        history_emitter.changed_signal.connect(self.reload)

    def reload(self):
        """
        Show the backup history as it is now. Connected to the history's changed signal, so it runs in the GUI thread.
        """
        try:
            backup_runs = get_backup_history().get_runs(max_history_rows)
            self.status_label.setVisible(False)
        except (sqlite3.Error, OSError) as e:
            log.warning(f"could not read the backup history : {e}")
            backup_runs = []
            self.status_label.setText(f"Backup history not available : {e}")
            self.status_label.setVisible(True)
        self.table.setRowCount(len(backup_runs))
        for row, backup_run in enumerate(backup_runs):
            for column, text in enumerate(get_row_text(backup_run)):
                item = QTableWidgetItem(text)
                if columns[column] == "Error details":
                    item.setToolTip("\n".join(backup_run.errors))  # every error message on record, not only the first
                self.table.setItem(row, column, item)

    def showEvent(self, a0: QShowEvent) -> None:
        """
        The tab is being shown: read the history again.

        :param a0: the show event (the name is the one PyQt5 gives this parameter of QWidget.showEvent)
        """
        self.reload()
        super().showEvent(a0)
