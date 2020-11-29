from pathlib import Path
from typing import Tuple

import appdirs
from tobool import to_bool
from balsa import get_logger
from sqlitedict import SqliteDict

from bup import __application_name__, __author__


log = get_logger(__application_name__)


class GUIPreferences(SqliteDict):
    def __init__(self):
        self.sqlite_path = Path(appdirs.user_config_dir(__application_name__, __author__), f"{__application_name__}_pref.sqlite")
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        # DB stores values directly
        super().__init__(self.sqlite_path, "preferences", autocommit=True, encode=lambda x: x, decode=lambda x: x)

    _width_str = "width"
    _height_str = "height"

    def set_window_dimensions(self, width: int, height: int):
        self[self._width_str] = width
        self[self._height_str] = height

    def get_window_dimensions(self) -> Tuple[int, int]:
        w = int(self.get(self._width_str))
        h = int(self.get(self._height_str))
        return w, h

    # backup directory
    _backup_directory_string = "backup_directory"

    def set_backup_directory(self, value: Path):
        self[self._backup_directory_string] = str(value)

    def get_backup_directory(self) -> (Path, None):
        return self.get(self._backup_directory_string, None)

    # AWS IAM (need either AWS Profile or Access Key ID/Secret Access Key pair)
    _aws_profile_string = "aws_profile"

    def set_aws_profile(self, profile: str):
        self[self._aws_profile_string] = profile

    def get_aws_profile(self) -> str:
        return self.get(self._aws_profile_string)

    _aws_access_key_id_string = "aws_access_key_id"

    def set_aws_access_key_id(self, access_key_id: str):
        self[self._aws_access_key_id_string] = access_key_id

    def get_aws_access_key_id(self) -> str:
        return self.get(self._aws_access_key_id_string)

    _aws_secret_access_key_string = "aws_secret_access_key"

    def set_aws_secret_access_key(self, secret_access_key: str):
        self[self._aws_secret_access_key_string] = secret_access_key

    def get_aws_secret_access_key(self) -> str:
        return self.get(self._aws_secret_access_key_string)

    # todo: put this in its own class
    def get_exclusions_string(self):
        return ""

    # dry run
    _dry_run_string = "dry_run"

    def set_dry_run(self, dry_run: bool):
        self[self._dry_run_string] = dry_run

    def get_dry_run(self) -> bool:
        return to_bool(self.get(self._dry_run_string))
