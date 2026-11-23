"""
Tests for the paths through the GitHub backup that are not the ordinary clone or fetch: nothing to back up with, repositories that
are skipped, and the failures a repository can have.
All tests, fixtures and helpers in this file are AI-authored (Claude Code).
"""

from pathlib import Path
from typing import List, Optional
from unittest.mock import call, patch, MagicMock

import pytest
from git.exc import GitCommandError, InvalidGitRepositoryError
from github3.exceptions import AuthenticationFailed

from bup import UITypes
from bup.github_backup import GithubBackup, get_main_branch_name, is_excluded


def _branch(name: str) -> MagicMock:
    branch = MagicMock()
    branch.name = name
    return branch


def _github_repo(owner_and_name: str = "owner/repo", branch_names: Optional[List[str]] = None) -> MagicMock:
    github_repo = MagicMock()
    github_repo.__str__.return_value = owner_and_name
    github_repo.branches.return_value = [_branch(branch_name) for branch_name in (branch_names or ["main"])]
    github_repo.clone_url = f"https://github.com/{owner_and_name}.git"
    return github_repo


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.fixture
def github_backup(qapp):
    infos, warnings, errors = [], [], []
    backup = GithubBackup(UITypes.cli, infos.append, warnings.append, errors.append)
    backup.infos = infos
    backup.warnings = warnings
    backup.errors = errors
    return backup


