from pathlib import Path
from typing import List

import appdirs
from balsa import get_logger
from sqlitedict import SqliteDict
from attr import attrib, attrs

from bup import __application_name__, __author__, BackupTypes


log = get_logger(__application_name__)


sqlite_path = Path(appdirs.user_config_dir(__application_name__, __author__), f"{__application_name__}_pref.db")

# DB stores values directly (not encoded as a pickle)
preferences_sqlite_dict = SqliteDict(sqlite_path, "preferences", autocommit=True, encode=lambda x: x, decode=lambda x: x)


@attrs
class PreferencesStore:
    aws_profile: str = attrib(default=None)
    aws_access_key_id: str = attrib(default=None)

    def __attrs_post_init__(self):
        # load all attribute values from DB (if an attribute is in the table, a value of None is used)
        for key in self.__dict__:
            self.__setattr__(key, preferences_sqlite_dict.get(key))

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        # Save attribute value to DB.  Don't write to the database with the *default* value of None (also means that we can't do a *regular* write of a None value to the database).
        if value is not None:
            preferences_sqlite_dict[key] = value

    # def __init__(self):
    #     self.sqlite_path = Path(appdirs.user_config_dir(__application_name__, __author__), db_file_name)
    #     self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    #     # DB stores values directly (not encoded as a pickle)
    #     super().__init__(self.sqlite_path, "preferences", autocommit=True, encode=lambda x: x, decode=lambda x: x)

    # width_str = "width"
    # height_str = "height"
    #
    # def set_window_dimensions(self, width: int, height: int):
    #     self[self.width_str] = width
    #     self[self.height_str] = height
    #
    # def get_window_dimensions(self) -> Tuple[int, int]:
    #     w = int(self.get(self.width_str))
    #     h = int(self.get(self.height_str))
    #     return w, h
    #
    # # backup directory
    # backup_directory_string = "backup_directory"
    #
    # def set_backup_directory(self, value: Path):
    #     self[self.backup_directory_string] = str(value)
    #
    # def get_backup_directory(self) -> (Path, None):
    #     return self.get(self.backup_directory_string, None)
    #
    # # AWS IAM (need either AWS Profile or Access Key ID/Secret Access Key pair)
    # aws_profile_string = "aws_profile"
    #
    # def set_aws_profile(self, profile: str):
    #     self[self.aws_profile_string] = profile
    #
    # def get_aws_profile(self) -> str:
    #     return self.get(self.aws_profile_string)
    #
    # aws_access_key_id_string = "aws_access_key_id"
    #
    # def set_aws_access_key_id(self, access_key_id: str):
    #     self[self.aws_access_key_id_string] = access_key_id
    #
    # def get_aws_access_key_id(self) -> str:
    #     return self.get(self.aws_access_key_id_string)
    #
    # aws_secret_access_key_string = "aws_secret_access_key"
    #
    # def set_aws_secret_access_key(self, secret_access_key: str):
    #     self[self.aws_secret_access_key_string] = secret_access_key
    #
    # def get_aws_secret_access_key(self) -> str:
    #     return self.get(self.aws_secret_access_key_string)
    #
    # # dry run
    # dry_run_string = "dry_run"
    #
    # def set_dry_run(self, dry_run: bool):
    #     self[self.dry_run_string] = dry_run
    #
    # def get_dry_run(self) -> bool:
    #     return to_bool(self.get(self.dry_run_string))


class OrderedSetOfStringsStore(SqliteDict):
    """
    store/retrieve a list of strings to/from a SQlite database
    """
    def __init__(self, backup_type: BackupTypes):
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        # DB stores values directly (not encoded as a pickle)
        super().__init__(sqlite_path, backup_type.name, encode=lambda x: x, decode=lambda x: x)

    def set_set(self, strings: list):
        """
        set the list of strings
        :param strings: list of strings
        """
        self.clear()  # delete entire table
        # ordering is done by making the value in the key/value pair the index and our desired list "value" is the key
        for index, string in enumerate(strings):
            self[string] = index
        self.commit()  # not using autocommit since we're updating (setting) multiple values in the above for loop

    def get_set(self) -> List[str]:
        """
        returns the list of strings
        :return: list of strings
        """
        return list(sorted(self, key=self.get))
