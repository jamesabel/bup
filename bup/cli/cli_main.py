from balsa import Balsa, get_logger

from bup import __application_name__, __author__, __version__, S3Backup, DynamoDBBackup, GithubBackup, get_preferences, UITypes, ExclusionPreferences, BackupTypes

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

    try:
        preferences = get_preferences(ui_type)
        preferences.backup_directory = args.path  # backup classes will read the preferences DB directly
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

        did_something = False
        dynamodb_local_backup = None
        s3_local_backup = None
        github_local_backup = None
        if args.s3 or args.aws:
            s3_local_backup = S3Backup(ui_type, _console_info, _console_warning, _console_error)
            s3_local_backup.start()
            did_something = True
        if args.dynamodb or args.aws:
            dynamodb_local_backup = DynamoDBBackup(ui_type, _console_info, _console_warning, _console_error)
            dynamodb_local_backup.start()
            did_something = True
        if args.github:
            github_local_backup = GithubBackup(ui_type, _console_info, _console_warning, _console_error)
            github_local_backup.start()
            did_something = True
        if not did_something:
            print("nothing to do - please specify a backup to do or -h/--help for help")

        # QThread uses wait(), not join()
        if dynamodb_local_backup is not None:
            dynamodb_local_backup.wait()
        if s3_local_backup is not None:
            s3_local_backup.wait()
        if github_local_backup is not None:
            github_local_backup.wait()
    except Exception as e:
        log.exception(e)