class _Run:
    """
    A run of the GitHub backup with stand-ins for GitHub and git. After run(), .clone and .pull_branches are the mocks of the clone
    and of GithubBackup.pull_branches.
    """

    def __init__(self, github_backup: GithubBackup, tmp_path: Path):
        self.github_backup = github_backup
        self.tmp_path = tmp_path
        self.github_repos = [_github_repo()]
        self.login = MagicMock()  # what github3.login() returns
        self.login.repositories.side_effect = lambda: self.github_repos
        self.git_executable: Optional[str] = "git"
        self.exclusions: List[str] = []
        self.pull_branches_result = True  # or an exception that pull_branches raises, or a list of these for one call after the other
        self.rmdir = None  # a stand-in for bup's rmdir (None for the real one)
        self.clone = MagicMock()
        self.pull_branches = MagicMock()

    def make_local_repo(self, owner_and_name: str = "owner/repo") -> Path:
        # as if the repository was cloned by an earlier backup
        repo_dir = Path(self.tmp_path, "github", owner_and_name)
        repo_dir.mkdir(parents=True)
        return repo_dir

    def run(self):
        preferences = MagicMock(backup_directory=str(self.tmp_path), dry_run=False, github_token="test_token")
        pull_branches_kwargs = {"side_effect": self.pull_branches_result} if isinstance(self.pull_branches_result, (Exception, list)) else {"return_value": self.pull_branches_result}
        with (
            patch("bup.github_backup.get_preferences", return_value=preferences),
            patch("bup.github_backup.ExclusionPreferences") as mock_exclusions,
            patch("bup.github_backup.github3.login", return_value=self.login),
            patch("bup.github_backup.shutil.which", return_value=self.git_executable),
            patch("bup.github_backup.time.sleep"),
            patch("bup.github_backup.rmdir", **({} if self.rmdir is None else {"side_effect": self.rmdir})) as mock_rmdir,
            patch("git.Repo.clone_from") as self.clone,
            patch.object(GithubBackup, "pull_branches", **pull_branches_kwargs) as self.pull_branches,
        ):
            if self.rmdir is None:
                from bup.robust_os_calls import rmdir

                mock_rmdir.side_effect = rmdir
            mock_exclusions.return_value.get_no_comments.return_value = self.exclusions
            self.github_backup.run()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_without_git_the_backup_can_not_run(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    run.git_executable = None

    run.run()

    assert github_backup.errors == ["git executable not found in PATH - GitHub backup cannot run"]
    run.clone.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_without_a_login_there_is_nothing_to_back_up(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    run.login = None  # github3.login() without a token

    run.run()

    assert github_backup.warnings == ["could not login to github - check that a github token is set in preferences"]
    assert github_backup.errors == []
    assert "0 repos, 0 pulls, 0 clones, 0 excluded" in github_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_failed_authentication_is_an_error(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    response = MagicMock(status_code=401)
    response.json.return_value = {"message": "Bad credentials"}
    run.login.repositories.side_effect = AuthenticationFailed(response)

    run.run()

    assert github_backup.errors == ["github authentication failed - check the github token in preferences"]
    run.clone.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_request_ends_the_backup_before_the_next_repository(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    github_backup.request_stop()

    run.run()

    run.clone.assert_not_called()
    assert "1 repos, 0 pulls, 0 clones, 0 excluded" in github_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_repositories_are_excluded_by_name_or_by_owner_and_name(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    run.github_repos = [_github_repo("owner/by-name"), _github_repo("owner/by-owner-and-name"), _github_repo("other-owner/by-owner-and-name")]
    run.exclusions = ["by-name", "owner/by-owner-and-name"]

    run.run()

    assert "owner/by-name excluded" in github_backup.infos
    assert "owner/by-owner-and-name excluded" in github_backup.infos
    assert [clone_call.args[0] for clone_call in run.clone.call_args_list] == ["https://github.com/other-owner/by-owner-and-name.git"]  # the same name, of another owner
    assert "3 repos, 0 pulls, 1 clones, 2 excluded" in github_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_repository_that_was_cloned_before_is_pulled(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    repo_dir = run.make_local_repo()

    run.run()

    run.clone.assert_not_called()
    run.pull_branches.assert_called_once()
    assert run.pull_branches.call_args.args[0] == "owner/repo"
    assert run.pull_branches.call_args.args[2] == repo_dir.absolute()
    assert run.pull_branches.call_args.kwargs == {"clone_url": "https://github.com/owner/repo.git"}
    assert "1 repos, 1 pulls, 0 clones, 0 excluded" in github_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_pull_that_raises_is_a_warning_and_the_repository_is_cloned(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    repo_dir = run.make_local_repo()
    (repo_dir / "stale.txt").write_text("from the earlier clone")
    # the pull of the local copy raises, and the pull that follows the clone works
    run.pull_branches_result = [GitCommandError(["git", "fetch"], 128, stderr=b"fatal: test_token was rejected"), True]

    run.run()

    assert len(github_backup.warnings) == 1
    assert github_backup.warnings[0].startswith(f'could not pull "{repo_dir.absolute()}" - will try to start over and do a clone of "owner/repo,')
    assert "test_token" not in github_backup.warnings[0]  # the token is not in the output
    run.clone.assert_called_once()
    assert not (repo_dir / "stale.txt").exists()  # the local copy was removed for the clone
    assert github_backup.errors == []
    assert "1 repos, 0 pulls, 1 clones, 0 excluded" in github_backup.infos


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_local_copy_that_can_not_be_removed_is_an_error_and_is_not_cloned_over(github_backup, tmp_path):
    run = _Run(github_backup, tmp_path)
    repo_dir = run.make_local_repo()
    run.pull_branches_result = False
    run.rmdir = lambda path: False  # e.g. a file of the repository is in use

    run.run()

    assert github_backup.errors == [f'could not remove "{repo_dir.absolute()}" - may require manual removal']
    run.clone.assert_not_called()
    assert "1 repos, 0 pulls, 0 clones, 0 excluded" in github_backup.infos


def _pull_branches(github_backup: GithubBackup, tmp_path: Path, git_repo, branch_names: List[str], clone_url: Optional[str] = None) -> bool:
    """
    Call pull_branches() for a local repository that GitPython opens as git_repo (or fails to open, if it is an exception).
    """
    repo_kwargs = {"side_effect": git_repo} if isinstance(git_repo, Exception) else {"return_value": git_repo}
    with patch("git.Repo", **repo_kwargs):
        return github_backup.pull_branches("owner/repo", [_branch(branch_name) for branch_name in branch_names], tmp_path, clone_url=clone_url)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_local_copy_that_is_not_a_repository_is_a_warning(github_backup, tmp_path):
    assert _pull_branches(github_backup, tmp_path, InvalidGitRepositoryError("not a repository"), ["main"]) is False

    assert len(github_backup.warnings) == 1
    assert github_backup.warnings[0].startswith("InvalidGitRepositoryError: owner/repo,")
    assert github_backup.errors == []


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_remote_url_is_set_to_the_url_without_a_token(github_backup, tmp_path):
    git_repo = MagicMock()

    assert _pull_branches(github_backup, tmp_path, git_repo, ["main"], clone_url="https://github.com/owner/repo.git") is True

    git_repo.remotes.origin.set_url.assert_called_once_with("https://github.com/owner/repo.git")


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_remote_url_that_can_not_be_set_does_not_stop_the_pull(github_backup, tmp_path):
    git_repo = MagicMock()
    git_repo.remotes.origin.set_url.side_effect = GitCommandError(["git", "remote", "set-url"], 1)

    assert _pull_branches(github_backup, tmp_path, git_repo, ["main"], clone_url="https://github.com/owner/repo.git") is True

    assert github_backup.warnings == []  # it only goes to the log
    assert call.reset("--hard", "origin/main") in git_repo.git.mock_calls


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_stop_request_ends_the_pull_before_the_next_branch(github_backup, tmp_path):
    git_repo = MagicMock()
    git_repo.git.checkout.side_effect = lambda branch_name: github_backup.request_stop()  # e.g. Stop is pressed during the first branch

    assert _pull_branches(github_backup, tmp_path, git_repo, ["develop", "feature"]) is True  # the first branch was reset

    assert git_repo.git.checkout.call_args_list == [call("develop")]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_branch_that_can_not_be_reset_is_a_warning_and_ends_the_pull(github_backup, tmp_path):
    git_repo = MagicMock()
    git_repo.git.checkout.side_effect = GitCommandError(["git", "checkout"], 128, stderr=b"fatal: bad object test_token")
    github_backup._github_token = "test_token"

    assert _pull_branches(github_backup, tmp_path, git_repo, ["develop", "feature"]) is False

    assert len(github_backup.warnings) == 1
    assert github_backup.warnings[0].startswith("owner/repo : ")
    assert "test_token" not in github_backup.warnings[0]
    assert github_backup.errors == []  # the caller starts over with a clone
    assert git_repo.git.checkout.call_args_list == [call("develop")]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.parametrize(
    "branch_names,main_branch_name",
    [
        (["feature", "main"], "main"),
        (["master", "feature"], "master"),
        (["master", "main", "feature"], "main"),  # "main" over "master", wherever they are
        (["main", "master"], "main"),
        (["Main", "feature"], "Main"),
    ],
)
def test_repository_is_left_on_its_main_branch(github_backup, tmp_path, branch_names, main_branch_name):
    git_repo = MagicMock()

    assert _pull_branches(github_backup, tmp_path, git_repo, branch_names) is True

    git_repo.git.switch.assert_called_once_with(main_branch_name)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_repository_without_a_main_branch_is_left_on_the_last_branch(github_backup, tmp_path):
    git_repo = MagicMock()

    assert _pull_branches(github_backup, tmp_path, git_repo, ["develop", "feature"]) is True

    git_repo.git.switch.assert_not_called()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_main_branch_that_can_not_be_switched_to_is_a_warning(github_backup, tmp_path):
    git_repo = MagicMock()
    git_repo.git.switch.side_effect = GitCommandError(["git", "switch"], 1)

    assert _pull_branches(github_backup, tmp_path, git_repo, ["feature", "main"]) is True  # the backup itself is done

    assert len(github_backup.warnings) == 1
    assert github_backup.warnings[0].startswith('could not switch "owner/repo" to branch "main" : ')


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_is_excluded():
    assert is_excluded("owner/repo", ["repo"])
    assert is_excluded("owner/repo", ["other", "owner/repo"])
    assert not is_excluded("owner/repo", ["other-owner/repo", "owner", "rep"])
    assert not is_excluded("owner/repo", [])


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_get_main_branch_name():
    assert get_main_branch_name(["feature", "main"]) == "main"
    assert get_main_branch_name(["master", "feature"]) == "master"
    assert get_main_branch_name(["master", "main"]) == "main"
    assert get_main_branch_name(["develop"]) is None
    assert get_main_branch_name([]) is None


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_local_repository_is_left_alone_once_a_branch_can_not_be_reset(github_backup, tmp_path):
    # the caller starts over with a clone, so the other branches are not reset and the main branch is not switched to
    git_repo = MagicMock()
    git_repo.git.checkout.side_effect = [None, GitCommandError(["git", "checkout"], 128, stderr=b"fatal: bad object")]

    assert _pull_branches(github_backup, tmp_path, git_repo, ["main", "broken", "feature"]) is False

    assert git_repo.git.checkout.call_args_list == [call("main"), call("broken")]
    git_repo.git.switch.assert_not_called()
    assert len(github_backup.warnings) == 1
