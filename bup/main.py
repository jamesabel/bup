import argparse

from balsa import Balsa, get_logger, verbose_arg_string, log_dir_arg_string, delete_existing_arg_string

from bup import __application_name__, __author__, __version__, __description__, S3Backup, DynamoDBBackup, GitBackup

log = get_logger(__application_name__)


def main():

    parser = argparse.ArgumentParser(
        prog=__application_name__,
        description=__description__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f"v{__version__}, www.abel.co, see github.com/jamesabel/bup for LICENSE.",
    )
    parser.add_argument("path", help="directory to back up to")
    parser.add_argument("-a", "--aws", action="store_true", default=False, help="backup AWS S3 and DynamoDB")
    parser.add_argument("-s", "--s3", action="store_true", default=False, help="backup AWS S3")
    parser.add_argument("-d", "--dynamodb", action="store_true", default=False, help="backup AWS DynamoDB")
    parser.add_argument("-g", "--github", action="store_true", default=False, help="backup github")
    parser.add_argument("-e", "--exclude", nargs="*", help="exclude these AWS S3 buckets and/or tables")
    parser.add_argument("-x", "--exclude_file", help="exclude the AWS S3 buckets and/or tables listed in this file")
    parser.add_argument("-p", "--profile", help="AWS profile (uses the default AWS profile if not given)")
    parser.add_argument("-t", "--token", help="github token (only need to enter once - it will be stored for you)")
    parser.add_argument("--dry_run", action="store_true", default=False, help="Displays operations that would be performed using the specified command without actually running them")
    parser.add_argument("-v", f"--{verbose_arg_string}", dest=verbose_arg_string, action="store_true", default=False, help="set verbose")
    parser.add_argument("-l", f"--{log_dir_arg_string}", dest=log_dir_arg_string, help="log dir")
    parser.add_argument(f"--{delete_existing_arg_string}", dest=delete_existing_arg_string, help="delete existing logs")
    args = parser.parse_args()

    balsa = Balsa(__application_name__, __author__)
    if args.verbose:
        balsa.verbose = args.verbose
    balsa.log_directory = args.path
    balsa.log_console_prefix = "\r"
    balsa.init_logger()
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
