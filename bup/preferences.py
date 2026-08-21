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

    s3_size_only: bool = attrib(default=False)  # aws s3 sync --size-only (compare file size only, not timestamps)

    verbose: bool = attrib(default=False)

    detailed_log_directory: str = attrib(default=None)  # None/blank = detailed file logging off
    detailed_log_file_size_limit_mb: int = attrib(default=None)  # None = default limit

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
    log_pane_s3_height: int = attrib(default=None)
    log_pane_dynamodb_height: int = attrib(default=None)
    log_pane_github_height: int = attrib(default=None)
    log_pane_application_height: int = attrib(default=None)


def get_preferences(ui_type: UITypes) -> BupPreferences:
    return BupPreferences(__application_name__, __author__, f"{ui_type.name}_preferences")


class ExclusionPreferences(PrefOrderedSet):
    def __init__(self, exclusion_type: str):
        super().__init__(__application_name__, __author__, f"exclusions_{exclusion_type}")

    def get_no_comments(self) -> List[str]:
        """
        Exclusion entries with rudimentary sanitization applied: anything from a "#" to the end of the line is a comment
        (so both whole-line comments and inline trailing comments such as "my-bucket  # note" are supported), comments and
        blank/whitespace-only lines are dropped, and leading/trailing whitespace is stripped from the remaining entries
        so that e.g. "my-bucket " still matches "my-bucket". "#" can not appear in S3 bucket, DynamoDB table, or GitHub
        repo names, so there is no need for an escape.
        """
        entries_without_comments = [s.split("#", 1)[0].strip() for s in super().get()]
        return [s for s in entries_without_comments if len(s) > 0]
