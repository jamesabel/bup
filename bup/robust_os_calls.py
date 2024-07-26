import stat
import shutil
import time
import logging
from os import chmod
from pathlib import Path

# robust OS functions

from bup import __application_name__

log = logging.getLogger(__application_name__)


def remove_readonly(path: Path):
    chmod(path, stat.S_IWRITE | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


# sometimes needed for Windows
def _remove_readonly_onerror(func, path, excinfo):
    _path = Path(path)
    if _path.is_file():
        remove_readonly(_path)
    else:
        for p in _path.rglob('*'):
            remove_readonly(p)
    func(path)


def rmdir(p: Path):
    retry_count = 10
    delete_ok = False
    while p.exists() and retry_count > 0:
        try:
            shutil.rmtree(p, onerror=_remove_readonly_onerror)
            delete_ok = True
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
    return delete_ok and retry_count > 0


def mkdirs(d: Path, remove_first=False):
    if remove_first:
        rmdir(d)
    # sometimes when Path.mkdir() exits the dir is not actually there
    count = 600
    while count > 0 and not d.exists():
        try:
            # for some reason we can get the FileNotFoundError exception
            d.mkdir(parents=True, exist_ok=True)
        except FileNotFoundError:
            pass
        if not d.exists():
            time.sleep(0.1)
        count -= 1
    if not d.exists():
        log.error(f'could not mkdirs "{d}" ({d.absolute()})')
