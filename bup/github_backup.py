from typing import Iterable
from pathlib import Path
import time

import github3
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
from balsa import get_logger
from typeguard import typechecked

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences, rmdir

log = get_logger(__application_name__)


class GithubBackup(BupBase):

    backup_type = BackupTypes.github

    def run(self):

        preferences = get_preferences(self.ui_type)
        dry_run = preferences.dry_run
        exclusions = ExclusionPreferences(BackupTypes.github.name).get_no_comments()

        backup_dir = Path(preferences.backup_directory, "github")
        gh = github3.login(token=preferences.github_token)
        repositories = list(gh.repositories())

        clone_count = 0
        pull_count = 0

        for github_repo in repositories:

            repo_owner_and_name = str(github_repo)
            repo_name = repo_owner_and_name.split("/")[-1]
            if any([e == repo_name for e in exclusions]):
                self.info_out(f"{repo_owner_and_name} excluded")
            elif dry_run:
                self.info_out(f'dry run {repo_owner_and_name}')
            else:
                repo_dir = Path(backup_dir, repo_owner_and_name).absolute()
                branches = github_repo.branches()

                # if we've cloned previously, just do a pull
                pull_success = False
                if repo_dir.exists():
                    try:
                        if pull_success := self.pull_branches(repo_owner_and_name, branches, repo_dir):
                            pull_count += 1
                    except GitCommandError as e:
                        self.warning_out(f'could not pull "{repo_dir}" - will try to start over and do a clone of "{repo_owner_and_name} {e}"')

                # new to us - clone the repo
                if not pull_success:
                    try:
                        if repo_dir.exists():
                            rmdir(repo_dir)

                        self.info_out(f'git clone "{repo_owner_and_name}"')

                        Repo.clone_from(github_repo.clone_url, repo_dir)
                        time.sleep(1.0)
                        self.pull_branches(repo_owner_and_name, branches, repo_dir)
                        clone_count += 1
                    except PermissionError as e:
                        self.warning_out(f"{repo_owner_and_name} : {e}")

        self.info_out(f"{len(repositories)} repos, {pull_count} pulls, {clone_count} clones, {len(exclusions)} excluded")

    @typechecked()
    def pull_branches(self, repo_name: str, branches: Iterable, repo_dir: Path) -> bool:

        try:
            git_repo = Repo(repo_dir)
        except InvalidGitRepositoryError as e:
            self.error_out(f"InvalidGitRepositoryError: {repo_name} , {repo_dir} , {e}")
            git_repo = None

        success = False
        if git_repo is not None:
            for branch in branches:
                branch_name = branch.name
                self.info_out(f'git pull "{repo_name}" branch:"{branch_name}"')
                try:
                    git_repo.git.checkout(branch_name)
                    git_repo.git.pull()
                    success = True
                except GitCommandError as e:
                    self.error_out(f"{repo_name} : {e}")
                    success = False
                    break

        return success
