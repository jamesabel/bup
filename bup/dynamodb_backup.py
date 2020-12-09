import pickle
from datetime import timedelta
from pathlib import Path

from awsimple import DynamoDBAccess, dynamodb_to_json

from bup import BupBase, BackupTypes, get_preferences, ExclusionPreferences


class DynamoDBBackup(BupBase):

    backup_type = BackupTypes.DynamoDB

    def run(self):
        preferences = get_preferences(self.ui_type)
        backup_directory = preferences.backup_directory
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(self.backup_type.name).get()

        tables = DynamoDBAccess(profile_name=preferences.aws_profile).get_table_names()
        self.info_out(f"backing up {len(tables)} DynamoDB tables")
        count = 0
        for table_name in tables:

            # awsimple will update immediately if number of table rows changes, but backup from scratch every so often to be safe
            cache_life = timedelta(days=7).total_seconds()

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
