from pathlib import Path
from multiprocessing import Process

from balsa import get_logger

from bup import __application_name__

log = get_logger(__application_name__)


class BupBase(Process):

    def __init__(self, backup_directory: Path, excludes: list = None, dry_run: bool = False, aws_profile: (str, None) = None):
        super().__init__()
        self.backup_directory: Path = backup_directory
        self.excludes: list = [] if excludes is None else excludes
        self.aws_profile = aws_profile
        self.dry_run: bool = dry_run

    def info_out(self, s: str):
        log.info(s)

    def warning_out(self, s: str):
        log.warning(s)

    def error_out(self, s: str):
        log.error(s)
