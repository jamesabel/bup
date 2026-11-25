"""
The GUI's "Transfer" tab: what each backup received over the network, and approximately what AWS charges for it.
"""

import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from balsa import get_logger

from bup import BackupTypes, __application_name__
from bup.aws_prices import AWSPrices, get_cached_aws_prices, s3_standard_storage_class
from bup.gui.gui_util import get_local_time_string, make_row
from bup.transfer import TransferRecord, transfer_emitter, get_transfer_total, format_size, format_cost

log = get_logger(__application_name__)

max_transfer_rows = 1000  # rows kept in the table (the lowest cost rows are dropped)

columns = ["Time", "Backup", "Name", "Region", "Received", "S3 requests", "Read units", "Approximate cost"]

no_prices_text = "No AWS prices yet. bup gets them from AWS the first time a backup receives data from S3 or DynamoDB."

cost_note = (
    "Costs are approximate. bup gets the prices of each AWS region from AWS and refreshes them periodically. Costs are before the AWS "
    "free allowances (e.g. 100 GB of data transfer a month, shared by the whole AWS account). S3 costs are the data transfer and the "
    "requests (a request is priced by the storage class of its object), but not the retrieval fee some storage classes have. DynamoDB "
    "reads count as on-demand. GitHub does not charge for transfer, so its sizes are informational."
)


def get_s3_request_prices_text(aws_prices: AWSPrices) -> str:
    """
    The S3 request prices of a region: the tier 1 (list) and tier 2 (other) price, then the storage classes whose tier 2 price is not
    the STANDARD one.
    """
    standard_price = aws_prices.get_s3_tier2_request_price_per_thousand(s3_standard_storage_class)
    s = f"per 1000 S3 requests ${aws_prices.s3_tier1_request_price_per_thousand:g} list and ${standard_price:g} other"
    other_prices = [f"{storage_class} ${price:g}" for storage_class, price in sorted(aws_prices.s3_tier2_request_prices_per_thousand.items()) if price != standard_price]
    if other_prices:
        s += f" ({', '.join(other_prices)})"
    return s


def get_prices_text() -> str:
    """
    The AWS prices bup has fetched, one line per region.
    """
    try:
        all_aws_prices = get_cached_aws_prices()
    except (sqlite3.Error, OSError) as e:
        log.warning(f"could not read the AWS price cache : {e}")
        return f"AWS prices not available : {e}"
    if not all_aws_prices:
        return no_prices_text
    return "\n".join(
        f"{aws_prices.region} : ${aws_prices.transfer_out_price_per_gb:g} per GB data transfer out, {get_s3_request_prices_text(aws_prices)}, "
        f"${aws_prices.dynamodb_read_price_per_million_units:g} per million DynamoDB read units (from AWS on {datetime.fromtimestamp(aws_prices.fetched).date().isoformat()})"
        for aws_prices in all_aws_prices
    )


def get_cost_rank(transfer_record: TransferRecord) -> Tuple[bool, float, int]:
    """
    Where a transfer belongs in the table, which is sorted by cost: a higher rank is closer to the top. Transfers without a cost
    (GitHub, or AWS prices not known) rank below every transfer with one, and equal costs rank by the size received.
    """
    has_cost = transfer_record.cost is not None
    return has_cost, transfer_record.cost if has_cost else 0.0, transfer_record.received_bytes


