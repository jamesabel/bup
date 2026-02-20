from balsa import get_logger
from pref import Pref, PrefOrderedSet
from attr import attrib, attrs
from typing import List

from bup import __application_name__, __author__, UITypes


log = get_logger(__application_name__)


@attrs
class BupPreferences(Pref):

    backup_directory: str = attrib(default=None)

    aws_profile: str = attrib(default=None)
    aws_access_key_id: str = attrib(default=None)
    aws_secret_access_key: str = attrib(default=None)
    aws_region: str = attrib(default=None)
    github_token: str = attrib(default=None)

    automatic_backup: bool = attrib(default=None)
    backup_period: int = attrib(default=None)  # hours
    most_recent_backup: int = attrib(default=None)  # epoch in seconds

    dry_run: bool = attrib(default=False)

    verbose: bool = attrib(default=False)

    height: int = attrib(default=None)
    width: int = attrib(default=None)
    S3_exclusions_height: int = attrib(default=None)
    S3_exclusions_width: int = attrib(default=None)
    S3_log_height: int = attrib(default=None)
    S3_log_width: int = attrib(default=None)
    S3_warnings_height: int = attrib(default=None)
    S3_warnings_width: int = attrib(default=None)
    S3_errors_height: int = attrib(default=None)
    S3_errors_width: int = attrib(default=None)
    DynamoDB_exclusions_height: int = attrib(default=None)
    DynamoDB_exclusions_width: int = attrib(default=None)
    DynamoDB_log_height: int = attrib(default=None)
    DynamoDB_log_width: int = attrib(default=None)
    DynamoDB_warnings_height: int = attrib(default=None)
    DynamoDB_warnings_width: int = attrib(default=None)
    DynamoDB_errors_height: int = attrib(default=None)
    DynamoDB_errors_width: int = attrib(default=None)
    github_exclusions_height: int = attrib(default=None)
    github_exclusions_width: int = attrib(default=None)
    github_log_height: int = attrib(default=None)
    github_log_width: int = attrib(default=None)
    github_warnings_height: int = attrib(default=None)
    github_warnings_width: int = attrib(default=None)
    github_errors_height: int = attrib(default=None)
    github_errors_width: int = attrib(default=None)


def get_preferences(ui_type: UITypes) -> BupPreferences:
    return BupPreferences(__application_name__, __author__, f"{ui_type.name}_preferences")


class ExclusionPreferences(PrefOrderedSet):
    def __init__(self, exclusion_type: str):
        super().__init__(__application_name__, __author__, f"exclusions_{exclusion_type}")

    def get_no_comments(self) -> List[str]:
        # get list of exclusions with comment lines removed
        return [s for s in super().get() if len(s) > 0 and s[0] != "#"]
