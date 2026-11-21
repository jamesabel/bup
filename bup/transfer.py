"""
Network transfer accounting for backups: how much each backup received from AWS (and GitHub), and approximately what AWS charges for it.

The costs are estimates. They use list prices that vary by region and change over time (editable in the GUI's Transfer tab), they do not
know how much of the AWS free data transfer allowance (100 GB a month, shared by the whole AWS account) is left, and they do not include
request charges (e.g. S3 GET and LIST).
"""

from dataclasses import dataclass
from typing import Iterable, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from bup.backup_types import BackupTypes

bytes_per_gb = 1024**3  # AWS bills data transfer per GB of 2^30 bytes

# Default prices in USD (us-east-1 list prices when this was written - check https://aws.amazon.com/s3/pricing/ and
# https://aws.amazon.com/dynamodb/pricing/ for the current prices in your region).
default_aws_transfer_out_price_per_gb = 0.09  # data transfer out to the internet
default_dynamodb_read_price_per_million_units = 0.125  # on-demand read request units

read_units_per_million = 1000000

smallest_displayed_cost = 0.0001  # USD

size_units = ["B", "KB", "MB", "GB", "TB"]


def get_price(preference_value, default_price: float) -> float:
    """
    A price from a preference, which is None until the user sets it.
    """
    return default_price if preference_value is None else float(preference_value)


def get_transfer_out_cost(byte_count: int, price_per_gb: float) -> float:
    return byte_count / bytes_per_gb * price_per_gb


def get_dynamodb_read_cost(read_units: float, price_per_million_units: float) -> float:
    return read_units / read_units_per_million * price_per_million_units


def format_size(byte_count: int) -> str:
    """
    Human-readable size in the 1024-based units AWS bills in, e.g. 1536 -> "1.5 KB".
    """
    size = float(byte_count)
    unit_index = 0
    while size >= 1024.0 and unit_index < len(size_units) - 1:
        size /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{byte_count} {size_units[0]}"
    return f"{size:.1f} {size_units[unit_index]}"


def format_cost(cost: float) -> str:
    """
    Cost in USD. Backups usually cost a fraction of a cent, so small costs get more decimal places.
    """
    if 0.0 < cost < smallest_displayed_cost:
        return f"less than ${smallest_displayed_cost:.4f}"
    return f"${cost:.2f}" if cost >= 1.0 else f"${cost:.4f}"


@dataclass(frozen=True)
class TransferRecord:
    """
    What one backed up item (an S3 bucket, a DynamoDB table or a GitHub repo) received over the network.
    """

    backup_type: BackupTypes
    name: str
    received_bytes: int
    read_units: float = 0.0  # DynamoDB read request units consumed (DynamoDB only)
    cost: Optional[float] = None  # approximate USD, None where there is no charge to estimate (GitHub)

    def __str__(self):
        s = f"{self.name} : received {format_size(self.received_bytes)}"
        if self.read_units > 0.0:
            s += f", {self.read_units:g} read units"
        if self.cost is not None:
            s += f", approximately {format_cost(self.cost)} before any AWS free allowance"
        return s


def get_transfer_total(backup_type: BackupTypes, transfer_records: Iterable[TransferRecord]) -> TransferRecord:
    """
    The sum of a backup type's transfer records, as a record named "transfer total".
    """
    transfer_records = list(transfer_records)
    costs = [transfer_record.cost for transfer_record in transfer_records if transfer_record.cost is not None]
    return TransferRecord(
        backup_type,
        "transfer total",
        sum(transfer_record.received_bytes for transfer_record in transfer_records),
        sum(transfer_record.read_units for transfer_record in transfer_records),
        sum(costs) if costs else None,
    )


class TransferEmitter(QObject):
    transfer_signal = pyqtSignal(object)  # a TransferRecord


# Backups report their transfer records here, and the GUI's Transfer tab listens. Backups run in worker QThreads and Qt widgets may only
# be touched from the GUI thread - the signal connection handles the thread hop. With no listener (e.g. the CLI) an emit does nothing.
transfer_emitter = TransferEmitter()
