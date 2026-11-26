"""
The history of backup runs: when each backup started and ended, how it ended, what it backed up (how many buckets, tables or
repositories, and files), what it received over the network, approximately what that cost and what errors it had.

The history is kept in a local SQLite database, with one row per backup type each time it is run (the GUI runs every backup type at
once, the CLI the ones it is asked for). A backup writes its row when it starts, updates it as it goes and completes it when it ends,
so a backup that never got to its end (bup was killed, or the system crashed or lost power) leaves a row that still says it is
running. The next time the GUI is started those rows are found and marked as interrupted (see mark_interrupted_backups()).
"""

import dataclasses
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import appdirs
import psutil
from balsa import get_logger
from PyQt5.QtCore import QObject, pyqtSignal

from bup import __application_name__, __author__
from bup.backup_types import BackupTypes
from bup.sqlite_store import SQLiteStore
from bup.transfer import TransferRecord
from bup.ui_types import UITypes

log = get_logger(__application_name__)

max_recorded_errors = 100  # error messages kept per backup run (every error is counted)

process_start_tolerance_seconds = 2.0  # the start time the OS reports for a process can differ slightly from one reading to the next


class BackupStatus(Enum):
    """
    How a backup run is going or how it ended. The name is what is stored in the database, the value is what the user is shown.
    """

    running = "running"
    completed = "completed"
    completed_with_errors = "completed with errors"
    stopped = "stopped"  # the user asked it to stop
    failed = "failed"  # ended by an exception
    interrupted = "did not finish"  # never got to its end: bup was closed or crashed, or the system crashed or was shut down


@dataclass
class BackupCounts:
    """
    What a backup run counted. A count is None if the run has not counted it (yet, or it was recorded by a bup that did not), or if
    its backup type does not have it.
    """

    found: Optional[int] = None  # the buckets (S3), tables (DynamoDB) or repositories (GitHub) there are
    backed_up: Optional[int] = None  # those that were backed up without an error
    excluded: Optional[int] = None  # those that were not backed up because they are in the exclusion list
    files: Optional[int] = None  # S3: the files in the backup of the buckets that were synced, whenever they were downloaded
    files_synced: Optional[int] = None  # S3: the files that were downloaded in this run


@dataclass(frozen=True)
class BackupRun:
    """
    One run of one backup type, as recorded in the history. The fields are the columns of the history table, in order.
    """

    run_id: int
    backup_type: Optional[BackupTypes]  # None only for a backup class that has no type
    ui_type: UITypes
    pid: int  # the process that ran it, which with process_start tells if it is still running
    process_start: float  # when that process started (epoch seconds), since a later process can have the same pid
    started: float  # epoch seconds
    ended: Optional[float]  # epoch seconds, None while it is running and if it was interrupted (when is not known)
    status: BackupStatus
    received_bytes: int
    read_units: float  # DynamoDB read request units
    cost: Optional[float]  # approximate USD, None where there is no charge to estimate or the AWS prices are not known
    error_count: int
    warning_count: int
    errors: Tuple[str, ...]  # the error messages (the first max_recorded_errors of them)
    counts: BackupCounts  # how many buckets, tables or repositories, and files

    @property
    def duration(self) -> Optional[float]:
        """
        How long the run took in seconds, or None if it has not ended.
        """
        return None if self.ended is None else self.ended - self.started

    @property
    def average_rate(self) -> Optional[float]:
        """
        The bytes received per second over the whole run, or None if it has not ended (or took no time).
        """
        duration = self.duration
        return None if duration is None or duration <= 0.0 else self.received_bytes / duration


# the columns of the history table that are the fields of BackupCounts, in order
count_columns = ("found_count", "backed_up_count", "excluded_count", "file_count", "synced_file_count")

# the columns of the history table, which are the fields of BackupRun in order (and of its BackupCounts, last)
history_columns = "id, backup_type, ui_type, pid, process_start, started, ended, status, received_bytes, read_units, cost, error_count, warning_count, errors, " + ", ".join(count_columns)


