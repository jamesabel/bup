"""
Make the README's screen captures (doc/screenshots/*.png) of the bup GUI showing synthetic data.

Run from the project root with the project's virtual environment:  .venv\\Scripts\\python.exe tools\\make_screenshots.py

Nothing here reads or writes the real preferences, exclusions, AWS price cache or backup history, contacts AWS or GitHub, or runs a backup:
the GUI is given stand-ins for all of them, and every name, size and price shown is made up.
"""

import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from awsimple import S3RequestTier
from PyQt5.QtWidgets import QApplication

import bup
from bup import BackupTypes, UITypes, aws_prices, backup_history
from bup.aws_prices import AWSPrices, AWSPriceCache
from bup.backup_history import BackupCounts, BackupHistory, BackupStatus
from bup.transfer import TransferRecord, transfer_emitter, get_charged_request_count, get_dynamodb_scan_cost, get_s3_cost, get_transfer_total

screenshot_width = 1500
screenshot_height = 820
history_screenshot_width = 2000  # the History tab has many columns, and is captured wide enough to show them all
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
    s3_fix_mtime = False
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
    BackupTypes.S3: ['example-photos : S3 object "archive/2019.zip" not backed up : storage class GLACIER has to be restored before it can be read'],
}

synthetic_s3_tier2_request_prices = {
    "STANDARD": 0.0004,
    "STANDARD_IA": 0.001,
    "ONEZONE_IA": 0.001,
    "INTELLIGENT_TIERING": 0.0004,
    "GLACIER_IR": 0.01,
    "GLACIER": 0.0004,
    "DEEP_ARCHIVE": 0.0004,
}
synthetic_s3_retrieval_prices = {"STANDARD_IA": 0.01, "ONEZONE_IA": 0.01, "GLACIER_IR": 0.03}
synthetic_prices = [
    AWSPrices("us-east-1", 0.09, 0.125, time.time(), 0.005, synthetic_s3_tier2_request_prices, synthetic_s3_retrieval_prices),
    AWSPrices("eu-west-1", 0.09, 0.1415, time.time(), 0.005, synthetic_s3_tier2_request_prices, synthetic_s3_retrieval_prices),
]


