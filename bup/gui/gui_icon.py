from pathlib import Path

from bup import __application_name__


def get_icon_path() -> Path:
    icon_file_name = f"{__application_name__}.png"
    icon_file_path = None
    for d in [Path(), Path("icons")]:
        if (p := Path(d, icon_file_name)).exists():
            icon_file_path = p
            break
    assert icon_file_path is not None
    return icon_file_path
