from pathlib import Path
import time

import github3
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
from github3.exceptions import AuthenticationFailed
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
            if any([e == repo_name for e in exclusions]):
                self.info_out(f"{repo_owner_and_name} excluded")
            elif dry_run:
                self.info_out(f"dry run {repo_owner_and_name}")
            else:
                repo_dir = Path(backup_dir, repo_owner_and_name).absolute()
                branches = list(github_repo.branches())

                # if we've cloned previously, just do a pull
                pull_success = False
                if repo_dir.exists():
                    try:
                        if pull_success := self.pull_branches(repo_owner_and_name, branches, repo_dir):
                            pull_count += 1
                    except GitCommandError as e:
                        self.warning_out(f'could not pull "{repo_dir}" - will try to start over and do a clone of "{repo_owner_and_name},{e}","{__file__}"')

                # new to us - clone the repo
                if not pull_success:
                    try:
                        if repo_dir.exists():
                            rmdir(repo_dir)

                        if repo_dir.exists():
                            self.error_out(f'could not remove "{repo_dir}" - may require manual removal')
                        else:
                            self.info_out(f'git clone "{repo_owner_and_name}"')
                            clone_url = github_repo.clone_url
                            if preferences.github_token:
                                clone_url = clone_url.replace("https://", f"https://{preferences.github_token}@")
                            Repo.clone_from(clone_url, repo_dir)
                            time.sleep(1.0)
                            self.pull_branches(repo_owner_and_name, branches, repo_dir)
                            clone_count += 1
                    except PermissionError as e:
                        self.warning_out(f'{repo_owner_and_name},"{repo_dir}",{e},"{__file__}"')
                    except GitCommandError as e:
                        self.warning_out(f'{repo_owner_and_name},"{repo_dir}",{e},"{__file__}"')

        self.info_out(f"{len(repositories)} repos, {pull_count} pulls, {clone_count} clones, {len(exclusions)} excluded")

    @typechecked()
    def pull_branches(self, repo_name: str, branches: list, repo_dir: Path) -> bool:

        try:
            git_repo = Repo(repo_dir)
        except InvalidGitRepositoryError as e:
            self.error_out(f'InvalidGitRepositoryError: {repo_name},"{repo_dir}",{e},"{__file__}"')
            git_repo = None

        success = False
        main_branch = None
        if git_repo is not None:
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
                        self.warning_out(f"{repo_name} branch:{branch_name} : checkout blocked by apparent local changes (likely line-ending normalization) : {e}")
                        success = False
                        break
                    else:
                        self.error_out(f"{repo_name} : {e}")
                        success = False
                        break

            # if more than one branch, switch to main (or master) branch upon exit
            if len(branches) > 1 and main_branch is not None:
                main_branch_name = main_branch.name
                self.info_out(f'git switch "{repo_name}" branch:"{main_branch_name}"')
                git_repo.git.reset("--hard")  # clear any phantom changes (e.g. CRLF normalization) before switching
                git_repo.git.switch(main_branch_name)

        return success