def make_synthetic_transfer_records() -> list:
    prices = {region_prices.region: region_prices for region_prices in synthetic_prices}
    transfer_records = []
    # each bucket: what its sync received and the requests it made, then the requests of its verification (one for each object)
    for bucket_name, region, received_bytes, storage_class, sync_request_count, object_count in (
        ("example-photos", "us-east-1", 3 * 1024**3, "GLACIER_IR", 1260, 48200),
        ("example-website-assets", "eu-west-1", 42 * 1024**2, "STANDARD", 96, 3150),
        ("example-invoices", "us-east-1", 6 * 1024**2, "STANDARD_IA", 31, 870),
    ):
        sync_tier_counts = {(S3RequestTier.tier1, "STANDARD"): 2 + object_count // 1000, (S3RequestTier.tier2, storage_class): sync_request_count}
        verify_tier_counts = {(S3RequestTier.tier2, storage_class): object_count}
        for name, size, tier_counts in ((bucket_name, received_bytes, sync_tier_counts), (f"{bucket_name} (verification)", 0, verify_tier_counts)):
            cost = get_s3_cost(size, tier_counts, {storage_class: size}, prices[region])  # the objects that were downloaded have the retrieval fee of their storage class
            transfer_records.append(TransferRecord(BackupTypes.S3, name, size, cost=cost, region=region, requests=get_charged_request_count(tier_counts)))
    for table_name, received_bytes, read_units in (("customers", 12 * 1024**2, 1500.0), ("orders", 180 * 1024**2, 22500.0)):
        cost = get_dynamodb_scan_cost(received_bytes, read_units, prices["us-east-1"])
        transfer_records.append(TransferRecord(BackupTypes.DynamoDB, table_name, received_bytes, read_units, cost, "us-east-1"))
    for repo_name, received_bytes in (("example-org/website", 350 * 1024), ("example-org/mobile-app", 28 * 1024**2)):
        transfer_records.append(TransferRecord(BackupTypes.github, repo_name, received_bytes))
    return transfer_records


seconds_per_day = 24 * 60 * 60

# how long each backup type's run took in the synthetic history (seconds)
synthetic_durations = {BackupTypes.S3: 1325.0, BackupTypes.DynamoDB: 212.0, BackupTypes.github: 96.0}

# what each backup type finds (buckets, tables, repositories), how many of them are excluded, and the files of its backup
synthetic_counts = {BackupTypes.S3: (14, 2, 218734), BackupTypes.DynamoDB: (9, 1, 0), BackupTypes.github: (37, 3, 0)}


def get_synthetic_counts(backup_type: BackupTypes, days_ago: float, files_synced: int = 0, failed: int = 0) -> BackupCounts:
    """
    Made up counts of a run: what there is to back up grows a little from day to day.

    :param backup_type: the type of the backup
    :param days_ago: how long ago the run was
    :param files_synced: the files an S3 run downloaded
    :param failed: how many of what it found it could not back up
    :return: the counts of the run
    """
    found, excluded, files = synthetic_counts[backup_type]
    is_s3 = backup_type is BackupTypes.S3
    return BackupCounts(found, found - excluded - failed, excluded, round(files - 310 * days_ago) if is_s3 else None, files_synced if is_s3 else None)


def make_synthetic_history(history: BackupHistory, transfer_records: list):
    """
    Fill the backup history with a few days of made up runs: the most recent one received the synthetic transfers, one had an
    error, one was cut short and one was a run from the command line.
    """
    no_transfer = TransferRecord(None, "transfer total", 0)
    # the runs start at 02:10 (the most recent one today, or yesterday if that is still to come), so that none of them goes past midnight
    today_start = datetime.now().replace(hour=2, minute=10, second=7, microsecond=0).timestamp()
    most_recent_start = today_start if today_start + max(synthetic_durations.values()) < time.time() else today_start - seconds_per_day
    for days_ago in range(5, -1, -1):
        started = most_recent_start - days_ago * seconds_per_day
        for backup_type in BackupTypes:
            run_id = history.start(backup_type, UITypes.gui, started)
            ended = started + synthetic_durations[backup_type]
            if days_ago == 0:
                transfer_total = get_transfer_total(backup_type, [transfer_record for transfer_record in transfer_records if transfer_record.backup_type is backup_type])
                counts = get_synthetic_counts(backup_type, days_ago, files_synced=1284)
                history.update(run_id, BackupStatus.completed, transfer_total, 0, len(synthetic_warnings.get(backup_type, [])), [], ended, counts)
            elif days_ago == 2:
                # the system went down during this run
                history.update(run_id, BackupStatus.interrupted, no_transfer, 0, 0, [])
            elif days_ago == 4 and backup_type is BackupTypes.github:
                errors = ['could not fetch "example-org/billing-service" : could not resolve host github.com']
                counts = get_synthetic_counts(backup_type, days_ago, failed=1)
                history.update(run_id, BackupStatus.completed_with_errors, TransferRecord(backup_type, "transfer total", 350 * 1024), len(errors), 0, errors, ended, counts)
            else:
                history.update(run_id, BackupStatus.completed, no_transfer, 0, 0, [], ended, get_synthetic_counts(backup_type, days_ago))
    started = most_recent_start - 3.5 * seconds_per_day
    run_id = history.start(BackupTypes.S3, UITypes.cli, started)
    counts = get_synthetic_counts(BackupTypes.S3, 3.5, files_synced=42)
    history.update(run_id, BackupStatus.completed, TransferRecord(BackupTypes.S3, "transfer total", 6 * 1024**2, cost=0.0005), 0, 0, [], started + 61.0, counts)


def main():
    output_directory = Path(project_root, "doc", "screenshots")
    output_directory.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)

    # Give the GUI its stand-ins before the GUI modules are imported (they bind these names at import).
    synthetic_preferences = SyntheticPreferences()
    bup.get_preferences = lambda ui_type: synthetic_preferences
    bup.ExclusionPreferences = SyntheticExclusions
    with tempfile.TemporaryDirectory() as data_directory:
        price_cache_path = Path(data_directory, "aws_prices.db")
        aws_prices.get_aws_price_cache_path = lambda: price_cache_path
        for region_prices in synthetic_prices:
            AWSPriceCache(price_cache_path).put(region_prices)
        backup_history_path = Path(data_directory, "backup_history.db")
        backup_history.get_backup_history_path = lambda: backup_history_path
        transfer_records = make_synthetic_transfer_records()
        make_synthetic_history(BackupHistory(backup_history_path), transfer_records)

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
        for transfer_record in transfer_records:
            transfer_emitter.transfer_signal.emit(transfer_record)

        dialog.show()
        app.processEvents()
        for backup_widget in dialog.run_backup_widget.backup_status.values():
            backup_widget.splitter.setSizes(pane_heights)
            for display_box in backup_widget.display_boxes.values():
                display_box.text_box.verticalScrollBar().setValue(0)  # most recent lines are at the top
        for tab_widget, file_name, width in (
            (dialog.run_backup_widget, "backup.png", screenshot_width),
            (dialog.transfer_widget, "transfer.png", screenshot_width),
            (dialog.preferences_widget, "preferences.png", screenshot_width),
            (dialog.history_widget, "history.png", history_screenshot_width),
        ):
            dialog.resize(width, screenshot_height)
            dialog.tab_widget.setCurrentWidget(tab_widget)
            app.processEvents()
            screenshot_path = Path(output_directory, file_name)
            if not dialog.grab().save(str(screenshot_path)):
                raise OSError(f'could not write "{screenshot_path}"')
            print(screenshot_path)
        dialog.log_widget.detach()


if __name__ == "__main__":
    main()
