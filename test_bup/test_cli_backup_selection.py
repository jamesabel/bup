"""
Tests for which backups the command line selects: the backups that are made and started, and the backup types whose exclusion list
"-e" sets.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from typing import Dict, List
from unittest.mock import patch, MagicMock

import pytest

from bup import BackupTypes
from bup.cli.cli_main import cli_main


def _run_cli(**selected) -> tuple:
    """
    Run the CLI with the given arguments (e.g. s3=True, exclude=["a"]), with stand-ins for the backups, the preferences and the logging.
    :return: (the backup classes that were made, by backup type name, and the exclusions that were set, by backup type name)
    """
    arguments = dict(path="backup_dir", token=None, profile=None, region=None, dry_run=False, size_only=False, verify=False, fix_mtime=False, exclude=None)
    arguments.update(s3=False, dynamodb=False, github=False, aws=False)
    arguments.update(selected)
    exclusions_set: Dict[str, List[str]] = {}

    def make_exclusion_preferences(exclusion_type: str) -> MagicMock:
        exclusion_preferences = MagicMock()
        exclusion_preferences.set.side_effect = lambda exclusions: exclusions_set.__setitem__(exclusion_type, exclusions)
        return exclusion_preferences

    with (
        patch("bup.cli.cli_main.S3Backup") as s3_backup,
        patch("bup.cli.cli_main.DynamoDBBackup") as dynamodb_backup,
        patch("bup.cli.cli_main.GithubBackup") as github_backup,
        patch("bup.cli.cli_main.ExclusionPreferences", side_effect=make_exclusion_preferences),
        patch("bup.cli.cli_main.get_preferences", return_value=MagicMock(detailed_log_directory=None, detailed_log_file_size_limit_mb=None)),
        patch("bup.cli.cli_main.Balsa"),
        patch("bup.cli.cli_main.set_detailed_file_logging"),
    ):
        backup_classes = {BackupTypes.S3.name: s3_backup, BackupTypes.DynamoDB.name: dynamodb_backup, BackupTypes.github.name: github_backup}
        for backup_class in backup_classes.values():
            backup_class.return_value.error_count = 0
        cli_main(MagicMock(**arguments))
    return backup_classes, exclusions_set


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize(
    "selected,expected_backup_types",
    [
        ({"s3": True}, ["S3"]),
        ({"dynamodb": True}, ["DynamoDB"]),
        ({"github": True}, ["github"]),
        ({"aws": True}, ["S3", "DynamoDB"]),
        ({"aws": True, "s3": True, "github": True}, ["S3", "DynamoDB", "github"]),
        ({}, []),
    ],
)
def test_selected_backups_are_made_started_and_waited_for(selected, expected_backup_types):
    backup_classes, _unused_exclusions_set = _run_cli(**selected)

    for backup_type_name, backup_class in backup_classes.items():
        if backup_type_name in expected_backup_types:
            backup_class.assert_called_once()  # made once, also when it is selected twice (e.g. --aws and --s3)
            backup_class.return_value.start.assert_called_once()
            backup_class.return_value.wait.assert_called_once()
        else:
            backup_class.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_backups_report_to_the_console(capsys):
    backup_classes, _unused_exclusions_set = _run_cli(github=True)

    ui_type, info_out, warning_out, error_out = backup_classes["github"].call_args.args
    info_out("a line")
    warning_out("a warning")
    error_out("an error")
    assert capsys.readouterr().out.splitlines() == ["a line", "WARNING: a warning", "ERROR: an error"]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize(
    "selected,expected_backup_types",
    [({"s3": True}, ["S3"]), ({"dynamodb": True}, ["DynamoDB"]), ({"github": True}, ["github"]), ({"aws": True}, ["S3", "DynamoDB"])],
)
def test_exclusions_are_set_for_the_selected_backup_types(selected, expected_backup_types):
    _unused_backup_classes, exclusions_set = _run_cli(exclude=["a", "b"], **selected)

    assert exclusions_set == {backup_type_name: ["a", "b"] for backup_type_name in expected_backup_types}


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_exclude_without_values_clears_the_exclusions_and_no_exclude_leaves_them(capsys):
    _unused_backup_classes, exclusions_set = _run_cli(s3=True, exclude=[])
    assert exclusions_set == {"S3": []}

    _unused_backup_classes, exclusions_set = _run_cli(s3=True)
    assert exclusions_set == {}


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_nothing_selected_says_so(capsys):
    _run_cli()

    assert "nothing to do" in capsys.readouterr().out
