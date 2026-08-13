import logging
import pickle
from datetime import timedelta
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from awsimple import DynamoDBAccess, dynamodb_to_json
from balsa import get_logger

# boto3/botocore log responses at DEBUG level; the repr() of large responses can contain
# characters that cp1252 (Windows console default) cannot encode, causing noisy logging errors.
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)

from bup import BupBase, BackupTypes, get_preferences, ExclusionPreferences, __application_name__

log = get_logger(__application_name__)


class DynamoDBBackup(BupBase):

    backup_type = BackupTypes.DynamoDB

    def run_backup(self):
        preferences = get_preferences(self.ui_type)
        backup_directory = preferences.backup_directory
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(self.backup_type.name).get_no_comments()

        dynamodb_access = DynamoDBAccess(
            profile_name=preferences.aws_profile or None,
            aws_access_key_id=preferences.aws_access_key_id or None,
            aws_secret_access_key=preferences.aws_secret_access_key or None,
            region_name=preferences.aws_region or None,
        )
        try:
            tables = dynamodb_access.get_table_names()
        except (ClientError, BotoCoreError) as e:
            # BotoCoreError covers e.g. NoCredentialsError and EndpointConnectionError
            self.error_out(f"could not list DynamoDB tables - check credentials and connectivity : {e}")
            return
        self.info_out(f"found {len(tables)} DynamoDB tables")
        count = 0
        for table_name in tables:
            if self.stop_requested:
                break

            # awsimple will update immediately if number of table rows changes, but backup from scratch every so often to be safe
            cache_life = timedelta(days=1).total_seconds()

            if table_name in exclusions:
                self.info_out(f"excluding {table_name}")
            elif dry_run:
                self.info_out(f"dry run {table_name}")
            else:
                self.info_out(f"{table_name}")
                table = DynamoDBAccess(
                    table_name,
                    profile_name=preferences.aws_profile or None,
                    aws_access_key_id=preferences.aws_access_key_id or None,
                    aws_secret_access_key=preferences.aws_secret_access_key or None,
                    region_name=preferences.aws_region or None,
                    cache_life=cache_life,
                )
                try:
                    table_contents = table.scan_table_cached()
                except (ClientError, BotoCoreError) as e:
                    # don't let one failed table kill the backup of the remaining tables
                    self.error_out(f"could not scan {table_name} : {e}")
                    continue

                dir_path = Path(backup_directory, "dynamodb")
                dir_path.mkdir(parents=True, exist_ok=True)
                try:
                    with Path(dir_path, f"{table_name}.pickle").open("wb") as f:
                        pickle.dump(table_contents, f)
                    with Path(dir_path, f"{table_name}.json").open("w", encoding="utf-8") as f:
                        f.write(dynamodb_to_json(table_contents, indent=4))
                except OSError as e:
                    self.error_out(f"could not write backup files for {table_name} : {e}")
                    continue
                count += 1

        self.info_out(f"{len(tables)} tables, {count} backed up, {len(exclusions)} excluded")
