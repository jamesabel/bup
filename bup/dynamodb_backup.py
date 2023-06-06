import pickle
from datetime import timedelta
from pathlib import Path

from botocore.exceptions import ClientError
from awsimple import DynamoDBAccess, dynamodb_to_json
from balsa import get_logger

from bup import BupBase, BackupTypes, get_preferences, ExclusionPreferences, __application_name__

log = get_logger(__application_name__)


class DynamoDBBackup(BupBase):

    backup_type = BackupTypes.DynamoDB

    def run(self):
        preferences = get_preferences(self.ui_type)
        backup_directory = preferences.backup_directory
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(self.backup_type.name).get_no_comments()

        dynamodb_access = DynamoDBAccess(profile_name=preferences.aws_profile)
        try:
            tables = dynamodb_access.get_table_names()
        except ClientError as e:
            log.warning(e)
            tables = []
        self.info_out(f"found {len(tables)} DynamoDB tables")
        count = 0
        for table_name in tables:

            # awsimple will update immediately if number of table rows changes, but backup from scratch every so often to be safe
            cache_life = timedelta(days=1).total_seconds()

            if table_name in exclusions:
                self.info_out(f"excluding {table_name}")
            elif dry_run:
                self.info_out(f"dry run {table_name}")
            else:
                self.info_out(f"{table_name}")
                table = DynamoDBAccess(table_name, cache_life=cache_life)
                table_contents = table.scan_table_cached()

                dir_path = Path(backup_directory, "dynamodb")
                dir_path.mkdir(parents=True, exist_ok=True)
                with Path(dir_path, f"{table_name}.pickle").open("wb") as f:
                    pickle.dump(table_contents, f)
                with Path(dir_path, f"{table_name}.json").open("w") as f:
                    f.write(dynamodb_to_json(table_contents, indent=4))
                count += 1

        self.info_out(f"{count} tables, {count} backed up, {len(exclusions)} excluded")
