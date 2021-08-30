import os
from pathlib import Path
from multiprocessing import freeze_support, Pool
from psutil import cpu_count
from typing import Union

from awsimple import S3Access
from balsa import get_logger

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences

log = get_logger(__application_name__)

freeze_support()


def get_dir_size(dir_path: Path):
    dir_size = 0
    file_count = 0
    for dir_path, _, file_names in os.walk(dir_path):
        for file_name in file_names:
            file_count += 1
            dir_size += os.path.getsize(os.path.join(dir_path, file_name))
    return dir_size, file_count


def file_backup(s3_bucket: str, s3_key: str, destination_path: Path):
    s3_access = S3Access(s3_bucket)

    # STOPPED HERE
    raise NotImplementedError


class S3Backup(BupBase):

    backup_type = BackupTypes.S3

    def run(self):

        preferences = get_preferences(self.ui_type)
        exclusions_no_comments = ExclusionPreferences(BackupTypes.S3.name).get_no_comments()
        dry_run = preferences.dry_run

        backup_directory = os.path.join(preferences.backup_directory, "s3")

        os.makedirs(backup_directory, exist_ok=True)

        buckets = S3Access(profile_name=preferences.aws_profile).bucket_list()
        self.info_out(f"found {len(buckets)} buckets")

        process_pool_size = cpu_count(logical=False)  # only use real cores (not HT/SMT)
        with Pool(processes=process_pool_size) as process_pool:

            count = 0
            for bucket_name in buckets:

                # do the sync
                if bucket_name in exclusions_no_comments:
                    self.info_out(f"excluding {bucket_name}")
                else:
                    if dry_run:
                        self.info_out(f"dry run {bucket_name}")
                    else:
                        self.info_out(f"{bucket_name}")

                        s3_access = S3Access(bucket_name=bucket_name)
                        for s3_key, s3_metadata in s3_access.dir().items():
                            destination_path = Path(backup_directory, s3_key)
                            process_pool.apply_async(file_backup, (bucket_name, s3_key, destination_path))

                        # check the results
                        # todo

                        # rough check that the sync worked
                        # if s3_total_size > local_size:
                        #     # we're missing files
                        #     message = "not all files backed up"
                        #     output_routine = self.error_out
                        # elif s3_total_size != local_size:
                        #     # Compare size, not number of files, since aws s3 sync does not copy files of zero size.
                        #     message = "mismatch"
                        #     output_routine = self.warning_out
                        # else:
                        #     message = "match"
                        #     output_routine = log.info
                        # output_routine(f"{bucket_name} : {message} (s3_count={s3_object_count}, local_count={local_count}; s3_total_size={s3_total_size}, local_size={local_size})")

        self.info_out(f"{len(buckets)} buckets, {count} backed up, {len(exclusions_no_comments)} excluded")
