import pickle
from datetime import timedelta
from pathlib import Path

from awsimple import DynamoDBAccess

from bup import BupBase, BackupTypes


class DynamoDBBackup(BupBase):

    backup_type = BackupTypes.DynamoDB

    def run(self):

        tables = DynamoDBAccess(profile_name=self.aws_profile).get_table_names()
        self.info_out(f"backing up {len(tables)} DynamoDB tables")
        if self.dry_run:
            self.info_out("*** DRY RUN ***")
        count = 0
        for table_name in tables:
            self.info_out(f"{table_name}")

            # awsimple will update immediately if number of table rows changes, but backup from scratch every so often to be safe
            cache_life = timedelta(days=7).total_seconds()

            if self.excludes is not None and table_name in self.excludes:
                self.info_out(f"\rexcluding {table_name}")
            else:
                table = DynamoDBAccess(table_name, cache_life=cache_life)
                table_contents = table.scan_table_cached()
                if not self.dry_run:
                    dir_path = Path(self.backup_directory, "dynamodb")
                    dir_path.mkdir(parents=True, exist_ok=True)
                    with Path(dir_path, f"{table_name}.pickle").open("wb") as f:
                        pickle.dump(table_contents, f)
                        count += 1
        self.info_out(f"backed up {count} tables")