class TransferWidget(QWidget):
    """
    "Transfer" tab - what each backup received over the network and approximately what AWS charges for it, one row per S3 bucket,
    DynamoDB table or GitHub repo that received anything (highest cost at the top), with totals per backup type since bup was started
    (or the tab was cleared).
    """

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        # the prices in use (read-only - bup gets them from AWS)
        self.prices_widget = QGroupBox("AWS prices (USD)")
        self.prices_widget.setLayout(QVBoxLayout())
        self.prices_label = QLabel()
        self.prices_widget.layout().addWidget(self.prices_label)
        self.layout().addWidget(self.prices_widget)

        self.cost_note_label = QLabel(cost_note)
        self.cost_note_label.setWordWrap(True)
        self.layout().addWidget(self.cost_note_label)

        # totals
        self.transfer_records: Dict[BackupTypes, List[TransferRecord]] = {backup_type: [] for backup_type in BackupTypes}
        self.totals_widget = QGroupBox("Totals")
        self.totals_widget.setLayout(QVBoxLayout())
        self.total_labels = {}
        for backup_type in BackupTypes:
            self.total_labels[backup_type] = QLabel()
            self.totals_widget.layout().addWidget(self.total_labels[backup_type])
        self.grand_total_label = QLabel()  # all the backup types together, in bold
        grand_total_font = self.grand_total_label.font()
        grand_total_font.setBold(True)
        self.grand_total_label.setFont(grand_total_font)
        self.totals_widget.layout().addWidget(self.grand_total_label)
        self.layout().addWidget(self.totals_widget)

        # one row per transfer, highest cost first
        self.row_records: List[TransferRecord] = []  # the transfer record of each table row, in row order
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.controls_widget = make_row(self.clear_button)
        self.layout().addWidget(self.controls_widget)
        # every column is as wide as its contents, and an empty spacer column on the far right takes up the remaining width
        self.table = QTableWidget(0, len(columns) + 1)
        self.table.setHorizontalHeaderLabels(columns + [""])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout().addWidget(self.table)

        self.update_prices()
        self.update_totals()
        transfer_emitter.transfer_signal.connect(self.add_transfer_record)

    def add_transfer_record(self, transfer_record: TransferRecord):
        """
        Add a transfer that a backup reported to the table and the totals. Connected to the transfer signal, so it runs in the GUI thread.
        """
        backup_type = transfer_record.backup_type
        if backup_type is None:
            raise ValueError(f'"{transfer_record.name}" has no backup type: it is a total, not the transfer of a backup')
        self.transfer_records[backup_type].append(transfer_record)
        row_text = [
            get_local_time_string("seconds"),
            backup_type.name,
            transfer_record.name,
            transfer_record.region or "",
            format_size(transfer_record.received_bytes),
            str(transfer_record.requests) if transfer_record.requests > 0 else "",
            f"{transfer_record.read_units:g}" if transfer_record.read_units > 0.0 else "",
            format_cost(transfer_record.cost) if transfer_record.cost is not None else "",
        ]
        # keep the rows sorted by cost, highest at the top: the new row goes above the first row that doesn't rank higher than it
        # (so of two equal rows the more recent is on top)
        new_row_rank = get_cost_rank(transfer_record)
        row = next((row for row, row_record in enumerate(self.row_records) if get_cost_rank(row_record) <= new_row_rank), len(self.row_records))
        self.row_records.insert(row, transfer_record)
        self.table.insertRow(row)
        for column, text in enumerate(row_text):
            self.table.setItem(row, column, QTableWidgetItem(text))
        if self.table.rowCount() > max_transfer_rows:
            # drop the bottom (lowest cost) row - the totals still include it
            self.row_records.pop()
            self.table.removeRow(self.table.rowCount() - 1)
        self.update_totals()
        self.update_prices()  # the backup that reported this may have just fetched prices

    def update_prices(self):
        """
        Show the AWS prices as they are now in the price cache.
        """
        self.prices_label.setText(get_prices_text())

    def update_totals(self):
        """
        Show the total of each backup type and the grand total.
        """
        for backup_type in BackupTypes:
            total = get_transfer_total(backup_type, self.transfer_records[backup_type])
            self.total_labels[backup_type].setText(f"{backup_type.name} {total}")
        all_transfer_records = [transfer_record for backup_type in BackupTypes for transfer_record in self.transfer_records[backup_type]]
        self.grand_total_label.setText(str(get_transfer_total(None, all_transfer_records, "Grand total")))

    def clear(self):
        """
        Empty the table and start the totals again from zero.
        """
        for backup_type in BackupTypes:
            self.transfer_records[backup_type] = []
        self.row_records = []
        self.table.setRowCount(0)
        self.update_totals()
