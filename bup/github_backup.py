"""
The GitHub backup: every repository the token can see is cloned to <backup directory>/github/<owner>/<repo>, and from then on
every branch is kept an exact mirror of the remote (fetch and hard reset - never a merge).

GitPython is imported where it is used and not at the top of this module: importing it fails if there is no git executable, which
run_backup() checks for (and reports) first.
"""

import base64
from enum import Enum
from pathlib import Path
import shutil
import time
from typing import List, Optional

import github3
from github3.exceptions import AuthenticationFailed, GitHubError, TransportError
from balsa import get_logger
from typeguard import typechecked

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences, rmdir
from bup.transfer import TransferRecord

log = get_logger(__application_name__)


def get_git_credential_environment(token: Optional[str]) -> dict:
    """
    Environment that lets git authenticate to GitHub without ever putting the token in a URL
    (URLs get persisted to .git/config and echoed back in git error messages).
    Uses git's GIT_CONFIG_* environment configs (git >= 2.31).
    """
    env = {"GIT_TERMINAL_PROMPT": "0"}  # fail instead of prompting for credentials
    if token:
        basic_auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {basic_auth}"
    return env


def parse_count_objects(count_objects_output: str) -> Optional[int]:
    """
    Size (bytes) of a git repository's object store, from the output of "git count-objects -v" (which reports loose objects as "size"
    and packed objects as "size-pack", both in KiB).
    :return: the size, or None if the output doesn't have both sizes
    """
    sizes = {}
    for line in count_objects_output.splitlines():
        key, separator, value = line.partition(":")
        if separator and value.strip().isdigit():
            sizes[key.strip()] = int(value)
    if "size" not in sizes or "size-pack" not in sizes:
        return None
    return (sizes["size"] + sizes["size-pack"]) * 1024


def is_excluded(repo_owner_and_name: str, exclusions: List[str]) -> bool:
    """
    :param repo_owner_and_name: a repository, as owner/name
    :param exclusions: the exclusion list, whose entries are each a repository name (of any owner) or an owner/name
    :return: True if the repository is not to be backed up
    """
    repo_name = repo_owner_and_name.split("/")[-1]
    return any(exclusion in (repo_name, repo_owner_and_name) for exclusion in exclusions)


def get_main_branch_name(branch_names: List[str]) -> Optional[str]:
    """
    The branch a local repository is left on: "main" if there is one, otherwise "master" (in any case).

    :param branch_names: the names of the branches of a repository
    :return: the name of the main branch, or None if no branch is named "main" or "master"
    """
    for main_name in ("main", "master"):
        # the last "main", but the first "master" (which only matters for a repository with e.g. both "main" and "Main")
        candidates = [branch_name for branch_name in branch_names if branch_name.lower() == main_name]
        if candidates:
            return candidates[-1] if main_name == "main" else candidates[0]
    return None


class RepoOutcomes(Enum):
    """
    What the backup did with a repository.
    """

    pulled = "pulled"  # the local repository was brought up to date
    cloned = "cloned"  # there was no local repository, or it could not be brought up to date, so the repository was cloned
    failed = "failed"  # the repository was not backed up (which has been reported as an error)


class BranchOutcomes(Enum):
    """
    What resetting a branch of a local repository to its remote did.
    """

    reset = "reset"  # the branch is a mirror of the remote
    no_files = "no files"  # a new branch that has no files yet, which is skipped
    failed = "failed"  # the branch could not be reset (which has been reported as a warning: the caller starts over with a clone)


