import sys

from balsa import Balsa, get_logger

from bup import __application_name__, __author__, __version__, S3Backup, DynamoDBBackup, GithubBackup, get_preferences, UITypes, ExclusionPreferences, BackupTypes
from bup.log_routing import set_detailed_file_logging

log = get_logger(__application_name__)


def _console_info(s: str):
    print(s)


def _console_warning(s: str):
    print(f"WARNING: {s}")


def _console_error(s: str):
    print(f"ERROR: {s}")


def cli_main(args):

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

    # Set the exclusions for the selected backup type(s).  The values are stored for subsequent runs.
    # An explicitly empty -e (no values) clears the stored exclusions.
    if args.exclude is not None:
        if args.s3 or args.aws:
            ExclusionPreferences(BackupTypes.S3.name).set(args.exclude)
        if args.dynamodb or args.aws:
            ExclusionPreferences(BackupTypes.DynamoDB.name).set(args.exclude)
        if args.github:
            ExclusionPreferences(BackupTypes.github.name).set(args.exclude)

    backups = []
    if args.s3 or args.aws:
        backups.append(S3Backup(ui_type, _console_info, _console_warning, _console_error))
    if args.dynamodb or args.aws:
        backups.append(DynamoDBBackup(ui_type, _console_info, _console_warning, _console_error))
    if args.github:
        backups.append(GithubBackup(ui_type, _console_info, _console_warning, _console_error))

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
