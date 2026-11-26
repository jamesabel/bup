"""
The command line interface of bup: runs the backups asked for on the command line and prints their output.
"""

import sys
from typing import List

from balsa import Balsa, get_logger

from bup import __application_name__, __author__, __version__, S3Backup, DynamoDBBackup, GithubBackup, get_preferences, UITypes, ExclusionPreferences, BackupTypes
from bup.log_routing import set_detailed_file_logging

log = get_logger(__application_name__)


def _console_info(s: str):
    """
    Print a line of regular output of a backup.
    """
    print(s)


def _console_warning(s: str):
    """
    Print a warning of a backup.
    """
    print(f"WARNING: {s}")


def _console_error(s: str):
    """
    Print an error of a backup.
    """
    print(f"ERROR: {s}")


def get_selected_backup_types(args) -> List[BackupTypes]:
    """
    :param args: the parsed command line (see arguments())
    :return: the backup types the command line asks for, in the order of BackupTypes (--aws is both S3 and DynamoDB)
    """
    selected = {BackupTypes.S3: args.s3 or args.aws, BackupTypes.DynamoDB: args.dynamodb or args.aws, BackupTypes.github: args.github}
    return [backup_type for backup_type in BackupTypes if selected[backup_type]]


def cli_main(args):
    """
    Run the backups the command line asks for, all at the same time, and wait for them. The command line's options are written to
    the CLI's preferences, which is where the backups read them. Exits with status 1 if a backup reported an error.

    :param args: the parsed command line (see arguments())
    """

    ui_type = UITypes.cli

    balsa = Balsa(__application_name__, __author__)
    balsa.log_console_prefix = "\r"
    balsa.init_logger_from_args(args)
    log.info(f"__application_name__={__application_name__}")
    log.info(f"__author__={__author__}")
    log.info(f"__version__={__version__}")

    preferences = get_preferences(ui_type)
    preferences.backup_directory = args.path  # backup classes will read the preferences DB directly
    set_detailed_file_logging(preferences.detailed_log_directory, preferences.detailed_log_file_size_limit_mb)  # one detailed log file per backup type, if configured
    # only overwrite saved values when explicitly given on the command line
    if args.token is not None:
        preferences.github_token = args.token
    if args.profile is not None:
        preferences.aws_profile = args.profile
    if args.region is not None:
        preferences.aws_region = args.region
    preferences.dry_run = args.dry_run
    preferences.s3_size_only = args.size_only
    preferences.s3_verify = args.verify
    preferences.s3_fix_mtime = args.fix_mtime

    backup_types = get_selected_backup_types(args)

    # Set the exclusions for the selected backup type(s).  The values are stored for subsequent runs.
    # An explicitly empty -e (no values) clears the stored exclusions.
    if args.exclude is not None:
        for backup_type in backup_types:
            ExclusionPreferences(backup_type.name).set(args.exclude)

    backup_classes = {BackupTypes.S3: S3Backup, BackupTypes.DynamoDB: DynamoDBBackup, BackupTypes.github: GithubBackup}
    backups = [backup_classes[backup_type](ui_type, _console_info, _console_warning, _console_error) for backup_type in backup_types]

    if len(backups) == 0:
        print("nothing to do - please specify a backup to do or -h/--help for help")
        return

    for backup in backups:
        backup.start()
    for backup in backups:
        backup.wait()  # QThread uses wait(), not join()

    # so schedulers (e.g. Task Scheduler, cron) can detect a failed or partial backup
    total_error_count = sum(backup.error_count for backup in backups)
    if total_error_count > 0:
        log.error(f"{total_error_count} errors during backup")
        sys.exit(1)
