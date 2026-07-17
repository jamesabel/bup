import base64
from pathlib import Path
import shutil
import time
from typing import Optional

import github3
from github3.exceptions import AuthenticationFailed
from balsa import get_logger
from typeguard import typechecked

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences, rmdir

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


class GithubBackup(BupBase):

    backup_type = BackupTypes.github

    _github_token: Optional[str] = None
    _git_env: dict = {}

    def redact(self, s: str) -> str:
        # keep the token out of the GUI, logs, and Sentry
        if self._github_token:
            s = s.replace(self._github_token, "***")
        return s

    def run(self):
        if shutil.which("git") is None:
            self.error_out("git executable not found in PATH - GitHub backup cannot run")
            return

        from git import Repo
        from git.exc import GitCommandError

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(BackupTypes.github.name).get_no_comments()

        self._github_token = preferences.github_token
        self._git_env = get_git_credential_environment(self._github_token)

        backup_dir = Path(preferences.backup_directory, "github")

        try:
            gh = github3.login(token=preferences.github_token)
            if gh is None:
                log.warning("could not login to github")
                repositories = []
            else:
                repositories = list(gh.repositories())  # this actually throws the authentication error
        except AuthenticationFailed:
            log.error("github authentication failed")
            return

        clone_count = 0
        pull_count = 0

        for github_repo in repositories:
            if self.stop_requested:
                break

            repo_owner_and_name = str(github_repo)
            repo_name = repo_owner_and_name.split("/")[-1]
            if any([e == repo_name or e == repo_owner_and_name for e in exclusions]):
                self.info_out(f"{repo_owner_and_name} excluded")
            elif dry_run:
                self.info_out(f"dry run {repo_owner_and_name}")
            else:
                repo_dir = Path(backup_dir, repo_owner_and_name).absolute()
                branches = list(github_repo.branches())
                clone_url = github_repo.clone_url  # tokenless - credentials go via the environment

                # if we've cloned previously, just do a pull
                pull_success = False
                if repo_dir.exists():
                    try:
                        if pull_success := self.pull_branches(repo_owner_and_name, branches, repo_dir, clone_url=clone_url):
                            pull_count += 1
                    except GitCommandError as e:
                        self.warning_out(self.redact(f'could not pull "{repo_dir}" - will try to start over and do a clone of "{repo_owner_and_name},{e}","{__file__}"'))

                # new to us - clone the repo
                if not pull_success:
                    try:
                        if repo_dir.exists():
                            rmdir(repo_dir)

                        if repo_dir.exists():
                            self.error_out(f'could not remove "{repo_dir}" - may require manual removal')
                        else:
                            self.info_out(f'git clone "{repo_owner_and_name}"')
                            Repo.clone_from(clone_url, repo_dir, env=self._git_env)
                            time.sleep(1.0)  # let Windows release file locks on the fresh clone before touching it
                            self.pull_branches(repo_owner_and_name, branches, repo_dir, clone_url=clone_url)
                            clone_count += 1
                    except PermissionError as e:
                        self.warning_out(self.redact(f'{repo_owner_and_name},"{repo_dir}",{e},"{__file__}"'))
                    except GitCommandError as e:
                        self.warning_out(self.redact(f'{repo_owner_and_name},"{repo_dir}",{e},"{__file__}"'))

        self.info_out(f"{len(repositories)} repos, {pull_count} pulls, {clone_count} clones, {len(exclusions)} excluded")

    @typechecked()
    def pull_branches(self, repo_name: str, branches: list, repo_dir: Path, clone_url: Optional[str] = None) -> bool:
        from git import Repo
        from git.exc import GitCommandError, InvalidGitRepositoryError

        try:
            git_repo = Repo(repo_dir)
        except InvalidGitRepositoryError as e:
            self.error_out(f'InvalidGitRepositoryError: {repo_name},"{repo_dir}",{e},"{__file__}"')
            git_repo = None

        success = False
        main_branch = None
        if git_repo is not None:
            git_repo.git.update_environment(**self._git_env)

            # scrub any token that an older bup version persisted into the remote URL
            if clone_url is not None:
                try:
                    git_repo.remotes.origin.set_url(clone_url)
                except (GitCommandError, AttributeError, ValueError) as e:
                    log.warning(self.redact(f'could not set remote url for "{repo_dir}" : {e}'))

            for branch in branches:
                if self.stop_requested:
                    break
                branch_name = branch.name

                # prefer "main" over "master"
                if branch_name.lower() == "main" or (main_branch is None and branch_name.lower() == "master"):
                    main_branch = branch

                self.info_out(f'git pull "{repo_name}" branch:"{branch_name}"')
                try:
                    git_repo.git.reset("--hard")
                    git_repo.git.clean("-fd")
                    git_repo.git.checkout(branch_name)
                    git_repo.git.pull()
                    success = True
                except GitCommandError as e:
                    if "did not match any file".lower() in str(e).lower():
                        # new branch with no files yet - skip it and continue with other branches
                        self.info_out(f"git pull {repo_name} branch:{branch_name} - no files")
                        continue
                    elif "would be overwritten by checkout" in str(e).lower():
                        # typically caused by CRLF line-ending normalization on Windows, not actual user edits
                        self.warning_out(self.redact(f"{repo_name} branch:{branch_name} : checkout blocked by apparent local changes (likely line-ending normalization) : {e}"))
                        success = False
                        break
                    else:
                        self.error_out(self.redact(f"{repo_name} : {e}"))
                        success = False
                        break

            # if more than one branch, switch to main (or master) branch upon exit
            if len(branches) > 1 and main_branch is not None:
                main_branch_name = main_branch.name
                self.info_out(f'git switch "{repo_name}" branch:"{main_branch_name}"')
                try:
                    git_repo.git.reset("--hard")  # clear any phantom changes (e.g. CRLF normalization) before switching
                    git_repo.git.switch(main_branch_name)
                except GitCommandError as e:
                    # failing to land on the main branch doesn't invalidate the backup itself
                    self.warning_out(self.redact(f'could not switch "{repo_name}" to branch "{main_branch_name}" : {e}'))

        return success
