import sqlite3
from datetime import datetime
from typing import Dict, List

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from balsa import get_logger

from bup import BackupTypes, __application_name__
from bup.aws_prices import get_cached_aws_prices
from bup.transfer import TransferRecord, transfer_emitter, get_transfer_total, format_size, format_cost

log = get_logger(__application_name__)

max_transfer_rows = 1000

columns = ["Time", "Backup", "Name", "Region", "Received", "Read units", "Approximate cost"]

no_prices_text = "No AWS prices yet. bup gets them from AWS the first time a backup receives data from S3 or DynamoDB."

cost_note = (
    "Costs are approximate. bup gets the prices of each AWS region from AWS and refreshes them periodically. Costs are before the AWS "
    "free data transfer allowance (100 GB a month, shared by the whole AWS account), do not include request charges, and count DynamoDB "
    "reads as on-demand. GitHub does not charge for transfer, so its sizes are informational."
)


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
        f"{aws_prices.region} : ${aws_prices.transfer_out_price_per_gb:g} per GB data transfer out, ${aws_prices.dynamodb_read_price_per_million_units:g} per million DynamoDB read units "
        f"(from AWS on {datetime.fromtimestamp(aws_prices.fetched).date().isoformat()})"
        for aws_prices in all_aws_prices
    )


class TransferWidget(QWidget):
    """
    "Transfer" tab - what each backup received over the network and approximately what AWS charges for it, one row per S3 bucket,
    DynamoDB table or GitHub repo that received anything, with totals per backup type since bup was started (or the tab was cleared).
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
        self.layout().addWidget(self.totals_widget)

        # one row per transfer, most recent first
        self.controls_widget = QWidget()
        self.controls_widget.setLayout(QHBoxLayout())
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.controls_widget.layout().addWidget(self.clear_button)
        self.controls_widget.layout().addStretch()
        self.layout().addWidget(self.controls_widget)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout().addWidget(self.table)

        self.update_prices()
        self.update_totals()
        transfer_emitter.transfer_signal.connect(self.add_transfer_record)

    def add_transfer_record(self, transfer_record: TransferRecord):
        self.transfer_records[transfer_record.backup_type].append(transfer_record)
        row_text = [
            datetime.now().astimezone().isoformat(timespec="seconds"),
            transfer_record.backup_type.name,
            transfer_record.name,
            transfer_record.region or "",
            format_size(transfer_record.received_bytes),
            f"{transfer_record.read_units:g}" if transfer_record.read_units > 0.0 else "",
            format_cost(transfer_record.cost) if transfer_record.cost is not None else "",
        ]
        self.table.insertRow(0)
        for column, text in enumerate(row_text):
            self.table.setItem(0, column, QTableWidgetItem(text))
        if self.table.rowCount() > max_transfer_rows:
            self.table.removeRow(self.table.rowCount() - 1)  # FIFO - the totals still include the removed row
        self.update_totals()
        self.update_prices()  # the backup that reported this may have just fetched prices

    def update_prices(self):
        self.prices_label.setText(get_prices_text())

    def update_totals(self):
        for backup_type in BackupTypes:
            total = get_transfer_total(backup_type, self.transfer_records[backup_type])
            self.total_labels[backup_type].setText(f"{backup_type.name} {total}")

    def clear(self):
        for backup_type in BackupTypes:
            self.transfer_records[backup_type] = []
        self.table.setRowCount(0)
        self.update_totals()
