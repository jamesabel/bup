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
from bup.transfer import TransferRecord, get_dynamodb_scan_cost
from bup.aws_prices import get_aws_prices

log = get_logger(__application_name__)


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
        client.meta.events.register(f"provide-client-params.{self.scan_operation}", self.request_consumed_capacity)
        client.meta.events.register(f"after-call.{self.scan_operation}", self.record_response)

    def request_consumed_capacity(self, params: dict, **kwargs):
        # DynamoDB only reports the read units a scan consumed when asked to
        params.setdefault("ReturnConsumedCapacity", "TOTAL")

    def record_response(self, http_response, parsed: dict, **kwargs):
        self.response_bytes += len(http_response.content)
        self.read_units += float(parsed.get("ConsumedCapacity", {}).get("CapacityUnits", 0.0))


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
                scan_meter = DynamoDBScanMeter()
                scan_meter.attach(table.resource.meta.client)  # the client the table scan goes through
                try:
                    table_contents = table.scan_table_cached()
                except (ClientError, BotoCoreError) as e:
                    # don't let one failed table kill the backup of the remaining tables
                    self.error_out(f"could not scan {table_name} : {e}")
                    continue
                finally:
                    # a scan that failed part way still received (and is charged for) what it read; a cached scan received nothing
                    if scan_meter.response_bytes > 0:
                        region = table.resource.meta.client.meta.region_name  # tables are in the region of the client that scans them
                        cost = get_dynamodb_scan_cost(scan_meter.response_bytes, scan_meter.read_units, get_aws_prices(region))
                        self.transfer_out(TransferRecord(BackupTypes.DynamoDB, table_name, scan_meter.response_bytes, scan_meter.read_units, cost, region))

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
        if not dry_run:
            self.transfer_summary_out()
