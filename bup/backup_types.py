"""
The types of backup that bup does.
"""

from enum import Enum
from pathlib import Path
from typing import Union


class BackupTypes(Enum):
    """
    A type of backup. The name is what its exclusion list is saved under and the title of its box in the GUI's Backup tab.
    """

    S3 = 0
    DynamoDB = 1
    github = 2


def get_backup_type_directory(backup_directory: Union[str, Path], backup_type: BackupTypes) -> Path:
    """
    Where the backup of a backup type is in the backup directory: the directory "s3", "dynamodb" or "github".

    :param backup_directory: the backup directory (of the preferences)
    :param backup_type: the backup type
    :return: the directory of the backup type's files
    """
    return Path(backup_directory, backup_type.name.lower())
