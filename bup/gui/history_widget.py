"""
The GUI's "History" tab: the backup runs on record - when each started and ended, how it ended, what it backed up and received,
and its errors.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from PyQt5.QtGui import QShowEvent
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHeaderView
from balsa import get_logger

from bup import __application_name__
from bup.backup_history import BackupRun, format_time, get_backup_history, history_emitter
from bup.gui.gui_util import make_table, set_table_row
from bup.transfer import format_size, format_cost

log = get_logger(__application_name__)

max_history_rows = 1000  # the most recent runs shown (the database keeps them all)

columns = [
    "Started",
    "Ended",
    "Duration",
    "Backup",
    "Run from",
    "Status",
    "Found",
    "Backed up",
    "Excluded",
    "Items",
    "Branches",
    "Files",
    "Files synced",
    "Size",
    "File dates",
    "Files hash",
    "Received",
    "Average rate",
    "Read units",
    "Approx. cost",
    "Errors",
    "Warnings",
    "Error details",
]
error_details_column = columns.index("Error details")
files_hash_column = columns.index("Files hash")

files_hash_shown_length = 12  # the characters of the files hash that its column shows (all of it is in the tool tip)

history_note = (
    "One row per backup type each time it is run, from the GUI or the command line, most recent first. A backup that did not finish "
    "was cut short: bup was closed or crashed, or the system crashed or was shut down, while it was running. Found, Backed up and "
    "Excluded are counts of buckets (S3), tables (DynamoDB) or repositories (GitHub). Items is the items of the DynamoDB tables and "
    "Branches the branches of the GitHub repositories that were backed up. Files is the files in the backup of the S3 buckets, and "
    "Files synced is how many of them this run downloaded. Size is the total size of those files, File dates the range of their "
    "modification times, and Files hash a hash of their paths, sizes and modification times (not of their contents), which is the "
    "same from run to run while none of that changes. Costs are approximate (see the Transfer tab)."
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


def format_count(count: Optional[int]) -> str:
    """
    :param count: a count of a backup run, None if the run does not have it
    :return: the count with thousands separators, e.g. "12,345", or "" if there is none
    """
    return "" if count is None else f"{count:,}"


def format_date_range(oldest: Optional[float], newest: Optional[float]) -> str:
    """
    :param oldest: the earliest of some times (epoch seconds), None if there are none
    :param newest: the latest of them
    :return: the local dates they are from and to, e.g. "2019-03-01 to 2026-11-20" (one date if they are on the same day, "" if there are none)
    """
    if oldest is None or newest is None:
        return ""
    oldest_date = datetime.fromtimestamp(oldest).date().isoformat()
    newest_date = datetime.fromtimestamp(newest).date().isoformat()
    return oldest_date if oldest_date == newest_date else f"{oldest_date} to {newest_date}"


def get_row_text(backup_run: BackupRun) -> List[str]:
    """
    :return: the text of each column of a backup run's row, in the order of the columns
    """
    duration = backup_run.duration
    average_rate = backup_run.average_rate
    counts = backup_run.counts
    return [
        format_time(backup_run.started),
        "" if backup_run.ended is None else format_end_time(backup_run.started, backup_run.ended),
        "" if duration is None else str(timedelta(seconds=round(duration))),
        "" if backup_run.backup_type is None else backup_run.backup_type.name,
        backup_run.ui_type.name.upper(),
        backup_run.status.value,
        format_count(counts.found),
        format_count(counts.backed_up),
        format_count(counts.excluded),
        format_count(counts.items),
        format_count(counts.branches),
        format_count(counts.files),
        format_count(counts.files_synced),
        "" if counts.size is None else format_size(counts.size),
        format_date_range(counts.oldest_file_mtime, counts.newest_file_mtime),
        (counts.files_hash or "")[:files_hash_shown_length],
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
        """
        Make the tab, with the backup history as it is now.
        """
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
        self.table = make_table(columns)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(error_details_column, QHeaderView.Stretch)
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
            items = set_table_row(self.table, row, get_row_text(backup_run))
            items[error_details_column].setToolTip("\n".join(backup_run.errors))  # every error message on record, not only the first
            items[files_hash_column].setToolTip(backup_run.counts.files_hash or "")  # all of the hash

    def showEvent(self, a0: QShowEvent) -> None:
        """
        The tab is being shown: read the history again.

        :param a0: the show event (the name is the one PyQt5 gives this parameter of QWidget.showEvent)
        """
        self.reload()
        super().showEvent(a0)
