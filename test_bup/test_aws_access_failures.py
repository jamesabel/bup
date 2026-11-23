"""
Tests for the AWS backups (S3 and DynamoDB) when AWS can not be accessed at all: an AWS profile that does not exist, and no
connectivity. Either is an error in the backup's output, and the backup ends without raising (an exception that leaves a backup's
thread takes the whole application down).
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

from pathlib import Path
from typing import Callable, List, Optional
from unittest.mock import patch, MagicMock

import pytest
from awsimple import DynamoDBAccess, S3Access
from botocore.exceptions import EndpointConnectionError

from bup import UITypes
from bup.dynamodb_backup import DynamoDBBackup

from .s3_sync_fakes import FakeS3, make_preferences, run_s3_backup

no_such_profile = "bup-test-profile-that-does-not-exist"


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def no_aws_configuration(monkeypatch, tmp_path):
    """
    No AWS profiles or credentials at all, whatever this machine has: the real awsimple accesses of these tests find no profile.
    """
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials-file"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config-file"))


def _make_preferences(tmp_path: Path, aws_profile: Optional[str] = None) -> MagicMock:
    preferences = make_preferences(tmp_path)
    preferences.aws_profile = aws_profile
    return preferences


def _run_dynamodb_backup(tmp_path: Path, dynamodb_access: Callable, aws_profile: Optional[str] = None) -> DynamoDBBackup:
    """
    Run a DynamoDB backup with dynamodb_access in place of awsimple's DynamoDBAccess (which can be the real DynamoDBAccess).
    :return: the backup, with what it put out in .infos and .errors
    """
    infos: List[str] = []
    errors: List[str] = []
    backup = DynamoDBBackup(UITypes.cli, infos.append, lambda s: None, errors.append)
    backup.infos = infos
    backup.errors = errors
    with (
        patch("bup.dynamodb_backup.get_preferences", return_value=_make_preferences(tmp_path, aws_profile)),
        patch("bup.dynamodb_backup.DynamoDBAccess", dynamodb_access),
        patch("bup.dynamodb_backup.ExclusionPreferences") as mock_exclusions,
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return backup


def _no_connectivity() -> EndpointConnectionError:
    return EndpointConnectionError(endpoint_url="https://aws.invalid/")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_backup_with_a_profile_that_does_not_exist_is_an_error(tmp_path, no_aws_configuration):
    # the real S3Access, which raises for the profile when it is made (before anything is asked of S3)
    backup = run_s3_backup(tmp_path, S3Access, _make_preferences(tmp_path, no_such_profile))

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("could not list S3 buckets - check credentials and connectivity : ")
    assert no_such_profile in backup.errors[0]
    assert backup.error_count == 1
    assert not any("backed up" in info for info in backup.infos)  # the backup ended there


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dynamodb_backup_with_a_profile_that_does_not_exist_is_an_error(tmp_path, no_aws_configuration):
    backup = _run_dynamodb_backup(tmp_path, DynamoDBAccess, no_such_profile)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("could not list DynamoDB tables - check credentials and connectivity : ")
    assert no_such_profile in backup.errors[0]
    assert backup.error_count == 1
    assert not any("backed up" in info for info in backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_s3_backup_without_connectivity_is_an_error(tmp_path):
    fake_s3 = FakeS3({})

    def s3_access_without_connectivity(*args, **kwargs):
        s3_access = fake_s3(*args, **kwargs)
        s3_access.bucket_list.side_effect = _no_connectivity()
        return s3_access

    backup = run_s3_backup(tmp_path, s3_access_without_connectivity)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("could not list S3 buckets - check credentials and connectivity : ")
    assert "https://aws.invalid/" in backup.errors[0]
    assert backup.error_count == 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dynamodb_backup_without_connectivity_is_an_error(tmp_path):
    dynamodb_access = MagicMock()
    dynamodb_access.return_value.get_table_names.side_effect = _no_connectivity()

    backup = _run_dynamodb_backup(tmp_path, dynamodb_access)

    assert len(backup.errors) == 1
    assert backup.errors[0].startswith("could not list DynamoDB tables - check credentials and connectivity : ")
    assert "https://aws.invalid/" in backup.errors[0]
    assert backup.error_count == 1
