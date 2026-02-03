from balsa import Balsa, get_logger

from bup import __application_name__, __author__, __version__, S3Backup, DynamoDBBackup, GithubBackup, get_preferences, UITypes, ExclusionPreferences, BackupTypes

log = get_logger(__application_name__)


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
        preferences.github_token = args.token
        preferences.aws_profile = args.profile

        # If setting the exclusions, just do it for one backup type at a time.  The values are stored for subsequent runs.
        if args.exclude is not None and len(args.exclude) > 0:
            if args.s3:
                ExclusionPreferences(BackupTypes.S3.name).set(args.exclude)
            elif args.dynamodb:
                ExclusionPreferences(BackupTypes.DynamoDB.name).set(args.exclude)
            elif args.github:
                ExclusionPreferences(BackupTypes.github.name).set(args.exclude)

        did_something = False
        dynamodb_local_backup = None
        s3_local_backup = None
        github_local_backup = None
        if args.s3:
            s3_local_backup = S3Backup(ui_type, log.info, log.warning, log.error)
            s3_local_backup.start()
            did_something = True
        if args.dynamodb:
            dynamodb_local_backup = DynamoDBBackup(ui_type, log.info, log.warning, log.error)
            dynamodb_local_backup.start()
            did_something = True
        if args.github:
            github_local_backup = GithubBackup(ui_type, log.info, log.warning, log.error)
            github_local_backup.start()
            did_something = True
        if not did_something:
            print("nothing to do - please specify a backup to do or -h/--help for help")

        if dynamodb_local_backup is not None:
            dynamodb_local_backup.join()
        if s3_local_backup is not None:
            s3_local_backup.join()
        if github_local_backup is not None:
            github_local_backup.join()
    except Exception as e:
        log.exception(e)
