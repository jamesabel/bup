"""
Tests for the files the DynamoDB backup writes for a table.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
The repository's conftest.py gives every test an empty AWS price cache of its own and makes fetching prices fail as if offline.
"""

import pickle
from pathlib import Path
from unittest.mock import patch, MagicMock

from bup import UITypes
from bup.dynamodb_backup import DynamoDBBackup

table_contents = [{"id": 1, "name": "a"}]


def _run_backup(tmp_path: Path, table_names: list):
    """
    Run a DynamoDB backup of tables that all have table_contents.
    :return: (the backup's info output, its error output)
    """
    table = MagicMock()
    table.scan_table_cached.return_value = table_contents
    list_access = MagicMock()
    list_access.get_table_names.return_value = table_names
    infos, errors = [], []
    backup = DynamoDBBackup(UITypes.cli, infos.append, lambda s: None, errors.append)
    preferences = MagicMock(backup_directory=str(tmp_path), dry_run=False, aws_profile=None, aws_access_key_id=None, aws_secret_access_key=None, aws_region=None)
    with (
        patch("bup.dynamodb_backup.get_preferences", return_value=preferences),
        patch("bup.dynamodb_backup.DynamoDBAccess", side_effect=lambda *args, **kwargs: table if args else list_access),
        patch("bup.dynamodb_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.dynamodb_backup.dynamodb_to_json", return_value='[{"id": 1}]'),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        backup.run()
    return infos, errors


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_table_is_written_as_pickle_and_json(tmp_path):
    infos, errors = _run_backup(tmp_path, ["my_table"])

    assert errors == []
    assert pickle.loads(Path(tmp_path, "dynamodb", "my_table.pickle").read_bytes()) == table_contents
    assert Path(tmp_path, "dynamodb", "my_table.json").read_text(encoding="utf-8") == '[{"id": 1}]'
    assert "1 tables, 1 backed up, 0 excluded" in infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_table_that_can_not_be_written_is_an_error_and_the_backup_goes_on(tmp_path):
    # a directory where the first table's pickle file has to be, so that the file can not be written
    Path(tmp_path, "dynamodb", "blocked_table.pickle").mkdir(parents=True)

    infos, errors = _run_backup(tmp_path, ["blocked_table", "my_table"])

    assert len(errors) == 1
    assert errors[0].startswith("could not write backup files for blocked_table : ")
    assert Path(tmp_path, "dynamodb", "my_table.json").exists()
    assert "2 tables, 1 backed up, 0 excluded" in infos
