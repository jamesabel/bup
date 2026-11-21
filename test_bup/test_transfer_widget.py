"""
Tests for the GUI's Transfer tab.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from unittest.mock import patch, MagicMock

import pytest

from bup import BackupTypes
from bup.gui.transfer_widget import TransferWidget, columns
from bup.transfer import TransferRecord, transfer_emitter


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def gui_preferences():
    preferences = MagicMock(aws_transfer_out_price_per_gb=None, dynamodb_read_price_per_million_units=None)
    with patch("bup.gui.transfer_widget.get_gui_preferences", return_value=preferences):
        yield preferences


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def transfer_widget(qapp, gui_preferences):
    return TransferWidget()


def _row_text(transfer_widget: TransferWidget, row: int) -> dict:
    return {column_name: transfer_widget.table.item(row, column).text() for column, column_name in enumerate(columns)}


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_prices_default_until_set(transfer_widget):
    assert transfer_widget.transfer_out_price.value() == 0.09
    assert transfer_widget.dynamodb_read_price.value() == 0.125


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_prices_load_from_preferences_without_saving(qapp, gui_preferences):
    gui_preferences.aws_transfer_out_price_per_gb = 0.12
    gui_preferences.dynamodb_read_price_per_million_units = 0.25

    transfer_widget = TransferWidget()

    assert transfer_widget.transfer_out_price.value() == 0.12
    assert transfer_widget.dynamodb_read_price.value() == 0.25
    assert gui_preferences.aws_transfer_out_price_per_gb == 0.12  # loading is not a change


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_changed_prices_are_saved(transfer_widget, gui_preferences):
    transfer_widget.transfer_out_price.setValue(0.05)
    transfer_widget.dynamodb_read_price.setValue(0.3)

    assert gui_preferences.aws_transfer_out_price_per_gb == 0.05
    assert gui_preferences.dynamodb_read_price_per_million_units == 0.3


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_reported_transfer_is_shown_most_recent_first(transfer_widget):
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.S3, "my-bucket", 2048, cost=0.5))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.DynamoDB, "my_table", 1024, 12.5, 0.25))
    transfer_emitter.transfer_signal.emit(TransferRecord(BackupTypes.github, "owner/repo", 4096))

    assert transfer_widget.table.rowCount() == 3
    github_row = _row_text(transfer_widget, 0)
    assert (github_row["Backup"], github_row["Name"], github_row["Received"], github_row["Read units"], github_row["Approximate cost"]) == ("github", "owner/repo", "4.0 KB", "", "")
    dynamodb_row = _row_text(transfer_widget, 1)
    assert (dynamodb_row["Backup"], dynamodb_row["Name"], dynamodb_row["Received"], dynamodb_row["Read units"], dynamodb_row["Approximate cost"]) == (
        "DynamoDB",
        "my_table",
        "1.0 KB",
        "12.5",
        "$0.2500",
    )
    s3_row = _row_text(transfer_widget, 2)
    assert (s3_row["Backup"], s3_row["Name"], s3_row["Received"], s3_row["Read units"], s3_row["Approximate cost"]) == ("S3", "my-bucket", "2.0 KB", "", "$0.5000")
    assert s3_row["Time"] != ""


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
