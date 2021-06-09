from pathlib import Path
import inspect

from balsa import get_logger

import bup
from bup import __application_name__

log = get_logger(__application_name__)


def get_icon_path(file_extension: str) -> Path:
    """
    get icon file path
    :param file_extension: "png" or "ico"
    :return: absolute path to icon file
    """
    icon_file_name = f"{__application_name__}.{file_extension}"
    bup_file = Path(inspect.getfile(bup)).absolute()
    log.debug(f"{bup_file=}")
    icon_file_path = Path(bup_file.parent, icon_file_name)
    if not icon_file_path.exists():
        log.exception(f"icon not found : {icon_file_path=}")
    return icon_file_path
