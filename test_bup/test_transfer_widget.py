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
def test_reported_transfer_is_shown(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.github, "owner/repo", 4096))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.DynamoDB, "my_table", 1024, 12.5, 0.25, "us-west-2"))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5, region="eu-west-1"))

    assert transfer_widget.table.rowCount() == 3
    s3_row = _row_text(transfer_widget, 0)
    assert s3_row["Time"] != ""
    del s3_row["Time"]
    assert s3_row == {"Backup": "S3", "Name": "my-bucket", "Region": "eu-west-1", "Received": "2.0 KB", "Read units": "", "Approximate cost": "$0.5000"}
    dynamodb_row = _row_text(transfer_widget, 1)
    del dynamodb_row["Time"]
    assert dynamodb_row == {"Backup": "DynamoDB", "Name": "my_table", "Region": "us-west-2", "Received": "1.0 KB", "Read units": "12.5", "Approximate cost": "$0.2500"}
    github_row = _row_text(transfer_widget, 2)
    del github_row["Time"]
    assert github_row == {"Backup": "github", "Name": "owner/repo", "Region": "", "Received": "4.0 KB", "Read units": "", "Approximate cost": ""}


def _names(transfer_widget: TransferWidget) -> list:
    return [_row_text(transfer_widget, row)["Name"] for row in range(transfer_widget.table.rowCount())]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_are_sorted_by_cost_highest_at_the_top(transfer_widget):
    # reported in neither cost order nor reverse cost order
    for name, cost in (("middle", 0.25), ("lowest", 0.001), ("highest", 12.5), ("second", 3.0), ("free", 0.0)):
        transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, name, 1024, cost=cost))

    assert _names(transfer_widget) == ["highest", "second", "middle", "lowest", "free"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_are_sorted_by_cost_not_by_how_the_cost_is_written(transfer_widget):
    # as text "$9.00" sorts above "$10.00"
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "nine", 1024, cost=9.0))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "ten", 1024, cost=10.0))

    assert _names(transfer_widget) == ["ten", "nine"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_without_a_cost_are_below_those_with_one_by_size(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.github, "small-repo", 1024))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "free-bucket", 512, cost=0.0))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.github, "big-repo", 4096))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "prices-unknown-bucket", 2048, cost=None))

    assert _names(transfer_widget) == ["free-bucket", "big-repo", "prices-unknown-bucket", "small-repo"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_of_equal_cost_are_by_size_then_most_recent_first(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "first", 1024, cost=0.5))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "bigger", 2048, cost=0.5))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "second", 1024, cost=0.5))

    assert _names(transfer_widget) == ["bigger", "second", "first"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_stay_sorted_after_clear(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "before-clear", 1024, cost=100.0))
    transfer_widget.clear_button.click()

    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "low", 1024, cost=0.25))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "high", 1024, cost=0.5))

    assert _names(transfer_widget) == ["high", "low"]


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
def test_grand_total_is_all_backup_types_together(transfer_widget):
    assert transfer_widget.grand_total_label.text() == "Grand total : received 0 B"

    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 1024, cost=0.5))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.DynamoDB, "my_table", 2048, 12.5, 0.25))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.github, "owner/repo", 1024))  # received bytes count, and it has no cost

    assert transfer_widget.grand_total_label.text() == "Grand total : received 4.0 KB, 12.5 read units, approximately $0.7500 before any AWS free allowance"
    assert transfer_widget.grand_total_label.font().bold()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_grand_total_is_cleared_with_the_rest(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 1024, cost=0.5))

    transfer_widget.clear_button.click()

    assert transfer_widget.grand_total_label.text() == "Grand total : received 0 B"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_rows_are_capped_but_totals_are_not(transfer_widget):
    with patch("bup.gui.transfer_widget.max_transfer_rows", 2):
        for name, cost in (("lowest", 0.25), ("highest", 1.0), ("middle", 0.5)):
            transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, name, 1024, cost=cost))

    assert _names(transfer_widget) == ["highest", "middle"]  # the lowest cost row was dropped
    assert transfer_widget.total_labels[BackupTypes.S3].text().startswith("S3 transfer total : received 3.0 KB")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_clear(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5))

    transfer_widget.clear_button.click()

    assert transfer_widget.table.rowCount() == 0
    assert transfer_widget.total_labels[BackupTypes.S3].text() == "S3 transfer total : received 0 B"
