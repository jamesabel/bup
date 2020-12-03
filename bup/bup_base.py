from pathlib import Path
from multiprocessing import Process
from typing import Callable

from typeguard import typechecked


class BupBase(Process):

    backup_type = None

    def __init__(self, backup_directory: Path, info_out: Callable, warning_out: Callable, error_out: Callable, excludes: list = None, dry_run: bool = False, aws_profile: (str, None) = None):
        super().__init__()
        self.backup_directory: Path = backup_directory
        self.excludes: list = [] if excludes is None else excludes
        self.aws_profile = aws_profile
        self.dry_run: bool = dry_run
        self.info_out = info_out
        self.warning_out = warning_out
        self.error_out = error_out
