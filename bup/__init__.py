"""
bup: backs up AWS S3 buckets, AWS DynamoDB tables and GitHub repositories to a local directory, from the command line (bup.cli)
or a GUI (bup.gui). The backups are S3Backup, DynamoDBBackup and GithubBackup, which share BupBase.

The order of the imports below matters: a module imports what it needs from this package, which has to be here already.
"""

from .__version__ import __application_name__, __version__, __description__, __author__, __url__, __download_url__, __author_url__
from .robust_os_calls import rmdir
from .ui_types import UITypes
from .arguments import arguments
from .preferences import BupPreferences, get_preferences, ExclusionPreferences
from .backup_types import BackupTypes
from .bup_base import BupBase
from .s3_backup import S3Backup
from .dynamodb_backup import DynamoDBBackup
from .github_backup import GithubBackup
