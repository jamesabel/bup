"""
Tests for transfer accounting (bup/transfer.py) and how BupBase reports it.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import logging

import pytest
from awsimple import S3RequestTier

from bup import BupBase, BackupTypes, UITypes, __application_name__
from bup.transfer import (
    TransferRecord,
    transfer_emitter,
    bytes_per_gb,
    get_charged_request_count,
    get_transfer_out_cost,
    get_dynamodb_scan_cost,
    get_s3_cost,
    get_s3_request_cost,
    get_s3_retrieval_cost,
    get_transfer_total,
    format_size,
    format_cost,
)

from .aws_price_offers import make_prices


class _TransferBackup(BupBase):
    backup_type = BackupTypes.S3

    def run_backup(self):
        pass


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def emitted_records():
    records = []
    transfer_emitter.transfer_signal.connect(records.append)
    yield records
    transfer_emitter.transfer_signal.disconnect(records.append)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_costs_use_the_regions_prices():
    aws_prices = make_prices("us-east-1", 0.09, 0.125, 0.0)

    assert get_transfer_out_cost(10 * bytes_per_gb, aws_prices) == pytest.approx(0.90)
    assert get_transfer_out_cost(0, aws_prices) == 0.0
    assert get_dynamodb_scan_cost(10 * bytes_per_gb, 2000000.0, aws_prices) == pytest.approx(0.90 + 0.25)  # transfer out plus reads


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_costs_are_unknown_without_prices():
    # unknown, as opposed to free
    assert get_transfer_out_cost(10 * bytes_per_gb, None) is None
    assert get_dynamodb_scan_cost(10 * bytes_per_gb, 2000000.0, None) is None
    assert get_s3_cost(10 * bytes_per_gb, {(S3RequestTier.tier2, "STANDARD"): 1000}, {"STANDARD": 10 * bytes_per_gb}, None) is None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_requests_are_priced_by_tier_and_storage_class():
    aws_prices = make_prices("us-east-1")  # per 1000 requests: $0.005 tier 1, and tier 2 $0.0004 STANDARD, $0.001 STANDARD_IA, $0.01 GLACIER_IR

    assert get_s3_request_cost({}, aws_prices) == 0.0
    assert get_s3_request_cost({(S3RequestTier.tier1, "STANDARD"): 2000}, aws_prices) == pytest.approx(0.01)
    assert get_s3_request_cost({(S3RequestTier.tier2, "STANDARD"): 10000}, aws_prices) == pytest.approx(0.004)
    assert get_s3_request_cost({(S3RequestTier.tier2, "GLACIER_IR"): 10000}, aws_prices) == pytest.approx(0.1)  # 25 times a STANDARD one
    assert get_s3_request_cost({(S3RequestTier.tier2, "STANDARD_IA"): 3000, (S3RequestTier.tier2, "GLACIER_IR"): 1000}, aws_prices) == pytest.approx(0.003 + 0.01)
    # a storage class the region has no price for is priced as STANDARD
    assert get_s3_request_cost({(S3RequestTier.tier2, "REDUCED_REDUNDANCY"): 10000}, aws_prices) == pytest.approx(0.004)
    # a listing is tier 1 at one price, whatever storage class it is counted as
    assert get_s3_request_cost({(S3RequestTier.tier1, "GLACIER_IR"): 2000}, aws_prices) == pytest.approx(0.01)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_requests_that_are_free_are_not_charged_or_counted():
    tier_counts = {(S3RequestTier.free, "STANDARD"): 500, (S3RequestTier.tier1, "STANDARD"): 2, (S3RequestTier.tier2, "GLACIER_IR"): 3}

    assert get_charged_request_count(tier_counts) == 5
    assert get_charged_request_count({}) == 0
    assert get_s3_request_cost({(S3RequestTier.free, "STANDARD"): 500}, make_prices("us-east-1")) == 0.0


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_cost_is_the_data_transfer_plus_the_requests_plus_the_retrieval_fees():
    aws_prices = make_prices("us-east-1")

    assert get_s3_cost(10 * bytes_per_gb, {(S3RequestTier.tier2, "STANDARD"): 10000}, {"STANDARD": 10 * bytes_per_gb}, aws_prices) == pytest.approx(0.90 + 0.004)
    # the same from Glacier Instant Retrieval: its requests are 25 times the price, and a third of the data transfer is added as its retrieval fee
    assert get_s3_cost(10 * bytes_per_gb, {(S3RequestTier.tier2, "GLACIER_IR"): 10000}, {"GLACIER_IR": 10 * bytes_per_gb}, aws_prices) == pytest.approx(0.90 + 0.1 + 0.30)
    assert get_s3_cost(0, {}, {}, aws_prices) == 0.0


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_retrieval_fee_is_per_gb_read_of_the_storage_classes_that_have_one():
    aws_prices = make_prices("us-east-1")  # per GB: $0.01 STANDARD_IA, $0.03 GLACIER_IR

    assert get_s3_retrieval_cost({}, aws_prices) == 0.0
    assert get_s3_retrieval_cost({"STANDARD": 100 * bytes_per_gb, "INTELLIGENT_TIERING": 100 * bytes_per_gb}, aws_prices) == 0.0  # no retrieval fee
    assert get_s3_retrieval_cost({"GLACIER_IR": 10 * bytes_per_gb}, aws_prices) == pytest.approx(0.30)
    assert get_s3_retrieval_cost({"STANDARD": bytes_per_gb, "STANDARD_IA": 2 * bytes_per_gb, "GLACIER_IR": bytes_per_gb // 2}, aws_prices) == pytest.approx(0.02 + 0.015)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_transfer_record_text_and_total_with_s3_requests():
    transfer_record = TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5, requests=1200)
    assert str(transfer_record) == "my-bucket : received 2.0 KB, 1200 S3 requests, approximately $0.5000 before any AWS free allowance"

    total = get_transfer_total(BackupTypes.S3, [transfer_record, TransferRecord(BackupTypes.S3, "my-bucket (verification)", 0, cost=0.25, requests=300)])
    assert total == TransferRecord(BackupTypes.S3, "transfer total", 2048, cost=0.75, requests=1500)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(1023) == "1023 B"
    assert format_size(1536) == "1.5 KB"
    assert format_size(5 * 1024**2) == "5.0 MB"
    assert format_size(bytes_per_gb) == "1.0 GB"
    assert format_size(3 * 1024**5) == "3072.0 TB"  # TB is the largest unit


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_format_cost():
    assert format_cost(0.0) == "$0.0000"
    assert format_cost(0.00001) == "less than $0.0001"
    assert format_cost(0.0123) == "$0.0123"
    assert format_cost(12.345) == "$12.35"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_transfer_record_text():
    assert str(TransferRecord(BackupTypes.github, "owner/repo", 2048)) == "owner/repo : received 2.0 KB"
    assert str(TransferRecord(BackupTypes.S3, "my-bucket", bytes_per_gb, cost=0.09)) == "my-bucket : received 1.0 GB, approximately $0.0900 before any AWS free allowance"
    assert str(TransferRecord(BackupTypes.DynamoDB, "my_table", 2048, 12.5, 0.5)) == "my_table : received 2.0 KB, 12.5 read units, approximately $0.5000 before any AWS free allowance"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_transfer_total():
    total = get_transfer_total(BackupTypes.DynamoDB, [TransferRecord(BackupTypes.DynamoDB, "a", 100, 1.5, 0.25), TransferRecord(BackupTypes.DynamoDB, "b", 200, 2.0, 0.5)])
    assert total == TransferRecord(BackupTypes.DynamoDB, "transfer total", 300, 3.5, 0.75)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_transfer_total_across_backup_types_with_its_own_name():
    grand_total = get_transfer_total(None, [TransferRecord(BackupTypes.S3, "a", 100, cost=0.25), TransferRecord(BackupTypes.github, "b", 200)], "Grand total")
    assert grand_total == TransferRecord(None, "Grand total", 300, 0.0, 0.25)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_transfer_total_without_costs_has_no_cost():
    # GitHub transfers have no cost, and neither does their total (as opposed to a cost of zero)
    assert get_transfer_total(BackupTypes.github, [TransferRecord(BackupTypes.github, "a", 100)]).cost is None
    assert get_transfer_total(BackupTypes.github, []) == TransferRecord(BackupTypes.github, "transfer total", 0)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cli_transfer_is_part_of_the_regular_output(emitted_records):
    infos = []
    backup = _TransferBackup(UITypes.cli, infos.append, lambda s: None, lambda s: None)
    transfer_record = TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.01)

    backup.transfer_out(transfer_record)
    backup.transfer_summary_out()

    assert infos == [str(transfer_record), "transfer total : received 2.0 KB, approximately $0.0100 before any AWS free allowance"]
    assert emitted_records == [transfer_record]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_gui_transfer_goes_to_the_transfer_tab_and_the_log_not_the_backup_output(emitted_records, caplog):
    infos = []
    backup = _TransferBackup(UITypes.gui, infos.append, lambda s: None, lambda s: None)
    transfer_record = TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.01)

    with caplog.at_level(logging.INFO, logger=__application_name__):
        backup.transfer_out(transfer_record)
        backup.transfer_summary_out()

    assert infos == []
    assert emitted_records == [transfer_record]
    logged = [record for record in caplog.records if "received 2.0 KB" in record.getMessage()]
    assert len(logged) == 2  # the record and the total
    assert all(record.backup_type == BackupTypes.S3 for record in logged)  # so the Log tab routes them to the S3 pane


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_start_resets_transfer_records():
    backup = _TransferBackup(UITypes.cli, lambda s: None, lambda s: None, lambda s: None)
    backup.transfer_out(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.01))

    backup.start()
    backup.wait()

    assert backup.transfer_records == []
