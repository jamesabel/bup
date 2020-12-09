import subprocess
import os
import re
from pathlib import Path
from multiprocessing import freeze_support
from copy import deepcopy

from awsimple import S3Access
from balsa import get_logger

from bup import __application_name__, __version__, BupBase, BackupTypes, get_preferences, ExclusionPreferences

log = get_logger(__application_name__)

freeze_support()


# sundry candidate
def get_dir_size(dir_path: Path):
    dir_size = 0
    file_count = 0
    for dir_path, _, file_names in os.walk(dir_path):
        for file_name in file_names:
            file_count += 1
            dir_size += os.path.getsize(os.path.join(dir_path, file_name))
    return dir_size, file_count


class S3Backup(BupBase):

    backup_type = BackupTypes.S3

    def run(self):

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run

        backup_directory = os.path.join(preferences.backup_directory, "s3")

        os.makedirs(backup_directory, exist_ok=True)

        s3_access = S3Access(profile_name=preferences.aws_profile)

        decoding = "utf-8"

        # we delete all whitespace below
        ls_re = re.compile(r"TotalObjects:([0-9]+)TotalSize:([0-9]+)")

        buckets = s3_access.bucket_list()
        self.info_out(f"backing up {len(buckets)} buckets")

        count = 0
        exclusions = ExclusionPreferences(BackupTypes.S3.name).get()
        for bucket_name in buckets:

            # do the sync
            if bucket_name in exclusions:
                self.info_out(f"excluding {bucket_name}")
            else:
                if dry_run:
                    self.info_out(f"dry run {bucket_name}")
                else:
                    self.info_out(f"{bucket_name}")

                # try to find the AWS CLI app
                paths = [(Path("venv", "Scripts", "python.exe").absolute(), Path("venv", "Scripts", "aws").absolute()),  # local venv
                         (Path("python.exe").absolute(), Path("Scripts", "aws").absolute())  # installed app
                         ]
                aws_cli_path = None
                python_path = None
                for p, a in paths:
                    if p.exists() and a.exists():
                        aws_cli_path = a
                        python_path = p
                        break

                if aws_cli_path is None:
                    log.error(f"AWS CLI executable not found ({paths=})")
                elif python_path is None:
                    log.error(f"Python executable not found ({paths=})")
                else:
                    aws_cli_path = f'"{str(aws_cli_path)}"'  # from Path to str, with quotes for installed app
                    # AWS CLI app also needs the python executable to be in the path if it's not in the same dir, which happens when this program is installed.
                    # Make the directory of our python.exe the first in the list so it's found and not any of the others that may or may not be in the PATH.
                    env_var = deepcopy(os.environ)
                    env_var["path"] = f"{str(python_path.parent)};{env_var.get('path', '')}"

                    destination = Path(backup_directory, bucket_name)
                    os.makedirs(destination, exist_ok=True)
                    s3_bucket_path = f"s3://{bucket_name}"
                    # Don't use --delete.  We want to keep 'old' files locally.
                    sync_command_line = [aws_cli_path, "s3", "sync", s3_bucket_path, str(destination.absolute())]
                    if dry_run:
                        sync_command_line.append("--dryrun")
                    sync_command_line_str = " ".join(sync_command_line)
                    log.info(sync_command_line_str)

                    try:
                        sync_result = subprocess.run(sync_command_line_str, stdout=subprocess.PIPE, shell=True, env=env_var)
                    except FileNotFoundError as e:
                        self.error_out(f'error executing {" ".join(sync_command_line)} {e}')
                        return

                    for line in sync_result.stdout.decode(decoding).splitlines():
                        log.info(line.strip())

                    # check the results
                    ls_command_line = [aws_cli_path, "s3", "ls", "--summarize", "--recursive", s3_bucket_path]
                    ls_command_line_str = " ".join(ls_command_line)
                    log.info(ls_command_line_str)
                    ls_result = subprocess.run(ls_command_line_str, stdout=subprocess.PIPE, shell=True, env=env_var)
                    count += 1
                    ls_stdout = "".join([c for c in ls_result.stdout.decode(decoding) if c not in " \r\n"])  # remove all whitespace
                    ls_parsed = ls_re.search(ls_stdout)
                    if ls_parsed is None:
                        log.error(f"parse error:\n{ls_command_line_str=}\n{ls_stdout=}")
                    else:
                        s3_object_count = int(ls_parsed.group(1))
                        s3_total_size = int(ls_parsed.group(2))
                        local_size, local_count = get_dir_size(destination)

                        # rough check that the sync worked
                        if s3_total_size > local_size:
                            # we're missing files
                            message = "not all files backed up"
                            output_routine = self.error_out
                        elif s3_total_size != local_size:
                            # Compare size, not number of files, since aws s3 sync does not copy files of zero size.
                            message = "mismatch"
                            output_routine = self.warning_out
                        else:
                            message = "match"
                            output_routine = log.info
                        output_routine(f"{bucket_name} : {message} (s3_count={s3_object_count}, local_count={local_count}; s3_total_size={s3_total_size}, local_size={local_size})")

        self.info_out(f"{len(buckets)} buckets, {count} backed up, {len(exclusions)} excluded")
