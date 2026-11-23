"""
Verification of a local file of the S3 backup against the metadata of its S3 object: size, hash and modification time.
"""

import hashlib
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from awscrt import checksums
from awsimple import S3ObjectMetadata, get_file_crc64nvme
from awsimple.s3_object import native_checksum_to_hex

# A local file gets the modification time of its S3 object when it is downloaded. S3 gives that time to the second in an object's
# metadata and more precisely in a bucket listing, and some file systems keep times to 2 seconds, so times this close are the same.
mtime_abs_tol = 2.0  # seconds

read_size = 1024 * 1024  # bytes read from a file at a time


def get_file_crc(path: Path, crc: Callable[[bytes, int], int]) -> str:
    """
    A 32 bit CRC of a file's contents, as S3 gives it once converted to hex.
    :param crc: gives the CRC of bytes that follow the bytes of a previous CRC, e.g. zlib.crc32
    """
    value = 0
    with open(path, "rb") as f:
        while chunk := f.read(read_size):
            value = crc(chunk, value)
    return f"{value:08x}"


def get_file_digest(path: Path, algorithm: str) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, algorithm).hexdigest()


# The hashes of an S3 object's contents that a local file can be checked against, strongest first: the name of the hash, the field of
# S3's native checksum of it, and what computes it for a local file. A CRC detects a damaged or incomplete file, and a SHA also
# detects contents that were made to differ.
native_hashes: List[Tuple[str, str, Callable[[Path], str]]] = [
    ("SHA-256", "ChecksumSHA256", lambda path: get_file_digest(path, "sha256")),
    ("SHA-1", "ChecksumSHA1", lambda path: get_file_digest(path, "sha1")),
    ("CRC64NVME", "ChecksumCRC64NVME", get_file_crc64nvme),
    ("CRC32C", "ChecksumCRC32C", lambda path: get_file_crc(path, checksums.crc32c)),
    ("CRC32", "ChecksumCRC32", lambda path: get_file_crc(path, zlib.crc32)),
]


def get_s3_object_hash(s3_object_metadata: S3ObjectMetadata) -> Optional[Tuple[str, str, Callable[[Path], str]]]:
    """
    The strongest hash of the whole contents that S3 has for an object. Not every object has one: S3 only has a checksum of an
    object that was written with one, and the checksum of an object that was uploaded in parts can be of its parts ("composite"),
    which can not be compared with a hash of a file.
    :return: (name of the hash, the hash as a hex string, what computes it for a local file), or None if S3 has no hash of the whole contents
    """
    if (sha512 := s3_object_metadata.get_content_sha512()) is not None:
        # S3's native SHA-512, or the SHA-512 awsimple puts in the object metadata of what it writes
        return "SHA-512", sha512, lambda path: get_file_digest(path, "sha512")
    for name, checksum_field, get_file_hash in native_hashes:
        if (s3_hash := native_checksum_to_hex(s3_object_metadata.checksums.get(checksum_field))) is not None:
            return name, s3_hash, get_file_hash
    return None


@dataclass
class S3FileVerification:
    """
    The result of verifying one local file against the metadata of its S3 object.
    """

    key: str
    problems: List[str] = field(default_factory=list)  # why the local file is not a copy of the S3 object (none if it is)
    mtime_difference: Optional[str] = None  # how the modification times differ (None if they are the same)
    hash_name: Optional[str] = None  # the hash that was compared (None if it was not: there are problems without it, or S3 has none)
    s3_has_hash: bool = True  # False if S3 has no hash of the whole contents of the object


def verify_local_file(local_path: Path, s3_object_metadata: S3ObjectMetadata) -> S3FileVerification:
    """
    Check a local file of the backup against the metadata of its S3 object: its size, the hash of its contents (the strongest that
    S3 has for the object, see get_s3_object_hash()) and its modification time.
    """
    verification = S3FileVerification(s3_object_metadata.key)
    try:
        local_stat = local_path.stat()
    except OSError as e:
        verification.problems.append(f'no local file "{local_path}" ({e})')
        return verification

    if local_stat.st_size != s3_object_metadata.size:
        # the contents differ, which a hash would only say again
        verification.problems.append(f"the local file is {local_stat.st_size} bytes but the S3 object is {s3_object_metadata.size} bytes")
    elif (s3_object_hash := get_s3_object_hash(s3_object_metadata)) is None:
        verification.s3_has_hash = False
    else:
        hash_name, s3_hash, get_file_hash = s3_object_hash
        try:
            local_hash = get_file_hash(local_path)
        except OSError as e:
            verification.problems.append(f'could not read the local file "{local_path}" ({e})')
        else:
            verification.hash_name = hash_name
            if local_hash != s3_hash:
                verification.problems.append(f"the {hash_name} of the local file is {local_hash} but the S3 object's is {s3_hash}")

    s3_mtime = s3_object_metadata.mtime.timestamp()
    if abs(local_stat.st_mtime - s3_mtime) > mtime_abs_tol:
        verification.mtime_difference = f"the local file was modified {local_stat.st_mtime - s3_mtime:+.0f} seconds from the S3 object ({s3_object_metadata.mtime.isoformat()})"
    return verification
