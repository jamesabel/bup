from pathlib import Path
from unittest.mock import patch, MagicMock

from botocore.exceptions import ClientError, NoCredentialsError

from bup import UITypes
from bup.dynamodb_backup import DynamoDBBackup


def _make_backup(info=None, warning=None, error=None) -> DynamoDBBackup:
    return DynamoDBBackup(UITypes.cli, info or (lambda s: None), warning or (lambda s: None), error or (lambda s: None))


def _make_preferences(tmp_path: Path, dry_run: bool = False) -> MagicMock:
    preferences = MagicMock()
    preferences.backup_directory = str(tmp_path)
    preferences.dry_run = dry_run
    preferences.aws_profile = None
    preferences.aws_access_key_id = None
    preferences.aws_secret_access_key = None
    preferences.aws_region = None
    return preferences


def _make_dynamodb_access_factory(table_names: list, table_mocks: dict):
    """
    DynamoDBAccess is constructed twice: once without a table name (to list tables) and once per table.
    """
    list_access = MagicMock()
    list_access.get_table_names.return_value = table_names

    def factory(*args, **kwargs):
        if args:
            return table_mocks[args[0]]
        return list_access

    return factory


@patch("bup.dynamodb_backup.ExclusionPreferences")
@patch("bup.dynamodb_backup.DynamoDBAccess")
@patch("bup.dynamodb_backup.get_preferences")
def test_missing_credentials_surface_error(mock_get_prefs, mock_ddb_access, mock_exclusions, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_ddb_access.return_value.get_table_names.side_effect = NoCredentialsError()
    errors = []
    backup = _make_backup(error=errors.append)

    backup.run()

    assert len(errors) == 1
    assert "could not list DynamoDB tables" in errors[0]
    assert backup.error_count == 1


@patch("bup.dynamodb_backup.dynamodb_to_json", return_value="{}")
@patch("bup.dynamodb_backup.ExclusionPreferences")
@patch("bup.dynamodb_backup.DynamoDBAccess")
@patch("bup.dynamodb_backup.get_preferences")
def test_table_backed_up_to_pickle_and_json(mock_get_prefs, mock_ddb_access, mock_exclusions, mock_to_json, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_exclusions.return_value.get_no_comments.return_value = []
    table = MagicMock()
    table.scan_table_cached.return_value = [{"id": 1}]
    mock_ddb_access.side_effect = _make_dynamodb_access_factory(["my_table"], {"my_table": table})
    infos = []
    backup = _make_backup(info=infos.append)

    backup.run()

    assert (tmp_path / "dynamodb" / "my_table.pickle").exists()
    assert (tmp_path / "dynamodb" / "my_table.json").exists()
    assert any("1 backed up" in i for i in infos)


@patch("bup.dynamodb_backup.dynamodb_to_json", return_value="{}")
@patch("bup.dynamodb_backup.ExclusionPreferences")
@patch("bup.dynamodb_backup.DynamoDBAccess")
@patch("bup.dynamodb_backup.get_preferences")
def test_excluded_table_is_skipped(mock_get_prefs, mock_ddb_access, mock_exclusions, mock_to_json, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_exclusions.return_value.get_no_comments.return_value = ["excluded_table"]
    table = MagicMock()
    table.scan_table_cached.return_value = [{"id": 1}]
    mock_ddb_access.side_effect = _make_dynamodb_access_factory(["excluded_table", "backed_up_table"], {"backed_up_table": table})
    infos = []
    backup = _make_backup(info=infos.append)

    backup.run()

    assert not (tmp_path / "dynamodb" / "excluded_table.pickle").exists()
    assert (tmp_path / "dynamodb" / "backed_up_table.pickle").exists()
    assert any("excluding excluded_table" in i for i in infos)


@patch("bup.dynamodb_backup.dynamodb_to_json", return_value="{}")
@patch("bup.dynamodb_backup.ExclusionPreferences")
@patch("bup.dynamodb_backup.DynamoDBAccess")
@patch("bup.dynamodb_backup.get_preferences")
def test_failed_table_scan_does_not_kill_remaining_tables(mock_get_prefs, mock_ddb_access, mock_exclusions, mock_to_json, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path)
    mock_exclusions.return_value.get_no_comments.return_value = []
    bad_table = MagicMock()
    bad_table.scan_table_cached.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "Scan")
    good_table = MagicMock()
    good_table.scan_table_cached.return_value = [{"id": 1}]
    mock_ddb_access.side_effect = _make_dynamodb_access_factory(["bad_table", "good_table"], {"bad_table": bad_table, "good_table": good_table})
    errors = []
    infos = []
    backup = _make_backup(info=infos.append, error=errors.append)

    backup.run()

    assert any("could not scan bad_table" in e for e in errors)
    assert (tmp_path / "dynamodb" / "good_table.pickle").exists()
    assert any("1 backed up" in i for i in infos)


@patch("bup.dynamodb_backup.dynamodb_to_json", return_value="{}")
@patch("bup.dynamodb_backup.ExclusionPreferences")
@patch("bup.dynamodb_backup.DynamoDBAccess")
@patch("bup.dynamodb_backup.get_preferences")
def test_dry_run_does_not_write_files(mock_get_prefs, mock_ddb_access, mock_exclusions, mock_to_json, tmp_path):
    mock_get_prefs.return_value = _make_preferences(tmp_path, dry_run=True)
    mock_exclusions.return_value.get_no_comments.return_value = []
    mock_ddb_access.side_effect = _make_dynamodb_access_factory(["my_table"], {})
    infos = []
    backup = _make_backup(info=infos.append)

    backup.run()

    assert not (tmp_path / "dynamodb").exists()
    assert any("dry run my_table" in i for i in infos)
