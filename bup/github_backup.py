from typing import Iterable
from pathlib import Path
import shutil
from typing import Callable

import github3
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
from balsa import get_logger

from bup import __application_name__, BupBase, BackupTypes, get_preferences, ExclusionPreferences

log = get_logger(__application_name__)


def pull_branches(repo_name: str, branches: Iterable, repo_dir: str, log_function: Callable):

    git_repo = None
    try:
        git_repo = Repo(repo_dir)
    except InvalidGitRepositoryError as e:
        log.error(f"InvalidGitRepositoryError: {repo_name} , {repo_dir} , {e}")

    if git_repo is not None:
        for branch in branches:
            branch_name = branch.name
            log_function(f'git pull "{repo_name}" branch:"{branch_name}"')
            git_repo.git.checkout(branch_name)
            git_repo.git.pull()


class GithubBackup(BupBase):

    backup_type = BackupTypes.github

    def run(self):

        preferences = get_preferences()
        exclusions = ExclusionPreferences(BackupTypes.github.name).get()

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
            else:
                repo_dir = Path(backup_dir, repo_owner_and_name).absolute()
                branches = github_repo.branches()

                # if we've cloned previously, just do a pull
                pull_success = False
                if repo_dir.exists():
                    try:
                        pull_branches(repo_owner_and_name, branches, repo_dir, self.info_out)
                        pull_success = True
                        pull_count += 1
                    except GitCommandError as e:
                        self.warning_out(f'could not pull "{repo_dir}" - will try to start over and do a clone of "{repo_owner_and_name}"')

                # new to us - clone the repo
                if not pull_success:
                    try:
                        if repo_dir.exists():
                            shutil.rmtree(repo_dir)

                        self.info_out(f'git clone "{repo_owner_and_name}"')

                        Repo.clone_from(github_repo.clone_url, repo_dir)
                        pull_branches(repo_owner_and_name, branches, repo_dir, self.info_out)
                        clone_count += 1
                    except PermissionError as e:
                        log.warning(f"{repo_owner_and_name} : {e}")

        self.info_out(f"{len(repositories)} repos, {pull_count} pulls, {clone_count} clones, {len(exclusions)} excluded")
