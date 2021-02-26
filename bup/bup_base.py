from typing import Callable

from PyQt5.QtCore import QThread, pyqtSignal
from typeguard import typechecked

from balsa import get_logger

from bup import __application_name__, UITypes

log = get_logger(__application_name__)


class BupBase(QThread):

    backup_type = None
    info_out_signal = pyqtSignal(str)
    warning_out_signal = pyqtSignal(str)
    error_out_signal = pyqtSignal(str)

    @typechecked()
    def __init__(self, ui_type: UITypes, info_out: Callable, warning_out: Callable, error_out: Callable):
        super().__init__()
        self.ui_type = ui_type
        self.caller_info_out = info_out
        self.caller_warning_out = warning_out
        self.caller_error_out = error_out
        self.info_out_signal.connect(self._info_out)
        self.warning_out_signal.connect(self._warning_out)
        self.error_out_signal.connect(self._error_out)

    def info_out(self, s: str):
        # callees could call emit(), but that seems awkward so provide this method
        self.info_out_signal.emit(s)

    def _info_out(self, s: str):
        # hooked up to the signal for threading
        log.info(s)
        self.caller_info_out(s)

    def warning_out(self, s: str):
        # callees could call emit(), but that seems awkward so provide this method
        self.warning_out_signal.emit(s)

    def _warning_out(self, s: str):
        # hooked up to the signal for threading
        log.warning(s)
        self.caller_warning_out(s)

    def error_out(self, s: str):
        # callees could call emit(), but that seems awkward so provide this method
        self.error_out_signal.emit(s)

    def _error_out(self, s: str):
        # hooked up to the signal for threading
        log.error(s)
        self.caller_error_out(s)
