from unittest.mock import patch, MagicMock, call
from pathlib import Path

import pytest
from git.exc import GitCommandError

from bup.github_backup import GithubBackup
from bup import UITypes


@pytest.fixture
def github_backup(qapp):
    warnings = []
    errors = []
    backup = GithubBackup(UITypes.cli, lambda s: None, lambda s: warnings.append(s), lambda s: errors.append(s))
    backup.caller_warning_out = lambda s: warnings.append(s)
    backup.caller_error_out = lambda s: errors.append(s)
    backup._warnings = warnings
    backup._errors = errors
    return backup


def _branch(name):
    b = MagicMock()
    b.name = name
    return b


def _overwritten_error():
    return GitCommandError(["git", "checkout"], 1, stderr=b"Your local changes to the following files would be overwritten by checkout:\n\tfile.py")


def _no_files_error(branch_name="empty"):
    return GitCommandError(["git", "checkout"], 1, stderr=f"pathspec '{branch_name}' did not match any file(s) known to git".encode())


def test_overwritten_error_is_warning_not_error(github_backup, tmp_path):
    """'would be overwritten by checkout' must produce a warning, not an error dialog."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mock_repo = MagicMock()
    mock_repo.git.checkout.side_effect = _overwritten_error()

    with patch("git.Repo", return_value=mock_repo):
        result = github_backup.pull_branches("owner/repo", [_branch("main")], repo_dir)

    assert result is False
    assert len(github_backup._errors) == 0
    assert len(github_backup._warnings) == 1
    assert "overwritten" in github_backup._warnings[0].lower() or "line-ending" in github_backup._warnings[0].lower()


def test_no_files_error_continues_to_next_branch(github_backup, tmp_path):
    """'did not match any file' should skip the branch and keep processing others."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mock_repo = MagicMock()
    # first branch fails with no-files, second succeeds
    mock_repo.git.checkout.side_effect = [_no_files_error("empty-branch"), None]

    with patch("git.Repo", return_value=mock_repo):
        result = github_backup.pull_branches("owner/repo", [_branch("empty-branch"), _branch("main")], repo_dir)

    assert result is True
    assert len(github_backup._errors) == 0


def test_reset_hard_called_before_switch(github_backup, tmp_path):
    """git reset --hard must precede git switch when returning to the main branch."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mock_repo = MagicMock()

    with patch("git.Repo", return_value=mock_repo):
        github_backup.pull_branches("owner/repo", [_branch("feature"), _branch("main")], repo_dir)

    git_calls = mock_repo.git.mock_calls
    reset_indices = [i for i, c in enumerate(git_calls) if c == call.reset("--hard")]
    switch_indices = [i for i, c in enumerate(git_calls) if c == call.switch("main")]

    assert len(switch_indices) == 1, "switch('main') should be called exactly once"
    assert len(reset_indices) >= 1, "reset('--hard') should be called at least once"
    assert reset_indices[-1] < switch_indices[0], "reset --hard must come before git switch"


def test_other_git_errors_use_warning_out(github_backup, tmp_path):
    """
    Unexpected git pull errors (e.g. 'refusing to merge unrelated histories' after a force-push)
    are warnings, not errors - the caller falls back to a fresh clone and only escalates to an
    error if that also fails.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mock_repo = MagicMock()
    mock_repo.git.pull.side_effect = GitCommandError(["git", "pull"], 128, stderr=b"fatal: refusing to merge unrelated histories")

    with patch("git.Repo", return_value=mock_repo):
        result = github_backup.pull_branches("owner/repo", [_branch("main")], repo_dir)

    assert result is False
    assert len(github_backup._errors) == 0
    assert len(github_backup._warnings) == 1


def test_single_branch_no_switch(github_backup, tmp_path):
    """With only one branch there should be no git switch call."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mock_repo = MagicMock()

    with patch("git.Repo", return_value=mock_repo):
        github_backup.pull_branches("owner/repo", [_branch("main")], repo_dir)

    git_calls = mock_repo.git.mock_calls
    switch_calls = [c for c in git_calls if c == call.switch("main")]
    assert len(switch_calls) == 0


def _run_with_failed_pull(github_backup, tmp_path, clone_side_effect=None):
    """
    Run GithubBackup.run() against one previously-cloned repo whose pull fails,
    so the fresh-clone fallback is exercised.
    """
    (tmp_path / "github" / "owner" / "repo").mkdir(parents=True)

    preferences = MagicMock()
    preferences.backup_directory = str(tmp_path)
    preferences.dry_run = False
    preferences.github_token = "test_token"

    github_repo = MagicMock()
    github_repo.__str__.return_value = "owner/repo"
    github_repo.branches.return_value = [_branch("main")]
    github_repo.clone_url = "https://github.com/owner/repo.git"

    gh = MagicMock()
    gh.repositories.return_value = [github_repo]

    with (
        patch("bup.github_backup.get_preferences", return_value=preferences),
        patch("bup.github_backup.ExclusionPreferences") as mock_exclusions,
        patch("bup.github_backup.github3.login", return_value=gh),
        patch("bup.github_backup.shutil.which", return_value="git"),
        patch("bup.github_backup.time.sleep"),
        patch("git.Repo.clone_from", side_effect=clone_side_effect) as mock_clone,
        patch.object(GithubBackup, "pull_branches", return_value=False),
    ):
        mock_exclusions.return_value.get_no_comments.return_value = []
        github_backup.run()

    return mock_clone


def test_failed_pull_recovered_by_clone_is_not_an_error(github_backup, tmp_path):
    """A failed pull followed by a successful fresh clone is a recovered backup - no error."""
    mock_clone = _run_with_failed_pull(github_backup, tmp_path)

    mock_clone.assert_called_once()
    assert len(github_backup._errors) == 0


def test_failed_pull_and_failed_clone_is_an_error(github_backup, tmp_path):
    """If the fresh-clone fallback also fails, the repo was not backed up - that is an error."""
    clone_error = GitCommandError(["git", "clone"], 128, stderr=b"fatal: could not read from remote repository")
    _run_with_failed_pull(github_backup, tmp_path, clone_side_effect=clone_error)

    assert len(github_backup._errors) == 1