def _to_backup_run(row: tuple) -> BackupRun:
    """
    :param row: a row of the history table (its history_columns)
    :return: the backup run of the row
    """
    run_id, backup_type, ui_type, pid, process_start, started, ended, status, received_bytes, read_units, cost, error_count, warning_count, errors, *counts = row
    return BackupRun(
        run_id,
        None if backup_type is None else BackupTypes[backup_type],
        UITypes[ui_type],
        pid,
        process_start,
        started,
        ended,
        BackupStatus[status],
        received_bytes,
        read_units,
        cost,
        error_count,
        warning_count,
        tuple(json.loads(errors)),
        BackupCounts(*counts),
    )


def get_backup_history_path() -> Path:
    """
    :return: the path of the SQLite database the backup history is kept in (in bup's user data directory)
    """
    return Path(appdirs.user_data_dir(__application_name__, __author__), "backup_history.db")


def is_process_running(pid: int, process_start: float) -> bool:
    """
    :param pid: the id of a process
    :param process_start: when that process started (epoch seconds)
    :return: True if that process is still running (and not a later process that was given the same id)
    """
    try:
        return abs(psutil.Process(pid).create_time() - process_start) <= process_start_tolerance_seconds
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # no such process, or one this user may not look at (which is then not the bup this user ran)
        return False