class GithubBackup(BupBase):
    """
    Backs up every GitHub repository the token can see (other than the excluded ones) to <backup directory>/github.
    """

    backup_type = BackupTypes.github

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._github_token: Optional[str] = None
        self._git_env: dict = {}

    def redact(self, s: str) -> str:
        """
        Take the GitHub token out of text (e.g. a git error message) that goes to the GUI, the logs or Sentry.
        """
        if self._github_token:
            s = s.replace(self._github_token, "***")
        return s

    # ----------------------------------------------------------------------------------------------------------------------------
    # what a clone or fetch received
    # ----------------------------------------------------------------------------------------------------------------------------

    def get_repo_size(self, git_repo) -> Optional[int]:
        """
        Size (bytes) of a local repository's object store, or None if it can't be determined.
        """
        from git.exc import GitCommandError

        try:
            return parse_count_objects(git_repo.git.count_objects("-v"))
        except GitCommandError as e:
            # the size is only used to report how much a clone or fetch received - not knowing it doesn't affect the backup
            log.warning(self.redact(f"could not get the repository size : {e}"))
            return None

    def report_received(self, repo_name: str, size_before: Optional[int], size_after: Optional[int]):
        """
        Report what a clone or fetch received, as the growth of the local object store. This is approximate (git stores what it
        receives compressed, and may repack after a fetch), and GitHub does not charge for it - it is informational.
        """
        if size_before is not None and size_after is not None and size_after > size_before:
            self.transfer_out(TransferRecord(BackupTypes.github, repo_name, size_after - size_before))

    # ----------------------------------------------------------------------------------------------------------------------------
    # the backup of every repository
    # ----------------------------------------------------------------------------------------------------------------------------

    def get_repositories(self, token: Optional[str]) -> Optional[list]:
        """
        Get the repositories the token can see.

        :return: the repositories (github3 repository objects). None if they could not be listed (the token was not accepted, GitHub
          could not be reached, or GitHub refused), which is reported as an error. Without a login at all (e.g. no token is set)
          there are none, which is reported as a warning.
        """
        try:
            gh = github3.login(token=token)
            if gh is None:
                self.warning_out("could not login to github - check that a github token is set in preferences")
                return []
            return list(gh.repositories())  # the first request to GitHub, so this is what raises
        except AuthenticationFailed:
            self.error_out("github authentication failed - check the github token in preferences")
        except TransportError as e:
            # no response from GitHub at all, e.g. no internet connectivity
            self.error_out(self.redact(f"could not reach github - check connectivity : {e}"))
        except GitHubError as e:
            # a response that is not the repositories, e.g. the rate limit is exceeded or GitHub has a server error
            self.error_out(self.redact(f"could not list the github repositories : {e}"))
        return None

    def run_backup(self):
        """
        Back up every repository: fetch and reset the local copy if there is one, and clone if there is none or the local copy can
        not be brought up to date. A failure of one repository does not end the backup of the others.
        """
        if shutil.which("git") is None:
            self.error_out("git executable not found in PATH - GitHub backup cannot run")
            return

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(BackupTypes.github.name).get_no_comments()

        self._github_token = preferences.github_token
        self._git_env = get_git_credential_environment(self._github_token)

        backup_dir = Path(preferences.backup_directory, "github")

        if (repositories := self.get_repositories(preferences.github_token)) is None:
            return

        outcome_counts = {repo_outcome: 0 for repo_outcome in RepoOutcomes}
        for github_repo in repositories:
            if self.stop_requested:
                break

            repo_owner_and_name = str(github_repo)
            if is_excluded(repo_owner_and_name, exclusions):
                self.info_out(f"{repo_owner_and_name} excluded")
            elif dry_run:
                self.info_out(f"dry run {repo_owner_and_name}")
            else:
                outcome_counts[self.backup_repo(github_repo, backup_dir)] += 1

        self.info_out(f"{len(repositories)} repos, {outcome_counts[RepoOutcomes.pulled]} pulls, {outcome_counts[RepoOutcomes.cloned]} clones, {len(exclusions)} excluded")
        if not dry_run:
            self.transfer_summary_out()

    # ----------------------------------------------------------------------------------------------------------------------------
    # the backup of one repository
    # ----------------------------------------------------------------------------------------------------------------------------

    def backup_repo(self, github_repo, backup_dir: Path) -> RepoOutcomes:
        """
        Back up one repository: if it was cloned before, bring the local repository up to date. If it is new, or the local repository
        can not be brought up to date (e.g. a corrupt local clone), clone it.

        :param github_repo: the repository on GitHub (a github3 repository object)
        :param backup_dir: the directory of the GitHub backup
        :return: what was done
        """
        repo_owner_and_name = str(github_repo)
        repo_dir = Path(backup_dir, repo_owner_and_name).absolute()
        try:
            branches = list(github_repo.branches())  # a request to GitHub
        except (TransportError, GitHubError) as e:
            # e.g. connectivity was lost part way through the backup
            self.error_out(self.redact(f"could not list the branches of {repo_owner_and_name} : {e}"))
            return RepoOutcomes.failed
        clone_url = github_repo.clone_url  # tokenless - credentials go via the environment

        if repo_dir.exists() and self.pull_repo(repo_owner_and_name, branches, repo_dir, clone_url):
            return RepoOutcomes.pulled
        if self.clone_repo(repo_owner_and_name, branches, repo_dir, clone_url):
            return RepoOutcomes.cloned
        return RepoOutcomes.failed

    def pull_repo(self, repo_owner_and_name: str, branches: list, repo_dir: Path, clone_url: str) -> bool:
        """
        Bring a local repository up to date with pull_branches(). A failure is a warning, not an error: the caller starts over with a
        clone.

        :return: True if the local repository is up to date
        """
        from git.exc import GitCommandError

        try:
            return self.pull_branches(repo_owner_and_name, branches, repo_dir, clone_url=clone_url)
        except GitCommandError as e:
            self.warning_out(self.redact(f'could not pull "{repo_dir}" - will try to start over and do a clone of "{repo_owner_and_name},{e}","{__file__}"'))
            return False

    def clone_repo(self, repo_owner_and_name: str, branches: list, repo_dir: Path, clone_url: str) -> bool:
        """
        Clone a repository, in place of the local repository if there is one, and make every branch a mirror of the remote. The
        clone is the last resort, so a failure is an error: the repository was not backed up.

        :return: True if the repository was cloned
        """
        from git import Repo
        from git.exc import GitCommandError

        try:
            if repo_dir.exists():
                rmdir(repo_dir)
            if repo_dir.exists():
                self.error_out(f'could not remove "{repo_dir}" - may require manual removal')
                return False

            self.info_out(f'git clone "{repo_owner_and_name}"')
            cloned_repo = Repo.clone_from(clone_url, repo_dir, env=self._git_env)
            self.report_received(repo_owner_and_name, 0, self.get_repo_size(cloned_repo))
            cloned_repo.close()
            time.sleep(1.0)  # let Windows release file locks on the fresh clone before touching it
            self.pull_branches(repo_owner_and_name, branches, repo_dir, clone_url=clone_url)
            return True
        except (PermissionError, GitCommandError) as e:
            self.error_out(self.redact(f'{repo_owner_and_name},"{repo_dir}",{e},"{__file__}"'))
            return False

    # ----------------------------------------------------------------------------------------------------------------------------
    # making a local repository a mirror of the remote
    # ----------------------------------------------------------------------------------------------------------------------------

    def open_repo(self, repo_name: str, repo_dir: Path):
        """
        Open a local repository, with the environment that authenticates git to GitHub.

        :return: the repository (a GitPython Repo), or None if the directory is not a git repository (which is reported as a warning)
        """
        from git import Repo
        from git.exc import InvalidGitRepositoryError

        try:
            git_repo = Repo(repo_dir)
        except InvalidGitRepositoryError as e:
            # recoverable - the caller falls back to removing the local copy and doing a fresh clone
            self.warning_out(f'InvalidGitRepositoryError: {repo_name},"{repo_dir}",{e},"{__file__}"')
            return None
        git_repo.git.update_environment(**self._git_env)
        return git_repo

    def set_remote_url(self, git_repo, repo_dir: Path, clone_url: str):
        """
        Set the URL of a local repository's remote to the URL without a token, which scrubs any token that an older bup version
        persisted into it. A failure only goes to the log: the backup does not depend on it.
        """
        from git.exc import GitCommandError

        try:
            git_repo.remotes.origin.set_url(clone_url)
        except (GitCommandError, AttributeError, ValueError) as e:
            log.warning(self.redact(f'could not set remote url for "{repo_dir}" : {e}'))

    def fetch(self, repo_name: str, git_repo) -> bool:
        """
        Fetch everything from the remote of a local repository, and report what that received.

        A backup is a mirror: the goal is "local == remote, exactly", never to integrate histories. So a local repository is brought
        up to date with a fetch and a hard reset of each branch to its remote-tracking ref (the model git itself uses for mirrors),
        not "git pull" - a merge would fail on any force-pushed branch (rebased feature branches, CI-owned branches such as gh-pages
        or badges, orphan branches) and trigger a needless full re-clone. One fetch per repo transfers every branch's objects in a
        single negotiation; --prune drops remote-tracking refs for branches deleted on GitHub so the local ref set stays honest.

        :return: True if the fetch worked. A failure is reported as a warning: it is recoverable, since the caller falls back to a
          fresh clone (and escalates to an error if that also fails).
        """
        from git.exc import GitCommandError

        self.info_out(f'git fetch "{repo_name}"')
        size_before_fetch = self.get_repo_size(git_repo)
        try:
            git_repo.git.fetch("--prune", "origin")
        except GitCommandError as e:
            self.warning_out(self.redact(f"{repo_name} : {e}"))
            return False
        self.report_received(repo_name, size_before_fetch, self.get_repo_size(git_repo))
        return True

    def reset_branch(self, repo_name: str, git_repo, branch_name: str) -> BranchOutcomes:
        """
        Make one branch of a local repository (that has been fetched) an exact mirror of the remote branch.

        :return: what was done
        """
        from git.exc import GitCommandError

        self.info_out(f'git reset "{repo_name}" branch:"{branch_name}"')
        try:
            git_repo.git.reset("--hard")
            git_repo.git.clean("-fd")
            git_repo.git.checkout(branch_name)  # creates a local tracking branch from origin/<name> on first sight
            git_repo.git.reset("--hard", f"origin/{branch_name}")
            git_repo.git.clean("-fd")
        except GitCommandError as e:
            if "did not match any file".lower() in str(e).lower():
                # new branch with no files yet - skip it and continue with other branches
                self.info_out(f"git reset {repo_name} branch:{branch_name} - no files")
                return BranchOutcomes.no_files
            if "would be overwritten by checkout" in str(e).lower():
                # typically caused by CRLF line-ending normalization on Windows, not actual user edits
                self.warning_out(self.redact(f"{repo_name} branch:{branch_name} : checkout blocked by apparent local changes (likely line-ending normalization) : {e}"))
            else:
                # recoverable (e.g. a corrupt object store) - the caller falls back to a fresh clone, and escalates to an error if that also fails
                self.warning_out(self.redact(f"{repo_name} : {e}"))
            return BranchOutcomes.failed
        return BranchOutcomes.reset

    def switch_branch(self, repo_name: str, git_repo, branch_name: str):
        """
        Leave a local repository on a branch. A failure is a warning: it does not invalidate the backup itself.
        """
        from git.exc import GitCommandError

        self.info_out(f'git switch "{repo_name}" branch:"{branch_name}"')
        try:
            git_repo.git.reset("--hard")  # clear any phantom changes (e.g. CRLF normalization) before switching
            git_repo.git.switch(branch_name)
        except GitCommandError as e:
            self.warning_out(self.redact(f'could not switch "{repo_name}" to branch "{branch_name}" : {e}'))

    @typechecked()
    def pull_branches(self, repo_name: str, branches: list, repo_dir: Path, clone_url: Optional[str] = None) -> bool:
        """
        Make every branch of a local repository an exact mirror of the remote: one fetch, then a hard reset of each branch to its
        remote-tracking ref. It is not a "git pull" (see fetch()). A repository with more than one branch is left on its main branch.

        :param repo_name: the repository, as owner/name (for the output)
        :param branches: the branches of the repository on GitHub (github3 branch objects)
        :param repo_dir: the local repository
        :param clone_url: the URL of the repository without a token, which the remote is set to
        :return: True if at least one branch was reset to its remote and none failed. On False the caller falls back to a fresh clone.
        """
        if (git_repo := self.open_repo(repo_name, repo_dir)) is None:
            return False
        if clone_url is not None:
            self.set_remote_url(git_repo, repo_dir, clone_url)
        if not self.fetch(repo_name, git_repo):
            return False

        success = False
        for branch in branches:
            if self.stop_requested:
                break
            branch_outcome = self.reset_branch(repo_name, git_repo, branch.name)
            if branch_outcome is BranchOutcomes.failed:
                return False  # the caller starts over with a clone, so there is nothing more to do with this local repository
            if branch_outcome is BranchOutcomes.reset:
                success = True

        # if more than one branch, switch to main (or master) branch upon exit
        if len(branches) > 1 and (main_branch_name := get_main_branch_name([branch.name for branch in branches])) is not None:
            self.switch_branch(repo_name, git_repo, main_branch_name)

        return success
