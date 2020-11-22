import pickle
import logging
from datetime import timedelta
from pathlib import Path

from awsimple import DynamoDBAccess

from bup import __application_name__, BupBase

log = logging.getLogger(__application_name__)


class DynamoDBBackup(BupBase):

    def run(self):

        tables = DynamoDBAccess(profile_name=self.aws_profile).get_table_names()
        print(f"\rbacking up {len(tables)} DynamoDB tables")
        if self.dry_run:
            print("*** DRY RUN ***")
        count = 0
        for table_name in tables:
            print(f"\r{table_name}")

            # awsimple will update immediately if number of table rows changes, but backup from scratch every so often to be safe
            cache_life = timedelta(days=7).total_seconds()

            if self.excludes is not None and table_name in self.excludes:
                print(f"\rexcluding {table_name}")
            else:
                table = DynamoDBAccess(table_name, cache_life=cache_life)
                table_contents = table.scan_table_cached()
                if not self.dry_run:
                    dir_path = Path(self.backup_directory, "dynamodb")
                    dir_path.mkdir(parents=True, exist_ok=True)
                    with Path(dir_path, f"{table_name}.pickle").open("wb") as f:
                        pickle.dump(table_contents, f)
                        count += 1
        print(f"backed up {count} tables")
