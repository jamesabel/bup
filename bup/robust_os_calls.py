"""
File system calls that work where the plain ones do not on Windows: paths longer than MAX_PATH, read-only files, and files that
are briefly locked by another process (e.g. a virus scanner).
"""

import stat
import shutil
import time
import logging
import os
from os import chmod
from pathlib import Path

from bup import __application_name__

log = logging.getLogger(__application_name__)


def make_long_path_compatible(path: Path) -> str:
    """
    Converts a Path object to a long path string compatible with Windows.
    """
    path_str = str(path.resolve())
    if os.name.lower() == "nt" and not path_str.startswith("\\\\?\\"):
        if path_str.startswith("\\\\"):
            # UNC paths use the \\?\UNC\server\share form
            path_str = "\\\\?\\UNC" + path_str[1:]
        else:
            path_str = "\\\\?\\" + path_str
    return path_str


def remove_readonly(path: Path):
    """
    Make a file or directory writable, so that it can be removed.
    """
    chmod(path, stat.S_IWRITE | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


def _remove_readonly_onexc(func, path, exc):
    """
    Error handler of shutil.rmtree(), sometimes needed on Windows (e.g. the read-only files of a git repository): make what could
    not be removed writable, and try again.
    """
    _path = Path(path)
    if _path.is_file():
        remove_readonly(_path)
    else:
        for p in _path.rglob("*"):
            remove_readonly(p)
    func(path)


rmdir_attempts = 10  # times rmdir() tries to remove a directory
rmdir_retry_seconds = 1.0  # the wait after an attempt that failed


def rmdir(p: Path) -> bool:
    """
    Remove a directory and everything in it, trying again for a while if it can not be removed (e.g. a file in it is open in
    another process for a moment). A directory that is still there after rmdir_attempts attempts is not an exception: the caller
    is told with the return value, and it is the caller that reports it as the failure it is to what the caller is doing.

    :param p: the directory
    :return: True if the directory is gone (also if it was not there to begin with)
    """
    for attempt in range(1, rmdir_attempts + 1):
        if not p.exists():
            break
        try:
            shutil.rmtree(make_long_path_compatible(p), onexc=_remove_readonly_onexc)
        except OSError as e:
            # e.g. PermissionError for a file that is in use, or FileNotFoundError for something that was removed meanwhile
            log.info(f'could not remove "{p}" (attempt {attempt} of {rmdir_attempts}) : {e}')
            time.sleep(rmdir_retry_seconds)
    removed = not p.exists()
    if not removed:
        log.warning(f'could not remove "{p}" in {rmdir_attempts} attempts')
    return removed
