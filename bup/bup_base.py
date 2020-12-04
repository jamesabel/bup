from pathlib import Path
from multiprocessing import Process
from typing import Callable

from typeguard import typechecked
from PyQt5.QtCore import QProcess, QThread, pyqtSignal

from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)


class BupBase(QThread):

    backup_type = None
    info_out_signal = pyqtSignal(str)

    def __init__(self, backup_directory: Path, info_out: Callable, warning_out: Callable, error_out: Callable, excludes: list, dry_run: bool, aws_profile: (str, None)):
        super().__init__()
        self.backup_directory: Path = backup_directory
        self.excludes = excludes
        self.aws_profile = aws_profile
        self.dry_run: bool = dry_run
        self.caller_info_out = info_out
        self.warning_out = warning_out
        self.error_out = error_out
        self.info_out_signal.connect(self._info_out)

    def info_out(self, s: str):
        self.info_out_signal.emit(s)

    def _info_out(self, s: str):
        log.info(s)
        self.caller_info_out(s)