class BackupHistory(SQLiteStore):
    """
    The backup runs, in a SQLite database (see SQLiteStore: it can be used from any thread).
    """

    def __init__(self, path: Path):
        """
        :param path: the path of the database (made, with its directory, if it does not exist)
        """
        super().__init__(path)
        with self.transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS backup_runs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, backup_type TEXT, ui_type TEXT NOT NULL, pid INTEGER NOT NULL, process_start REAL NOT NULL, "
                "started REAL NOT NULL, ended REAL, status TEXT NOT NULL, received_bytes INTEGER NOT NULL DEFAULT 0, read_units REAL NOT NULL DEFAULT 0.0, cost REAL, "
                "error_count INTEGER NOT NULL DEFAULT 0, warning_count INTEGER NOT NULL DEFAULT 0, errors TEXT NOT NULL DEFAULT '[]')"
            )
            if self._get_missing_columns(connection):
                # The database was made by a bup that did not have these columns (bup 0.17.0 had no counts). Its runs stay as they
                # are, with no counts. More than one backup can open the history at the same time, so the columns are looked for
                # again once the database is locked: only one of them adds a column.
                connection.execute("BEGIN IMMEDIATE")
                for column in self._get_missing_columns(connection):
                    connection.execute(f"ALTER TABLE backup_runs ADD COLUMN {column} INTEGER")

    @staticmethod
    def _get_missing_columns(connection: sqlite3.Connection) -> List[str]:
        """
        :return: the count columns that the history table of this database does not have
        """
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(backup_runs)")}
        return [column for column in count_columns if column not in existing_columns]

    def start(self, backup_type: Optional[BackupTypes], ui_type: UITypes, started: Optional[float] = None) -> int:
        """
        Record that this process has started a backup.

        :param backup_type: the type of the backup
        :param ui_type: the UI the backup runs in
        :param started: when it started (epoch seconds), now if not given
        :return: the id of the run, to update() it with
        """
        pid = os.getpid()
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO backup_runs (backup_type, ui_type, pid, process_start, started, status) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    None if backup_type is None else backup_type.name,
                    ui_type.name,
                    pid,
                    psutil.Process(pid).create_time(),
                    time.time() if started is None else started,
                    BackupStatus.running.name,
                ),
            )
            run_id = cursor.lastrowid
        if run_id is None:
            raise sqlite3.Error("no id for the new backup run")  # an INSERT of one row always has one
        return run_id

    def update(
        self,
        run_id: int,
        status: BackupStatus,
        transfer_total: TransferRecord,
        error_count: int,
        warning_count: int,
        errors: Iterable[str],
        ended: Optional[float] = None,
        counts: Optional[BackupCounts] = None,
    ):
        """
        Record how a backup run is going, or how it ended.

        :param run_id: the id of the run, from start()
        :param status: BackupStatus.running while it is running, then how it ended
        :param transfer_total: the total of what it has received
        :param error_count: how many errors it has had
        :param warning_count: how many warnings it has had
        :param errors: its error messages (the first max_recorded_errors are kept)
        :param ended: when it ended (epoch seconds), None if it has not (or when is not known)
        :param counts: what it has counted, nothing if not given
        """
        counts = BackupCounts() if counts is None else counts
        with self.transaction() as connection:
            connection.execute(
                "UPDATE backup_runs SET status = ?, ended = ?, received_bytes = ?, read_units = ?, cost = ?, error_count = ?, warning_count = ?, errors = ?, "
                + ", ".join(f"{column} = ?" for column in count_columns)
                + " WHERE id = ?",
                (
                    status.name,
                    ended,
                    transfer_total.received_bytes,
                    transfer_total.read_units,
                    transfer_total.cost,
                    error_count,
                    warning_count,
                    json.dumps(list(errors)[:max_recorded_errors]),
                    *dataclasses.astuple(counts),
                    run_id,
                ),
            )

    def get_runs(self, limit: int = 1000) -> List[BackupRun]:
        """
        :param limit: the most runs to return
        :return: the most recent backup runs, the most recent first
        """
        with self.connection() as connection:
            rows = connection.execute(f"SELECT {history_columns} FROM backup_runs ORDER BY started DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [_to_backup_run(row) for row in rows]

    def mark_interrupted(self) -> List[BackupRun]:
        """
        Find the backup runs that never got to their end - recorded as running, by a process that no longer is - and record them as
        interrupted. A backup that another bup process (e.g. a CLI run) is running right now is left alone.

        :return: the runs that were marked, as they are now, the most recent first
        """
        with self.transaction() as connection:
            rows = connection.execute(f"SELECT {history_columns} FROM backup_runs WHERE status = ? ORDER BY started DESC, id DESC", (BackupStatus.running.name,)).fetchall()
            interrupted_runs = [backup_run for backup_run in map(_to_backup_run, rows) if not is_process_running(backup_run.pid, backup_run.process_start)]
            connection.executemany("UPDATE backup_runs SET status = ? WHERE id = ?", [(BackupStatus.interrupted.name, backup_run.run_id) for backup_run in interrupted_runs])
        return [dataclasses.replace(backup_run, status=BackupStatus.interrupted) for backup_run in interrupted_runs]


def get_backup_history() -> BackupHistory:
    """
    The backup history of this user. Raises sqlite3.Error or OSError if its database can't be opened or made.
    """
    return BackupHistory(get_backup_history_path())


def mark_interrupted_backups() -> List[BackupRun]:
    """
    Record the backups that never got to their end as interrupted (see BackupHistory.mark_interrupted()). Called when bup is started.

    :return: the runs that were marked (none if the history can't be read - that is logged)
    """
    try:
        return get_backup_history().mark_interrupted()
    except (sqlite3.Error, OSError) as e:
        log.warning(f"could not read the backup history : {e}")
        return []


def format_time(epoch_seconds: float) -> str:
    """
    :return: a time as local date and time to the second, e.g. "2026-11-23 14:05:09"
    """
    return datetime.fromtimestamp(epoch_seconds).isoformat(sep=" ", timespec="seconds")


def get_interrupted_message(interrupted_runs: List[BackupRun]) -> str:
    """
    What to tell the user about backups that never got to their end.

    :param interrupted_runs: the runs, from mark_interrupted_backups()
    :return: the message (one line), or "" if there are no such runs
    """
    if not interrupted_runs:
        return ""
    interrupted_backup_types = {backup_run.backup_type for backup_run in interrupted_runs}
    names = ", ".join(backup_type.name for backup_type in BackupTypes if backup_type in interrupted_backup_types)
    most_recent_start = max(backup_run.started for backup_run in interrupted_runs)
    which = f"The {names} backup" if names else "A backup"
    return f"{which} started {format_time(most_recent_start)} did not finish: bup was closed or crashed, or the system crashed or was shut down, while it was running. See the History tab."


class HistoryEmitter(QObject):
    """
    Has the signal that tells the GUI's History tab that the backup history has changed.
    """

    changed_signal = pyqtSignal()


# Backups emit this when they have written to the history, and the GUI's History tab listens. Backups run in worker QThreads and Qt
# widgets may only be touched from the GUI thread - the signal connection handles the thread hop. With no listener (e.g. the CLI) an
# emit does nothing.
history_emitter = HistoryEmitter()
