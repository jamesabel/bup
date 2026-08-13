from unittest.mock import patch, MagicMock

import pytest


def _make_args(**overrides):
    defaults = dict(
        path="/tmp/backup",
        token="ghp_token",
        profile="default",
        dry_run=False,
        exclude=None,
        s3=False,
        dynamodb=False,
        github=False,
        aws=False,
        verbose=False,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_engine(error_count: int = 0) -> MagicMock:
    engine = MagicMock()
    engine.error_count = error_count
    return engine


def _make_prefs() -> MagicMock:
    # detailed file logging off - a bare MagicMock would look like a truthy directory and start writing log files
    return MagicMock(detailed_log_directory=None, detailed_log_file_size_limit_mb=None)


@patch("bup.cli.cli_main.S3Backup")
@patch("bup.cli.cli_main.DynamoDBBackup")
@patch("bup.cli.cli_main.GithubBackup")
@patch("bup.cli.cli_main.Balsa")
@patch("bup.cli.cli_main.get_preferences")
def test_dry_run_true_written_to_preferences(mock_get_prefs, mock_balsa, mock_gh, mock_ddb, mock_s3):
    prefs = _make_prefs()
    mock_get_prefs.return_value = prefs
    from bup.cli.cli_main import cli_main

    cli_main(_make_args(dry_run=True))

    assert prefs.dry_run is True


@patch("bup.cli.cli_main.S3Backup")
@patch("bup.cli.cli_main.DynamoDBBackup")
@patch("bup.cli.cli_main.GithubBackup")
@patch("bup.cli.cli_main.Balsa")
@patch("bup.cli.cli_main.get_preferences")
def test_dry_run_false_written_to_preferences(mock_get_prefs, mock_balsa, mock_gh, mock_ddb, mock_s3):
    prefs = _make_prefs()
    mock_get_prefs.return_value = prefs
    from bup.cli.cli_main import cli_main

    cli_main(_make_args(dry_run=False))

    assert prefs.dry_run is False


@patch("bup.cli.cli_main.S3Backup")
@patch("bup.cli.cli_main.DynamoDBBackup")
@patch("bup.cli.cli_main.GithubBackup")
@patch("bup.cli.cli_main.Balsa")
@patch("bup.cli.cli_main.get_preferences")
def test_s3_backup_started_with_s3_flag(mock_get_prefs, mock_balsa, mock_gh, mock_ddb, mock_s3):
    prefs = _make_prefs()
    mock_get_prefs.return_value = prefs
    mock_engine = _make_engine()
    mock_s3.return_value = mock_engine
    from bup.cli.cli_main import cli_main

    cli_main(_make_args(s3=True))

    mock_engine.start.assert_called_once()
    mock_engine.wait.assert_called_once()  # QThread uses wait(), not join()


@patch("bup.cli.cli_main.S3Backup")
@patch("bup.cli.cli_main.DynamoDBBackup")
@patch("bup.cli.cli_main.GithubBackup")
@patch("bup.cli.cli_main.Balsa")
@patch("bup.cli.cli_main.get_preferences")
def test_aws_flag_starts_both_s3_and_dynamodb(mock_get_prefs, mock_balsa, mock_gh, mock_ddb, mock_s3):
    prefs = _make_prefs()
    mock_get_prefs.return_value = prefs
    s3_engine = _make_engine()
    ddb_engine = _make_engine()
    mock_s3.return_value = s3_engine
    mock_ddb.return_value = ddb_engine
    from bup.cli.cli_main import cli_main

    cli_main(_make_args(aws=True))

    s3_engine.start.assert_called_once()
    ddb_engine.start.assert_called_once()


@patch("bup.cli.cli_main.S3Backup")
@patch("bup.cli.cli_main.DynamoDBBackup")
@patch("bup.cli.cli_main.GithubBackup")
@patch("bup.cli.cli_main.Balsa")
@patch("bup.cli.cli_main.get_preferences")
def test_backup_errors_produce_nonzero_exit_code(mock_get_prefs, mock_balsa, mock_gh, mock_ddb, mock_s3):
    prefs = _make_prefs()
    mock_get_prefs.return_value = prefs
    mock_s3.return_value = _make_engine(error_count=2)
    from bup.cli.cli_main import cli_main

    with pytest.raises(SystemExit) as exc_info:
        cli_main(_make_args(s3=True))

    assert exc_info.value.code == 1


@patch("bup.cli.cli_main.S3Backup")
@patch("bup.cli.cli_main.DynamoDBBackup")
@patch("bup.cli.cli_main.GithubBackup")
@patch("bup.cli.cli_main.Balsa")
@patch("bup.cli.cli_main.get_preferences")
def test_backup_without_errors_exits_normally(mock_get_prefs, mock_balsa, mock_gh, mock_ddb, mock_s3):
    prefs = _make_prefs()
    mock_get_prefs.return_value = prefs
    mock_s3.return_value = _make_engine(error_count=0)
    from bup.cli.cli_main import cli_main

    cli_main(_make_args(s3=True))  # should not raise SystemExit
