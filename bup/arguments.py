import argparse
from pathlib import Path
import sys

from balsa import verbose_arg_string, log_dir_arg_string, delete_existing_arg_string

from bup import __application_name__, __version__, __description__


def arguments():

    version_string = "version"

    if len(sys.argv) > 1 and sys.argv[1].lower() == f"--{version_string}":
        print(__version__)
        sys.exit()

    if len(sys.argv) > 1:

        parser = argparse.ArgumentParser(
            prog=__application_name__,
            description=__description__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            epilog=f"{__application_name__} V{__version__}, see github.com/jamesabel/bup for LICENSE",
        )
        parser.add_argument("path", help="directory to back up to")
        parser.add_argument("-s", "--s3", action="store_true", default=False, help="backup AWS S3")
        parser.add_argument("-d", "--dynamodb", action="store_true", default=False, help="backup AWS DynamoDB")
        parser.add_argument("-g", "--github", action="store_true", default=False, help="backup github")
        parser.add_argument(
            "-e",
            "--exclude",
            nargs="*",
            help="exclude these AWS S3 buckets and/or tables (only do one backup type at a time when setting exclusions - these values are saved and used on subsequent runs)",
        )
        parser.add_argument("-p", "--profile", help="AWS profile (uses the default AWS profile if not given)")
        parser.add_argument("-r", "--region", help="AWS region (uses the default AWS region if not given)")
        parser.add_argument("-t", "--token", help="github token (saved and used on subsequent runs)")
        parser.add_argument("--dry_run", action="store_true", default=False, help="displays operations that would be performed using the specified command without actually running them")
        parser.add_argument(f"--{version_string}", action="store_true", default=False, help="display version and exit")
        parser.add_argument("-v", f"--{verbose_arg_string}", dest=verbose_arg_string, action="store_true", default=False, help="set verbose")
        parser.add_argument("-l", f"--{log_dir_arg_string}", dest=log_dir_arg_string, help="log dir")
        parser.add_argument(f"--{delete_existing_arg_string}", dest=delete_existing_arg_string, help="delete existing logs")
        args = parser.parse_args()

        if args.logdir is None and args.path is not None:
            # put the logs in the backup dir unless explicitly given
            args.logdir = Path(args.path, "log")
    else:
        args = None

    return args
