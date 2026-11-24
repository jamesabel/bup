"""
The base class of every backup (S3, DynamoDB, GitHub): a thread that runs the backup, with the output, stop request and transfer
reporting that all backups share, and the record of each run in the backup history.
"""

import sqlite3
import threading
import time
from typing import Callable, List, Optional

from PyQt5.QtCore import QThread, pyqtBoundSignal, pyqtSignal
from typeguard import typechecked

from balsa import get_logger

from bup import __application_name__, UITypes
from bup.backup_history import BackupCounts, BackupStatus, get_backup_history, history_emitter, max_recorded_errors
from bup.transfer import TransferRecord, get_transfer_total, transfer_emitter

log = get_logger(__application_name__)


class BupBase(QThread):
    """
    A backup that runs in its own thread. A derived class sets backup_type and implements run_backup(), which reports with info_out(),
    warning_out(), error_out() and transfer_out(), and checks stop_requested (or gives stop_event to what it calls) so that it can be
    stopped.

    Each kind of output is logged and given to the callable for it that the backup was made with. In the GUI that callable updates a
    widget, which only the GUI thread may do, so the output goes through a Qt signal (which makes the hop to the GUI thread). The CLI
    has no Qt event loop to deliver a signal, so there the callable is called directly.

    Every run is recorded in the backup history (see bup/backup_history.py): when it started and ended, how it ended, what it
    received, its errors and what the derived class counted in counts (e.g. the buckets it found and backed up).
    """

    backup_type = None  # the BackupTypes of the derived class
    info_out_signal = pyqtSignal(str)
    warning_out_signal = pyqtSignal(str)
    error_out_signal = pyqtSignal(str)

    @typechecked()
    def __init__(self, ui_type: UITypes, info_out: Callable, warning_out: Callable, error_out: Callable):
        """
        :param ui_type: the UI the backup runs in, which is also whose preferences it uses
        :param info_out: called with each line of regular output
        :param warning_out: called with each warning
        :param error_out: called with each error
        """
        super().__init__()
        self.stop_event = threading.Event()  # set to request a stop - an event so it can also be given to what a backup calls
        self.error_count = 0
        self.warning_count = 0
        self.error_messages: List[str] = []
        self.counts = BackupCounts()  # what this run has counted so far (set by the derived class as it goes), for the backup history
        self.count_lock = threading.Lock()  # errors and warnings can be reported from more than one thread
        self.transfer_records: List[TransferRecord] = []
        self.history_run_id: Optional[int] = None  # this run in the backup history, None if it is not recorded
        self.ui_type = ui_type
        self.caller_info_out = info_out
        self.caller_warning_out = warning_out
        self.caller_error_out = error_out
        self.info_out_signal.connect(self._info_out)
        self.warning_out_signal.connect(self._warning_out)
        self.error_out_signal.connect(self._error_out)

    def start(self, *args, **kwargs):
        """
        Start the backup in its thread. A prior run may have been stopped or had errors - a new start is a fresh run.
        """
        self.stop_event.clear()
        self.error_count = 0
        self.warning_count = 0
        self.error_messages = []
        self.counts = BackupCounts()
        self.transfer_records = []
        super().start(*args, **kwargs)

    def run(self):
        """
        What the thread runs: the backup of the derived class.
        """
        # QThreads aren't registered with Python's threading module by name, so log records would show a meaningless
        # thread name like "Dummy-25" - name the thread after this backup class (guard so a direct run() call in
        # tests doesn't rename the main thread)
        if threading.current_thread() is not threading.main_thread():
            threading.current_thread().name = type(self).__name__
        self.record_start()
        try:
            self.run_backup()
        except Exception as e:
            # an exception the backup did not handle ended it - record that, then let the exception on its way
            self.count_error(f"{type(e).__name__} : {e}")
            self.record_history(BackupStatus.failed, time.time())
            raise
        self.record_history(self.get_end_status(), time.time())

    def get_end_status(self) -> BackupStatus:
        """
        :return: how a run that got to its end ended
        """
        if self.stop_requested:
            return BackupStatus.stopped
        return BackupStatus.completed_with_errors if self.error_count > 0 else BackupStatus.completed

    def record_start(self):
        """
        Record in the backup history that this run has started. If bup or the system dies before the run ends, that record is what
        tells the next bup that a backup never got to its end.
        """
        self.history_run_id = None
        try:
            self.history_run_id = get_backup_history().start(self.backup_type, self.ui_type)
        except (sqlite3.Error, OSError) as e:
            # the backup itself does not need the history, so it goes on without it
            log.warning(f"could not record the backup in the backup history : {e}", extra=self._log_extra())
            return
        history_emitter.changed_signal.emit()

    def record_history(self, status: BackupStatus, ended: Optional[float] = None):
        """
        Record in the backup history how this run is going, or how it ended.

        :param status: BackupStatus.running while it is running, then how it ended
        :param ended: when it ended (epoch seconds), None while it is running
        """
        if self.history_run_id is None:
            return  # the start could not be recorded (which was logged), so there is no record to update
        transfer_total = get_transfer_total(self.backup_type, self.transfer_records)
        try:
            get_backup_history().update(self.history_run_id, status, transfer_total, self.error_count, self.warning_count, self.error_messages, ended, self.counts)
        except (sqlite3.Error, OSError) as e:
            log.warning(f"could not update the backup history : {e}", extra=self._log_extra())
            return
        history_emitter.changed_signal.emit()

    def run_backup(self):
        """
        Do the backup. Implemented by the derived class.
        """
        raise NotImplementedError

    def request_stop(self):
        """
        Ask the backup to stop. It stops at the next point where it checks, so it may still be running for a while.
        """
        self.stop_event.set()

    @property
    def stop_requested(self) -> bool:
        return self.stop_event.is_set()

    def _out(self, signal: pyqtBoundSignal, deliver: Callable[[str], None], s: str):
        """
        Send output on its way to the caller: directly in the CLI, through the signal in the GUI (see the class docstring).

        :param signal: the signal of this kind of output
        :param deliver: what the signal is connected to, which logs the output and gives it to the caller
        :param s: the output
        """
        if self.ui_type == UITypes.cli:
            deliver(s)
        else:
            signal.emit(s)

    def info_out(self, s: str):
        """
        Report a line of regular output (e.g. progress).
        """
        self._out(self.info_out_signal, self._info_out, s)

    def warning_out(self, s: str):
        """
        Report a warning: something to know about that is not a failure of the backup. Warnings are counted in warning_count.
        """
        with self.count_lock:
            self.warning_count += 1
        self._out(self.warning_out_signal, self._warning_out, s)

    def error_out(self, s: str):
        """
        Report an error: something was not backed up. Errors are counted in error_count (the CLI exits non-zero if there are any).
        """
        self.count_error(s)
        self._out(self.error_out_signal, self._error_out, s)

    def count_error(self, s: str):
        """
        Count an error and keep its message for the backup history. This is done where the error is reported, not where it is
        delivered: in the GUI the delivery is through a signal, which can be after the run has ended and recorded its errors.
        """
        with self.count_lock:
            self.error_count += 1
            if len(self.error_messages) < max_recorded_errors:
                self.error_messages.append(s)

    def _log_extra(self) -> dict:
        # stamp the record with this engine's backup type so the GUI log tab can route it to the right pane
        # (the record's own source location is this file, not the backup module the message came from)
        return {"backup_type": self.backup_type}

    def _info_out(self, s: str):
        log.info(s, extra=self._log_extra())
        self.caller_info_out(s)

    def _warning_out(self, s: str):
        log.warning(s, extra=self._log_extra())
        self.caller_warning_out(s)

    def _error_out(self, s: str):
        log.error(s, extra=self._log_extra())
        self.caller_error_out(s)

    def transfer_out(self, transfer_record: TransferRecord):
        """
        Report what one backed up item received over the network (and approximately what it cost).
        """
        self.transfer_records.append(transfer_record)
        self._transfer_text_out(str(transfer_record))
        transfer_emitter.transfer_signal.emit(transfer_record)
        self.record_history(BackupStatus.running)  # so that what a run received is on record even if it never gets to its end

    def transfer_summary_out(self):
        """
        Report the total of everything this run has reported with transfer_out().
        """
        self._transfer_text_out(str(get_transfer_total(self.backup_type, self.transfer_records)))

    def _transfer_text_out(self, s: str):
        if self.ui_type == UITypes.cli:
            # the CLI has no Transfer tab, so the transfer report is part of its regular output
            self._info_out(s)
        else:
            # the GUI shows transfers in the Transfer tab - only log them, to keep them out of the backup's own output
            log.info(s, extra=self._log_extra())
