"""
The DynamoDB backup: every table is scanned in full (through awsimple, which caches a scan while the table has not changed) and
written to <backup directory>/dynamodb as a pickle file and a JSON file.
"""

import pickle
from datetime import timedelta
from pathlib import Path
from typing import Optional

from botocore.exceptions import BotoCoreError, ClientError
from awsimple import DynamoDBAccess, dynamodb_to_json
from balsa import get_logger

from bup import BupBase, BackupTypes, get_preferences, ExclusionPreferences, __application_name__
from bup.aws_access import get_aws_access_kwargs
from bup.transfer import TransferRecord, get_dynamodb_scan_cost
from bup.aws_prices import get_aws_prices

log = get_logger(__application_name__)

# awsimple scans a table again as soon as its number of rows changes, but back up from scratch every so often to be safe
table_cache_life = timedelta(days=1).total_seconds()


class DynamoDBScanMeter:
    """
    Measures the DynamoDB table scans a boto3 client makes: the size of the responses (what was received over the network) and the read
    units consumed (what on-demand tables are billed for). awsimple does the scans, so this hooks the client's events rather than the calls.
    """

    scan_operation = "dynamodb.Scan"

    def __init__(self):
        self.response_bytes = 0
        self.read_units = 0.0

    def attach(self, client):
        """
        Start measuring the scans of a boto3 DynamoDB client.
        """
        client.meta.events.register(f"provide-client-params.{self.scan_operation}", self.request_consumed_capacity)
        client.meta.events.register(f"after-call.{self.scan_operation}", self.record_response)

    def request_consumed_capacity(self, params: dict, **kwargs):
        """
        Event handler, before a scan request is made: ask for the read units the scan consumes (DynamoDB only reports them when asked to).
        """
        params.setdefault("ReturnConsumedCapacity", "TOTAL")

    def record_response(self, http_response, parsed: dict, **kwargs):
        """
        Event handler, after a scan response is received: add its size and the read units it consumed.
        """
        self.response_bytes += len(http_response.content)
        self.read_units += float(parsed.get("ConsumedCapacity", {}).get("CapacityUnits", 0.0))


def write_table_files(dir_path: Path, table_name: str, table_contents: list):
    """
    Write the contents of a table as <table name>.pickle (exactly what the scan returned) and <table name>.json (readable anywhere).
    Raises OSError if a file can not be written.

    :param dir_path: the directory to write to (made if it does not exist)
    :param table_name: the table
    :param table_contents: the items of the table
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    with Path(dir_path, f"{table_name}.pickle").open("wb") as f:
        pickle.dump(table_contents, f)
    with Path(dir_path, f"{table_name}.json").open("w", encoding="utf-8") as f:
        f.write(dynamodb_to_json(table_contents, indent=4))


class DynamoDBBackup(BupBase):
    """
    Backs up every DynamoDB table of the region (other than the excluded ones) to <backup directory>/dynamodb.
    """

    backup_type = BackupTypes.DynamoDB

    def scan_transfer_out(self, table_name: str, table: DynamoDBAccess, scan_meter: DynamoDBScanMeter):
        """
        Report what the scan of a table received and approximately what AWS charges for it. A scan that failed part way still received
        (and is charged for) what it read. A scan that awsimple served from its cache received nothing, and nothing is reported.
        """
        if scan_meter.response_bytes > 0:
            region = table.resource.meta.client.meta.region_name  # tables are in the region of the client that scans them
            cost = get_dynamodb_scan_cost(scan_meter.response_bytes, scan_meter.read_units, get_aws_prices(region))
            self.transfer_out(TransferRecord(BackupTypes.DynamoDB, table_name, scan_meter.response_bytes, scan_meter.read_units, cost, region))

    def scan_table(self, preferences, table_name: str) -> Optional[list]:
        """
        Get the contents of a table, and report what that received.

        :return: the items of the table, or None if the table could not be scanned (which is reported as an error)
        """
        table = DynamoDBAccess(table_name, cache_life=table_cache_life, **get_aws_access_kwargs(preferences))
        scan_meter = DynamoDBScanMeter()
        scan_meter.attach(table.resource.meta.client)  # the client the table scan goes through
        try:
            return table.scan_table_cached()
        except (ClientError, BotoCoreError) as e:
            self.error_out(f"could not scan {table_name} : {e}")
            return None
        finally:
            self.scan_transfer_out(table_name, table, scan_meter)

    def backup_table(self, preferences, table_name: str) -> bool:
        """
        Back up one table: scan it and write its files. A failure is reported as an error.

        :return: True if the table was backed up
        """
        if (table_contents := self.scan_table(preferences, table_name)) is None:
            return False
        try:
            write_table_files(Path(preferences.backup_directory, "dynamodb"), table_name, table_contents)
        except OSError as e:
            self.error_out(f"could not write backup files for {table_name} : {e}")
            return False
        return True

    def run_backup(self):
        """
        Back up every table. A failure of one table does not end the backup of the others.
        """
        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(self.backup_type.name).get_no_comments()

        try:
            dynamodb_access = DynamoDBAccess(**get_aws_access_kwargs(preferences))  # making the access raises if the AWS profile does not exist
            tables = dynamodb_access.get_table_names()
        except (ClientError, BotoCoreError) as e:
            # BotoCoreError covers e.g. ProfileNotFound, NoCredentialsError and EndpointConnectionError
            self.error_out(f"could not list DynamoDB tables - check credentials and connectivity : {e}")
            return
        self.info_out(f"found {len(tables)} DynamoDB tables")

        count = 0
        for table_name in tables:
            if self.stop_requested:
                break

            if table_name in exclusions:
                self.info_out(f"excluding {table_name}")
            elif dry_run:
                self.info_out(f"dry run {table_name}")
            else:
                self.info_out(f"{table_name}")
                if self.backup_table(preferences, table_name):
                    count += 1

        self.info_out(f"{len(tables)} tables, {count} backed up, {len(exclusions)} excluded")
        if not dry_run:
            self.transfer_summary_out()
