import argparse

from balsa import Balsa, get_logger

from bup import __application_name__, __author__, __version__, __description__, s3_local_backup, dynamodb_local_backup, github_local_backup

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
    parser.add_argument("--github_subdir", default="github", help="github subdir (can be used to shorten the overall path)")
    parser.add_argument("-e", "--exclude", nargs="*", help="exclude these AWS S3 buckets and/or tables")
    parser.add_argument("-x", "--exclude_file", help="exclude the AWS S3 buckets and/or tables listed in this file")
    parser.add_argument("-p", "--profile", help="AWS profile (uses the default AWS profile if not given)")
    parser.add_argument("-t", "--token", help="github token (only need to enter once - it will be stored for you)")
    parser.add_argument("--dry_run", action="store_true", default=False, help="Displays operations that would be performed using the specified command without actually running them")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="set verbose")
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
    if args.s3 or args.aws:
        s3_local_backup(args.path, args.profile, args.dry_run, exclusion_list)
        did_something = True
    if args.dynamodb or args.aws:
        dynamodb_local_backup(args.path, args.profile, args.dry_run, exclusion_list)
        did_something = True
    if args.github:
        github_local_backup(args.path, args.github_subdir)
        did_something = True
    if not did_something:
        print("nothing to do - please specify a backup to do or -h/--help for help")
