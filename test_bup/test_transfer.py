"""
Tests for transfer accounting (bup/transfer.py) and how BupBase reports it.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

import logging

import pytest

from bup import BupBase, BackupTypes, UITypes, __application_name__
from bup.aws_prices import AWSPrices
from bup.transfer import (
    TransferRecord,
    transfer_emitter,
    bytes_per_gb,
    get_transfer_out_cost,
    get_dynamodb_scan_cost,
    get_transfer_total,
    format_size,
    format_cost,
)


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
    aws_prices = AWSPrices("us-east-1", 0.09, 0.125, 0.0)

    assert get_transfer_out_cost(10 * bytes_per_gb, aws_prices) == pytest.approx(0.90)
    assert get_transfer_out_cost(0, aws_prices) == 0.0
    assert get_dynamodb_scan_cost(10 * bytes_per_gb, 2000000.0, aws_prices) == pytest.approx(0.90 + 0.25)  # transfer out plus reads


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_costs_are_unknown_without_prices():
    # unknown, as opposed to free
    assert get_transfer_out_cost(10 * bytes_per_gb, None) is None
    assert get_dynamodb_scan_cost(10 * bytes_per_gb, 2000000.0, None) is None


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
