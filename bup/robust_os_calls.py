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


def rmdir(p: Path):
    """
    Remove a directory and everything in it, trying again for a while if it can not be removed.

    :param p: the directory
    :return: True if the directory is gone
    """
    retry_count = 10
    while p.exists() and retry_count > 0:
        try:
            _p = make_long_path_compatible(p)
            shutil.rmtree(_p, onexc=_remove_readonly_onexc)
        except FileNotFoundError as e:
            log.debug(str(e))  # this can happen when first doing the shutil.rmtree()
            time.sleep(1)
        except PermissionError as e:
            log.info(str(e))
            time.sleep(1)
        except OSError as e:
            log.info(str(e))
            time.sleep(1)
        retry_count -= 1
    if p.exists():
        log.error('could not remove "%s"' % p)
    return not p.exists()
