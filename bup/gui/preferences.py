from balsa import get_logger
from pref import PrefDict, PrefOrderedSet
from attr import attrib, attrs

from bup import __application_name__


log = get_logger(__application_name__)


@attrs
class BupPreferences(PrefDict):
    backup_directory: str = attrib(default=None)
    aws_profile: str = attrib(default=None)
    aws_access_key_id: str = attrib(default=None)
    aws_secret_access_key: str = attrib(default=None)
    aws_region: str = attrib(default=None)
