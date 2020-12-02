import json
from functools import lru_cache
from typing import Iterable
from pathlib import Path
import shutil

import github3
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
import appdirs
from pressenter2exit import PressEnter2ExitGUI
from balsa import get_logger

from bup import __application_name__, __author__, print_log, BupBase

log = get_logger(__application_name__)


# just instantiate once
@lru_cache()
def get_press_enter_to_exit() -> PressEnter2ExitGUI:
    return PressEnter2ExitGUI(title="github local backup")


def get_github_auth():

    token_string = "token"

    credentials_dir = Path(appdirs.user_config_dir(__application_name__, __author__))
    credentials_dir.mkdir(parents=True, exist_ok=True)
    credentials_file_path = Path(credentials_dir, "github_credentials.json")

    if not credentials_file_path.exists():
        token = input("github token:").strip()
        credentials_file_path.write_text(json.dumps({token_string: token}, indent=4))

    credentials = json.loads(credentials_file_path.read_text())
    token = credentials.get(token_string)
    assert token is not None and len(token) > 0
    gh = github3.login(token=token)

    return gh


def pull_branches(repo_name: str, branches: Iterable, repo_dir: str):

    git_repo = None
    try:
        git_repo = Repo(repo_dir)
    except InvalidGitRepositoryError as e:
        log.error(f"InvalidGitRepositoryError: {repo_name} , {repo_dir} , {e}")

    if git_repo is not None:
        for branch in branches:

            if not get_press_enter_to_exit().is_alive():
                break

            branch_name = branch.application_name
            print_log(f'git pull "{repo_name}" branch:"{branch_name}" to {repo_dir}')
            git_repo.git.checkout(branch_name)
            git_repo.git.pull()


class GithubBackup(BupBase):

    def github_local_backup(self):

        backup_dir = Path(self.backup_directory, "github")

        gh = get_github_auth()
        for github_repo in gh.repositories():

            if not get_press_enter_to_exit().is_alive():
                break

            repo_name = str(github_repo)
            repo_dir = Path(backup_dir, repo_name).absolute()
            branches = github_repo.branches()

            # if we've cloned previously, just do a pull
            pull_success = False
            if repo_dir.exists():
                try:
                    pull_branches(repo_name, branches, repo_dir)
                    pull_success = True
                except GitCommandError as e:
                    log.info(e)
                    print_log(f'could not pull "{repo_dir}" - will try to start over and do a clone of "{repo_name}"')

            # new to us - clone the repo
            if not pull_success:
                try:
                    if repo_dir.exists():
                        shutil.rmtree(repo_dir)

                    print_log(f'git clone "{repo_name}" to "{repo_dir}"')

                    Repo.clone_from(github_repo.clone_url, repo_dir)
                    pull_branches(repo_name, branches, repo_dir)
                except PermissionError as e:
                    log.warning(f"{repo_name} : {e}")
