"""
Make the README's screen captures (doc/screenshots/*.png) of the bup GUI showing synthetic data.

Run from the project root with the project's virtual environment:  venv\\Scripts\\python.exe tools\\make_screenshots.py

Nothing here reads or writes the real preferences, exclusions or AWS price cache, contacts AWS or GitHub, or runs a backup:
the GUI is given stand-ins for all of them, and every name, size and price shown is made up.
"""

import sys
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from PyQt5.QtWidgets import QApplication

import bup
from bup import BackupTypes, aws_prices
from bup.aws_prices import AWSPrices, AWSPriceCache
from bup.transfer import TransferRecord, transfer_emitter, get_transfer_out_cost, get_dynamodb_scan_cost

screenshot_width = 1500
screenshot_height = 820
pane_heights = [110, 380, 150, 90]  # of each backup type's exclusions, log, warnings and errors panes (pixels)


class SyntheticPreferences:
    """
    Stand-in for the preferences database: made up values, kept only in memory.
    """

    backup_directory = "D:\\backup"
    aws_profile = "example"
    aws_region = "us-east-1"
    github_token = "synthetic-token-not-real"
    automatic_backup = True
    backup_period = 24  # hours
    dry_run = False
    s3_size_only = False
    s3_verify = False
    verbose = False

    def __getattr__(self, name: str):
        return None  # everything else (e.g. saved window and pane sizes) is not set


class SyntheticExclusions:
    """
    Stand-in for the exclusion lists of each backup type.
    """

    exclusions = {
        BackupTypes.S3.name: ["# buckets to skip", "example-scratch  # temporary files"],
        BackupTypes.DynamoDB.name: ["sessions  # short-lived"],
        BackupTypes.github.name: ["example-org/archived-experiment"],
    }

    def __init__(self, exclusion_type: str):
        self.exclusion_type = exclusion_type

    def get(self) -> list:
        return self.exclusions[self.exclusion_type]

    def set(self, exclusions: list):
        pass


synthetic_log = {
    BackupTypes.S3: [
        "found 4 buckets",
        "example-photos",
        "example-website-assets",
        "example-invoices",
        "excluding example-scratch",
        "4 buckets, 3 backed up, 128 files synced, 1 excluded",
    ],
    BackupTypes.DynamoDB: ["found 3 DynamoDB tables", "customers", "orders", "excluding sessions", "3 tables, 2 backed up, 1 excluded"],
    BackupTypes.github: [
        'git fetch "example-org/website"',
        'git reset "example-org/website" branch:"main"',
        'git fetch "example-org/billing-service"',
        'git reset "example-org/billing-service" branch:"main"',
        'git clone "example-org/mobile-app"',
        "example-org/archived-experiment excluded",
        "4 repos, 2 pulls, 1 clones, 1 excluded",
    ],
}

synthetic_warnings = {
    BackupTypes.S3: ['example-photos : S3 object "2024/IMG_0042.JPG" has no local file at exactly that path : local name "img_0042.jpg" differs from S3 key "IMG_0042.JPG" only in case'],
}

synthetic_prices = [AWSPrices("us-east-1", 0.09, 0.125, time.time()), AWSPrices("eu-west-1", 0.09, 0.1415, time.time())]


def make_synthetic_transfer_records() -> list:
    prices = {region_prices.region: region_prices for region_prices in synthetic_prices}
    transfer_records = []
    for bucket_name, region, received_bytes in (
        ("example-photos", "us-east-1", 3 * 1024**3),
        ("example-website-assets", "eu-west-1", 42 * 1024**2),
        ("example-invoices", "us-east-1", 6 * 1024**2),
    ):
        transfer_records.append(TransferRecord(BackupTypes.S3, bucket_name, received_bytes, cost=get_transfer_out_cost(received_bytes, prices[region]), region=region))
    for table_name, received_bytes, read_units in (("customers", 12 * 1024**2, 1500.0), ("orders", 180 * 1024**2, 22500.0)):
        cost = get_dynamodb_scan_cost(received_bytes, read_units, prices["us-east-1"])
        transfer_records.append(TransferRecord(BackupTypes.DynamoDB, table_name, received_bytes, read_units, cost, "us-east-1"))
    for repo_name, received_bytes in (("example-org/website", 350 * 1024), ("example-org/mobile-app", 28 * 1024**2)):
        transfer_records.append(TransferRecord(BackupTypes.github, repo_name, received_bytes))
    return transfer_records


def main():
    output_directory = Path(project_root, "doc", "screenshots")
    output_directory.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)

    # Give the GUI its stand-ins before the GUI modules are imported (they bind these names at import).
    synthetic_preferences = SyntheticPreferences()
    bup.get_preferences = lambda ui_type: synthetic_preferences
    bup.ExclusionPreferences = SyntheticExclusions
    with tempfile.TemporaryDirectory() as price_cache_directory:
        price_cache_path = Path(price_cache_directory, "aws_prices.db")
        aws_prices.get_aws_price_cache_path = lambda: price_cache_path
        for region_prices in synthetic_prices:
            AWSPriceCache(price_cache_path).put(region_prices)

        from bup.gui import BupDialog, RunBackupWidget
        from bup.gui.run_backup_widget import DisplayTypes

        RunBackupWidget.start = lambda self: False  # never run a backup

        dialog = BupDialog()
        dialog.autobackup_timer.stop()  # the timer would otherwise try to start an automatic backup
        dialog.resize(screenshot_width, screenshot_height)

        for backup_type, backup_widget in dialog.run_backup_widget.backup_status.items():
            for line in synthetic_log[backup_type]:
                backup_widget.display_boxes[DisplayTypes.log].append_text(line)
            for line in synthetic_warnings.get(backup_type, []):
                backup_widget.display_boxes[DisplayTypes.warnings].append_text(line)
        dialog.run_backup_widget.countdown_text.setText("(in 23:14:07)")
        for transfer_record in make_synthetic_transfer_records():
            transfer_emitter.transfer_signal.emit(transfer_record)

        dialog.show()
        app.processEvents()
        for backup_widget in dialog.run_backup_widget.backup_status.values():
            backup_widget.splitter.setSizes(pane_heights)
            for display_box in backup_widget.display_boxes.values():
                display_box.text_box.verticalScrollBar().setValue(0)  # most recent lines are at the top
        for tab_widget, file_name in ((dialog.run_backup_widget, "backup.png"), (dialog.transfer_widget, "transfer.png"), (dialog.preferences_widget, "preferences.png")):
            dialog.tab_widget.setCurrentWidget(tab_widget)
            app.processEvents()
            screenshot_path = Path(output_directory, file_name)
            if not dialog.grab().save(str(screenshot_path)):
                raise OSError(f'could not write "{screenshot_path}"')
            print(screenshot_path)
        dialog.log_widget.detach()


if __name__ == "__main__":
    main()
