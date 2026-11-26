"""
The fix of a local file of the S3 backup that the verification found to have another modification time than its S3 object (see
README "Fixing modification times"): the local file gets the modification time of the S3 object, but only once its contents are
known to be the S3 object's. They are compared by the hash S3 has of the object, and for an object S3 has no hash of, the object
is downloaded to a temporary directory on the backup drive and the two files are compared. The download is deleted as soon as it
has been compared (also when the comparison or the download fails), and remove_temp_dir() removes what a run that was cut short
left behind.
"""

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from awsimple import S3Access, AWSimpleException, get_s3_object_hash
from botocore.exceptions import BotoCoreError, ClientError

download_hash_name = "sha512"  # what a local file and the download of its S3 object are compared by (a name hashlib has)
temp_dir_name = "s3_temp"  # the directory of the downloads, in the backup directory (next to the "s3" directory, so on the backup drive and not in the backup of a bucket)


class MtimeFixOutcome(StrEnum):
    """
    What fix_local_mtime() did with a local file.
    """

    fixed = "fixed"  # the contents are the S3 object's, and the local file now has its modification time
    differs = "differs"  # the local file is not a copy of the S3 object (MtimeFix.reason says how), and was left as it was
    failed = "failed"  # the contents could not be compared, or the time could not be set (MtimeFix.reason says why)


@dataclass
class MtimeFix:
    """
    The outcome of fix_local_mtime() for one S3 object.
    """

    key: str
    outcome: MtimeFixOutcome
    reason: str = ""  # for differs and failed
    downloaded: bool = False  # True if the S3 object was downloaded to compare the contents (S3 has no hash of it)
    old_mtime: float = 0.0  # the modification time the local file had (for fixed)
    new_mtime: float = 0.0  # the modification time it was given, which is the S3 object's (for fixed)


def get_file_hash(path: Path) -> str:
    """
    :param path: path to a file
    :return: the hash (download_hash_name) of the contents of the file, as hex digits
    """
    with open(path, "rb") as file:
        return hashlib.file_digest(file, download_hash_name).hexdigest()


def remove_temp_dir(temp_dir: Path):
    """
    Remove the directory of the downloads with everything in it, if it exists. Raises OSError if it can not be removed.

    :param temp_dir: the directory of the downloads
    """
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def _fix_local_mtime(access: S3Access, key: str, local_path: Path, temp_dir: Path) -> MtimeFix:
    """
    fix_local_mtime(), other than that a failure is raised.
    """
    # The metadata as it is now, not as the verification had it: the comparison and the modification time are then of the same object.
    s3_object_metadata = access.get_s3_object_metadata(key)
    local_stat = local_path.stat()
    if local_stat.st_size != s3_object_metadata.size:
        return MtimeFix(key, MtimeFixOutcome.differs, f"the local file is {local_stat.st_size} bytes but the S3 object is {s3_object_metadata.size} bytes")

    if (s3_object_hash := get_s3_object_hash(s3_object_metadata)) is not None:
        downloaded = False
        local_hash = s3_object_hash.get_file_hash(local_path)
        if local_hash != s3_object_hash.value:
            return MtimeFix(key, MtimeFixOutcome.differs, f"the {s3_object_hash.name} of the local file is {local_hash} but the S3 object's is {s3_object_hash.value}")
        new_mtime = s3_object_metadata.mtime.timestamp()
    else:
        # S3 has no hash of the whole contents of this object, so get the contents themselves
        downloaded = True
        temp_dir.mkdir(parents=True, exist_ok=True)
        # A directory for this one download, which is deleted with the download when this block is left, however it is left. If it
        # can not be deleted that is raised (OSError), so the modification time is then not set and the failure is reported.
        with tempfile.TemporaryDirectory(dir=temp_dir) as download_dir:
            download_path = Path(download_dir, "s3_object")
            access.download(key, download_path, s3_object_metadata)
            local_hash = get_file_hash(local_path)
            download_hash = get_file_hash(download_path)
            # awsimple gives a download the modification time of the object it downloaded (which is not the object of the metadata
            # above if the object was written again since)
            new_mtime = download_path.stat().st_mtime
        if local_hash != download_hash:
            reason = f"the {download_hash_name} of the local file is {local_hash} but that of the S3 object, which was downloaded to compare, is {download_hash}"
            return MtimeFix(key, MtimeFixOutcome.differs, reason, downloaded)

    os.utime(local_path, (new_mtime, new_mtime))
    return MtimeFix(key, MtimeFixOutcome.fixed, downloaded=downloaded, old_mtime=local_stat.st_mtime, new_mtime=new_mtime)


def fix_local_mtime(access: S3Access, key: str, local_path: Path, temp_dir: Path) -> MtimeFix:
    """
    Give a local file the modification time of its S3 object, if the local file has the contents of the S3 object: its size, and
    the hash S3 has of the whole contents of the object (see awsimple's get_s3_object_hash()). When S3 has no such hash, the object
    is downloaded to a directory of its own in temp_dir and the local file is compared with the download, which is then deleted,
    also when the download or the comparison fails. A local file that is not a copy of the S3 object is left as it is, and so is
    one that could not be compared. Nothing is raised for one file.

    :param access: access to the bucket
    :param key: the key of the S3 object
    :param local_path: the local file of the S3 object
    :param temp_dir: the directory of the downloads (made when there is a download), which has to have room for the object
    :return: what was done, and why if the modification time was not fixed
    """
    try:
        return _fix_local_mtime(access, key, local_path, temp_dir)
    except (ClientError, BotoCoreError, AWSimpleException, OSError) as e:
        # e.g. the object was deleted since the verification, the download failed, there is no room for the download, or it could not be deleted
        return MtimeFix(key, MtimeFixOutcome.failed, str(e))
