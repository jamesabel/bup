"""
Tests for what the DynamoDB backup reports as received from DynamoDB.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from bup import UITypes
from bup.dynamodb_backup import DynamoDBBackup, DynamoDBScanMeter


def _make_preferences(tmp_path: Path, dry_run: bool = False) -> MagicMock:
    return MagicMock(
        backup_directory=str(tmp_path),
        dry_run=dry_run,
        aws_profile=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_region=None,
        aws_transfer_out_price_per_gb=None,
        dynamodb_read_price_per_million_units=None,
    )


def _make_table(scan_responses: list, scan_error=None) -> MagicMock:
    """
    A stand-in for awsimple's DynamoDBAccess of one table, whose scan delivers the given (response size, read units) responses to
    whatever is registered for the scan's "after-call" event - as the real boto3 client does - and then optionally fails.
    """
    table = MagicMock()
    handlers = {}
    table.resource.meta.client.meta.events.register.side_effect = lambda event_name, handler: handlers.update({event_name: handler})

    def scan_table_cached():
        for response_size, read_units in scan_responses:
            handlers["after-call.dynamodb.Scan"](http_response=MagicMock(content=b"x" * response_size), parsed={"ConsumedCapacity": {"CapacityUnits": read_units}})
        if scan_error is not None:
            raise scan_error
        return [{"id": 1}]

    table.scan_table_cached.side_effect = scan_table_cached
    return table


def _run_backup(tmp_path: Path, table: MagicMock, dry_run: bool = False) -> list:
    """
    Run a DynamoDB backup of "my_table".
    :return: the backup's info output
    """
    list_access = MagicMock()
    list_access.get_table_names.return_value = ["my_table"]
    infos = []
    backup = DynamoDBBackup(UITypes.cli, infos.append, lambda s: None, lambda s: None)
    with (
        patch("bup.dynamodb_backup.get_preferences", return_value=_make_preferences(tmp_path, dry_run)),
        patch("bup.dynamodb_backup.DynamoDBAccess", side_effect=lambda *args, **kwargs: table if args else list_access),
        patch("bup.dynamodb_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.dynamodb_backup.dynamodb_to_json", return_value="{}"),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def mock_dynamodb(monkeypatch):
    # credentials for moto's in-process AWS, and nothing from this machine's real AWS configuration
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_scan_meter_measures_a_real_boto3_scan(mock_dynamodb):
    table = mock_dynamodb.create_table(
        TableName="my_table", KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST"
    )
    for item_number in range(3):
        table.put_item(Item={"id": str(item_number), "data": "x" * 1000})
    scan_meter = DynamoDBScanMeter()
    scan_meter.attach(mock_dynamodb.meta.client)
    scan_parameters = []
    mock_dynamodb.meta.client.meta.events.register("before-call.dynamodb.Scan", lambda params, **kwargs: scan_parameters.append(params["body"]))

    items = table.scan()["Items"]  # through the resource, as awsimple scans

    assert len(items) == 3
    assert scan_meter.response_bytes > 3000  # the three 1000 character items, plus the response's overhead
    assert b"ReturnConsumedCapacity" in scan_parameters[0]  # DynamoDB was asked to report the read units


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_scan_meter_adds_up_the_pages_of_a_scan():
    scan_meter = DynamoDBScanMeter()

    scan_meter.record_response(http_response=MagicMock(content=b"x" * 100), parsed={"ConsumedCapacity": {"CapacityUnits": 1.5}})
    scan_meter.record_response(http_response=MagicMock(content=b"x" * 50), parsed={})  # no consumed capacity reported

    assert scan_meter.response_bytes == 150
    assert scan_meter.read_units == 1.5


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_scan_meter_does_not_override_a_callers_consumed_capacity_request():
    params = {"TableName": "my_table", "ReturnConsumedCapacity": "INDEXES"}

    DynamoDBScanMeter().request_consumed_capacity(params)

    assert params["ReturnConsumedCapacity"] == "INDEXES"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_scanned_bytes_read_units_and_cost_are_reported(tmp_path):
    # 2 GB in two pages and 16 million read units: $0.18 of data transfer out plus $2 of reads at the default prices
    infos = _run_backup(tmp_path, _make_table([(1024**3, 8000000.0), (1024**3, 8000000.0)]))

    assert "my_table : received 2.0 GB, 1.6e+07 read units, approximately $2.18 before any AWS free allowance" in infos
    assert "transfer total : received 2.0 GB, 1.6e+07 read units, approximately $2.18 before any AWS free allowance" in infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cached_scan_reports_only_a_zero_total(tmp_path):
    # a scan served from awsimple's cache makes no DynamoDB calls
    infos = _run_backup(tmp_path, _make_table([]))

    assert not any(info.startswith("my_table : received") for info in infos)
    assert "transfer total : received 0 B" in infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_failed_scan_still_reports_what_it_received(tmp_path):
    scan_error = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}}, "Scan")

    infos = _run_backup(tmp_path, _make_table([(2048, 4.0)], scan_error))

    assert any(info.startswith("my_table : received 2.0 KB, 4 read units") for info in infos)
    assert not Path(tmp_path, "dynamodb", "my_table.pickle").exists()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dry_run_reports_no_transfer(tmp_path):
    infos = _run_backup(tmp_path, _make_table([]), dry_run=True)

    assert not any("received" in info for info in infos)
