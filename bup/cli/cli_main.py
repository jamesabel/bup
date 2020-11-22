from balsa import Balsa, get_logger

from bup import __application_name__, __author__, __version__, arguments, S3Backup, DynamoDBBackup, GitBackup

log = get_logger(__application_name__)


def cli_main(args):

    balsa = Balsa(__application_name__, __author__)
    balsa.log_console_prefix = "\r"
    balsa.init_logger_from_args(args)
    log.info(f"__application_name__={__application_name__}")
    log.info(f"__author__={__author__}")
    log.info(f"__version__={__version__}")

    if args.exclude is None:
        exclusion_list = []
    else:
        exclusion_list = args.exclude.split()

    if args.exclude_file is not None:
        with open(args.exclude_file) as f:
            for file_line in f:
                if file_line is not None:
                    file_line = file_line.strip()
                    if len(file_line) > 0 and file_line[0] != "#":
                        exclusion_list.append(file_line)
    log.debug(f"exclusion_list={exclusion_list}")

    did_something = False
    dynamodb_local_backup = None
    s3_local_backup = None
    github_local_backup = None
    if args.s3 or args.aws:
        s3_local_backup = S3Backup(args.path, args.profile, args.dry_run, exclusion_list)
        s3_local_backup.start()
        did_something = True
    if args.dynamodb or args.aws:
        dynamodb_local_backup = DynamoDBBackup(args.path, args.profile, args.dry_run, exclusion_list)
        dynamodb_local_backup.start()
        did_something = True
    if args.github:
        github_local_backup = GitBackup(args.path, dry_run=args.dry_run)
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
