from datetime import datetime
from typing import Dict, List

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QDoubleSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView

from bup import BackupTypes
from bup.gui import get_gui_preferences
from bup.transfer import (
    TransferRecord,
    transfer_emitter,
    get_price,
    get_transfer_total,
    format_size,
    format_cost,
    default_aws_transfer_out_price_per_gb,
    default_dynamodb_read_price_per_million_units,
)

max_transfer_rows = 1000

columns = ["Time", "Backup", "Name", "Received", "Read units", "Approximate cost"]

cost_note = (
    "Costs are approximate. They use the prices above (which vary by AWS region), are before the AWS free data transfer allowance "
    "(100 GB a month, shared by the whole AWS account), do not include request charges, and count DynamoDB reads as on-demand. "
    "GitHub does not charge for transfer, so its sizes are informational."
)


def make_price_spin_box(price: float) -> QDoubleSpinBox:
    price_spin_box = QDoubleSpinBox()
    price_spin_box.setDecimals(4)
    price_spin_box.setRange(0.0, 1000.0)
    price_spin_box.setSingleStep(0.01)
    price_spin_box.setPrefix("$")
    price_spin_box.setValue(price)
    return price_spin_box


class TransferWidget(QWidget):
    """
    "Transfer" tab - what each backup received over the network and approximately what AWS charges for it, one row per S3 bucket,
    DynamoDB table or GitHub repo that received anything, with totals per backup type since bup was started (or the tab was cleared).
    """

    def __init__(self):
        super().__init__()
        self.setLayout(QVBoxLayout())

        # prices
        preferences = get_gui_preferences()
        self.prices_widget = QGroupBox("AWS prices (USD)")
        self.prices_widget.setLayout(QHBoxLayout())
        self.transfer_out_price = make_price_spin_box(get_price(preferences.aws_transfer_out_price_per_gb, default_aws_transfer_out_price_per_gb))
        self.transfer_out_price.valueChanged.connect(self.transfer_out_price_changed)  # connected after the value is loaded, so loading doesn't save
        self.prices_widget.layout().addWidget(QLabel("Data transfer out, per GB:"))
        self.prices_widget.layout().addWidget(self.transfer_out_price)
        self.dynamodb_read_price = make_price_spin_box(get_price(preferences.dynamodb_read_price_per_million_units, default_dynamodb_read_price_per_million_units))
        self.dynamodb_read_price.valueChanged.connect(self.dynamodb_read_price_changed)
        self.prices_widget.layout().addWidget(QLabel("DynamoDB reads, per million read units:"))
        self.prices_widget.layout().addWidget(self.dynamodb_read_price)
        self.prices_widget.layout().addStretch()
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

        self.update_totals()
        transfer_emitter.transfer_signal.connect(self.add_transfer_record)

    def transfer_out_price_changed(self):
        get_gui_preferences().aws_transfer_out_price_per_gb = self.transfer_out_price.value()

    def dynamodb_read_price_changed(self):
        get_gui_preferences().dynamodb_read_price_per_million_units = self.dynamodb_read_price.value()

    def add_transfer_record(self, transfer_record: TransferRecord):
        self.transfer_records[transfer_record.backup_type].append(transfer_record)
        row_text = [
            datetime.now().astimezone().isoformat(timespec="seconds"),
            transfer_record.backup_type.name,
            transfer_record.name,
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

    def update_totals(self):
        for backup_type in BackupTypes:
            total = get_transfer_total(backup_type, self.transfer_records[backup_type])
            self.total_labels[backup_type].setText(f"{backup_type.name} {total}")

    def clear(self):
        for backup_type in BackupTypes:
            self.transfer_records[backup_type] = []
        self.table.setRowCount(0)
        self.update_totals()
