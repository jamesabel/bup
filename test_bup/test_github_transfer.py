"""
Tests for what the GitHub backup reports as received by a clone or fetch.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from unittest.mock import patch, MagicMock

import pytest
from git.exc import GitCommandError

from bup import UITypes
from bup.github_backup import GithubBackup, parse_count_objects


def _count_objects_output(size_kib: int, size_pack_kib: int) -> str:
    return f"count: 3\nsize: {size_kib}\nin-pack: 120\npacks: 1\nsize-pack: {size_pack_kib}\nprune-packable: 0\ngarbage: 0\nsize-garbage: 0"


def _branch(name: str) -> MagicMock:
    branch = MagicMock()
    branch.name = name
    return branch


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def github_backup(qapp):
    infos = []
    warnings = []
    backup = GithubBackup(UITypes.cli, infos.append, warnings.append, lambda s: None)
    backup.infos = infos
    backup.warnings = warnings
    return backup


def _run_backup(github_backup: GithubBackup, tmp_path, dry_run: bool = False) -> MagicMock:
    """
    Run a GitHub backup of one repo that has not been cloned yet.
    :return: the mock of the clone
    """
    github_repo = MagicMock()
    github_repo.__str__.return_value = "owner/repo"
    github_repo.branches.return_value = [_branch("main")]
    github_repo.clone_url = "https://github.com/owner/repo.git"
    gh = MagicMock()
    gh.repositories.return_value = [github_repo]
    cloned_repo = MagicMock()
    cloned_repo.git.count_objects.return_value = _count_objects_output(0, 300)
    with (
        patch("bup.github_backup.get_preferences", return_value=MagicMock(backup_directory=str(tmp_path), dry_run=dry_run, github_token="test_token")),
        patch("bup.github_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.github_backup.github3.login", return_value=gh),
        patch("bup.github_backup.shutil.which", return_value="git"),
        patch("bup.github_backup.time.sleep"),
        patch("git.Repo.clone_from", return_value=cloned_repo) as mock_clone,
        patch.object(GithubBackup, "pull_branches", return_value=True),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        github_backup.run()
    return mock_clone


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_parse_count_objects():
    assert parse_count_objects(_count_objects_output(4, 100)) == 104 * 1024


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_parse_count_objects_without_the_sizes_is_unknown():
    assert parse_count_objects("") is None
    assert parse_count_objects("count: 3\nsize: 4") is None  # no size-pack
    assert parse_count_objects("warning: something unexpected") is None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fetch_reports_the_growth_of_the_repository(github_backup, tmp_path):
    mock_repo = MagicMock()
    mock_repo.git.count_objects.side_effect = [_count_objects_output(0, 100), _count_objects_output(4, 100)]

    with patch("git.Repo", return_value=mock_repo):
        github_backup.pull_branches("owner/repo", [_branch("main")], tmp_path)

    assert "owner/repo : received 4.0 KB" in github_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_fetch_that_received_nothing_reports_nothing(github_backup, tmp_path):
    mock_repo = MagicMock()
    # the same size, or smaller (git may repack after a fetch), is not a transfer
    mock_repo.git.count_objects.side_effect = [_count_objects_output(8, 100), _count_objects_output(0, 100)]

    with patch("git.Repo", return_value=mock_repo):
        github_backup.pull_branches("owner/repo", [_branch("main")], tmp_path)

    assert not any("received" in info for info in github_backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_unknown_repository_size_is_a_logged_warning_and_the_backup_continues(github_backup, tmp_path, caplog):
    mock_repo = MagicMock()
    mock_repo.git.count_objects.side_effect = GitCommandError(["git", "count-objects"], 128, stderr=b"fatal: not a git repository")

    with patch("git.Repo", return_value=mock_repo):
        result = github_backup.pull_branches("owner/repo", [_branch("main")], tmp_path)

    assert result is True
    assert github_backup.warnings == []  # not a backup warning - the backup itself is unaffected
    assert any("could not get the repository size" in record.getMessage() for record in caplog.records)
    assert not any("received" in info for info in github_backup.infos)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_clone_reports_the_size_of_the_new_repository(github_backup, tmp_path):
    mock_clone = _run_backup(github_backup, tmp_path)

    mock_clone.assert_called_once()
    assert "owner/repo : received 300.0 KB" in github_backup.infos
    assert "transfer total : received 300.0 KB" in github_backup.infos  # no cost - GitHub does not charge for transfer


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dry_run_reports_no_transfer(github_backup, tmp_path):
    mock_clone = _run_backup(github_backup, tmp_path, dry_run=True)

    mock_clone.assert_not_called()
    assert not any("received" in info for info in github_backup.infos)
