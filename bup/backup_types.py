"""
The types of backup that bup does.
"""

from enum import Enum


class BackupTypes(Enum):
    """
    A type of backup. The name is what its exclusion list is saved under and the title of its box in the GUI's Backup tab.
    """

    S3 = 0
    DynamoDB = 1
    github = 2
