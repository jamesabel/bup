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


def test_other_git_errors_use_error_out(github_backup, tmp_path):
    """Unexpected git errors should still call error_out."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    mock_repo = MagicMock()
    mock_repo.git.checkout.side_effect = GitCommandError(["git", "checkout"], 128, stderr=b"fatal: not a git repository")

    with patch("git.Repo", return_value=mock_repo):
        result = github_backup.pull_branches("owner/repo", [_branch("main")], repo_dir)

    assert result is False
    assert len(github_backup._errors) == 1


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
