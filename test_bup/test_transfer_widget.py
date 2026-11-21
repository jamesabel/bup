"""
Tests for the GUI's Transfer tab.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from PyQt5.QtWidgets import QApplication, QAbstractSpinBox, QLineEdit

from bup import BackupTypes, aws_prices
from bup.aws_prices import AWSPrices, AWSPriceCache
from bup.gui.transfer_widget import TransferWidget, columns, no_prices_text
from bup.transfer import TransferRecord, transfer_emitter


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def transfer_widget(qapp):
    return TransferWidget()


def qapp_process_events():
    QApplication.instance().processEvents()  # let the shown widget lay itself out


def _row_text(transfer_widget: TransferWidget, row: int) -> dict:
    return {column_name: transfer_widget.table.item(row, column).text() for column, column_name in enumerate(columns)}


def _cache_prices(region: str, transfer_out_price_per_gb: float, fetched: datetime):
    AWSPriceCache(aws_prices.get_aws_price_cache_path()).put(AWSPrices(region, transfer_out_price_per_gb, 0.125, fetched.timestamp()))


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_no_prices_yet(transfer_widget):
    assert transfer_widget.prices_label.text() == no_prices_text


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_prices_are_shown_but_cannot_be_entered(qapp):
    _cache_prices("us-east-1", 0.09, datetime(2026, 11, 20, 12, 0))
    _cache_prices("ap-southeast-2", 0.114, datetime(2026, 11, 21, 12, 0))

    transfer_widget = TransferWidget()

    assert transfer_widget.prices_label.text() == (
        "ap-southeast-2 : $0.114 per GB data transfer out, $0.125 per million DynamoDB read units (from AWS on 2026-11-21)\n"
        "us-east-1 : $0.09 per GB data transfer out, $0.125 per million DynamoDB read units (from AWS on 2026-11-20)"
    )
    # bup gets the prices itself - there is nothing for the user to type a price into
    assert transfer_widget.findChildren(QAbstractSpinBox) == []
    assert transfer_widget.findChildren(QLineEdit) == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_prices_fetched_by_a_backup_appear_with_its_transfer(transfer_widget):
    _cache_prices("us-east-1", 0.09, datetime(2026, 11, 20, 12, 0))  # as a backup does just before it reports a transfer

    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5, region="us-east-1"))

    assert transfer_widget.prices_label.text().startswith("us-east-1 : $0.09 per GB data transfer out")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_unreadable_price_cache_is_reported_in_place_of_the_prices(qapp):
    cache_path = aws_prices.get_aws_price_cache_path()
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"this is not a SQLite database, and is long enough to not look like an empty one" * 10)

    transfer_widget = TransferWidget()

    assert transfer_widget.prices_label.text().startswith("AWS prices not available")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_reported_transfer_is_shown_most_recent_first(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5, region="eu-west-1"))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.DynamoDB, "my_table", 1024, 12.5, 0.25, "us-west-2"))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.github, "owner/repo", 4096))

    assert transfer_widget.table.rowCount() == 3
    github_row = _row_text(transfer_widget, 0)
    del github_row["Time"]
    assert github_row == {"Backup": "github", "Name": "owner/repo", "Region": "", "Received": "4.0 KB", "Read units": "", "Approximate cost": ""}
    dynamodb_row = _row_text(transfer_widget, 1)
    del dynamodb_row["Time"]
    assert dynamodb_row == {"Backup": "DynamoDB", "Name": "my_table", "Region": "us-west-2", "Received": "1.0 KB", "Read units": "12.5", "Approximate cost": "$0.2500"}
    s3_row = _row_text(transfer_widget, 2)
    assert s3_row["Time"] != ""
    del s3_row["Time"]
    assert s3_row == {"Backup": "S3", "Name": "my-bucket", "Region": "eu-west-1", "Received": "2.0 KB", "Read units": "", "Approximate cost": "$0.5000"}


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cost_column_is_only_as_wide_as_its_contents(transfer_widget):
    # an empty spacer column on the far right takes up the remaining width, not the "Approximate cost" column
    transfer_widget.show()
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5, region="eu-west-1"))
    qapp_process_events()
    header = transfer_widget.table.horizontalHeader()
    cost_column = columns.index("Approximate cost")
    spacer_column = len(columns)
    assert transfer_widget.table.columnCount() == spacer_column + 1
    assert transfer_widget.table.horizontalHeaderItem(spacer_column).text() == ""
    cost_width = header.sectionSize(cost_column)
    spacer_width = header.sectionSize(spacer_column)

    # make the tab wider - all of the extra width goes to the spacer
    extra_width = 400
    transfer_widget.resize(transfer_widget.width() + extra_width, transfer_widget.height())
    qapp_process_events()

    assert header.sectionSize(cost_column) == cost_width
    assert header.sectionSize(spacer_column) == spacer_width + extra_width


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_transfer_without_known_prices_has_no_cost(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=None, region="us-east-1"))

    assert _row_text(transfer_widget, 0)["Approximate cost"] == ""
    assert transfer_widget.total_labels[BackupTypes.S3].text() == "S3 transfer total : received 2.0 KB"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_totals_per_backup_type(transfer_widget):
    assert transfer_widget.total_labels[BackupTypes.S3].text() == "S3 transfer total : received 0 B"

    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "bucket-a", 1024, cost=0.25))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "bucket-b", 1024, cost=0.5))

    assert transfer_widget.total_labels[BackupTypes.S3].text() == "S3 transfer total : received 2.0 KB, approximately $0.7500 before any AWS free allowance"
    assert transfer_widget.total_labels[BackupTypes.github].text() == "github transfer total : received 0 B"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_are_capped_but_totals_are_not(transfer_widget):
    with patch("bup.gui.transfer_widget.max_transfer_rows", 2):
        for bucket_number in range(3):
            transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, f"bucket-{bucket_number}", 1024, cost=0.25))

    assert transfer_widget.table.rowCount() == 2
    assert _row_text(transfer_widget, 0)["Name"] == "bucket-2"  # the oldest row was dropped
    assert transfer_widget.total_labels[BackupTypes.S3].text().startswith("S3 transfer total : received 3.0 KB")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_clear(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5))

    transfer_widget.clear_button.click()

    assert transfer_widget.table.rowCount() == 0
    assert transfer_widget.total_labels[BackupTypes.S3].text() == "S3 transfer total : received 0 B"
