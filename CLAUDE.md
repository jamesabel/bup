# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bup is a cross-platform backup utility for AWS S3 buckets, AWS DynamoDB tables, and GitHub repositories. It provides both a CLI and a PyQt5-based GUI. Licensed under GPL v3.

## Common Commands

All commands are Windows batch scripts in the `tools` directory (except `bup.bat`, which runs the application and is in the project root). Each one changes to the project root itself, so it can be run from anywhere. The project is managed with [uv](https://docs.astral.sh/uv/): the dependencies and the development tools (the `dev` dependency group) are in `pyproject.toml`, and `uv.lock` is not checked in. The virtual environment is `.venv` and uses Python 3.15 (`requires-python` stays at 3.13, the minimum CI tests).

```bash
# Create virtual environment (uv sync, with the newest version of every dependency)
tools\make_venv.bat

# Run tests with coverage
tools\coverage.bat
# Equivalent to: set PYTHONPATH=%CD% && .venv\Scripts\pytest.exe --cov-report=html --cov

# Run a single test
.venv\Scripts\pytest.exe test_bup\test_preferences.py::test_preferences

# Format code (ruff format, 192-char line length)
tools\format.bat

# Lint (ruff check)
tools\run_ruff.bat

# Type check (ty)
tools\run_ty.bat

# Build sdist and wheel (uv build)
tools\build.bat

# Regenerate the README's screen captures (synthetic data, doc/screenshots/*.png) after a GUI change
.venv\Scripts\python.exe tools\make_screenshots.py

# Run the application
tools\bup.bat                  # GUI (no args)
python -m bup <path> -s    # CLI with S3 backup
```

## Architecture

**Entry point:** `bup/__main__.py` routes to CLI or GUI based on command-line arguments.

**Threading model:** All backup operations inherit from `BupBase` (a `QThread` subclass) and communicate with the UI via Qt signals (`info_out_signal`, `warning_out_signal`, `error_out_signal`). Backups run in separate threads and are joined on completion.

**Three backup implementations:**
- `S3Backup` - Uses awsimple's `S3Access.sync_to_directory()` to sync each bucket to a directory, in the bucket's own region (no AWS CLI; local files are never deleted). Per object outcomes: downloaded/failed/skipped (see README "S3 backup"). With the `s3_verify` preference (`--verify`), every local file is then checked against its S3 object's metadata - size, hash, mtime - by awsimple's `S3Access.verify_directory()`, which is given the sync result; bup only reports its outcomes (`S3Backup.verify_bucket()`), and ends the verification when S3 can no longer be reached (`VerifyWatch`, the verification's callback)
- `DynamoDBBackup` - Uses awsimple, exports tables to pickle and JSON
- `GithubBackup` - Uses github3.py for API access, GitPython for git operations (clone, then mirror every branch by `fetch --prune` + `reset --hard origin/<branch>` - never `git pull`, so force-pushed/orphan branches never trigger a re-clone). `run_backup()` -> `backup_repo()` -> `pull_repo()` or `clone_repo()`; `pull_branches()` -> `open_repo()`, `fetch()`, `reset_branch()` per branch, `switch_branch()`

**Shared pieces:** `bup/aws_access.py` gives the S3 and DynamoDB backups their awsimple access arguments from the preferences (`get_aws_access_kwargs()`), and `bup/gui/gui_util.py` holds the GUI helpers (`make_row()`, `to_positive_int()`, `get_local_time_string()`). Tests patch `get_preferences` and `ExclusionPreferences` per backup module (e.g. `bup.s3_backup.get_preferences`), so each backup module keeps calling them by its own name.

**Preferences:** SQLite-backed via the `pref` library with `attrs` data classes. CLI and GUI have separate preference stores. Exclusion lists (per backup type) are sanitized by `ExclusionPreferences.get_no_comments()`: `#` starts a comment (whole-line or inline trailing), blank lines are dropped, and entries are whitespace-stripped (see README "Exclusions").

**GUI:** PyQt5 tabbed dialog (`BupDialog`) with `RunBackupWidget`, `PreferencesWidget` (its `PreferencesLineEdit` and `PreferenceCheckBox` widgets are each bound to one preference by name - a new option is one line there), `LogWidget` (detailed application log via a logging handler), `TransferWidget` (bytes received and approximate AWS cost), and `BupAbout` tabs.

**Transfer accounting:** `bup/transfer.py` holds `TransferRecord`, the cost math, and the `transfer_emitter` signal. `bup/aws_prices.py` gets each AWS region's prices from the public AWS Price List files and caches them in a SQLite DB (refetched weekly; no user-entered prices) - tests never fetch or touch the real cache (root `conftest.py`). Backups call `BupBase.transfer_out()` per bucket/table/repo that received data; the GUI shows these only in the Transfer tab and the log (not the Backup tab), the CLI prints them (see README "Transfer and approximate AWS cost").

## Code Style

- ruff formatter with **192-character line length**
- ruff lint: pycodestyle and pyflakes (`E`, `F`, `W`), ignoring E402, E501 and F401 (`[tool.ruff]` in `pyproject.toml`)
- ty type checks the `bup` package (`[tool.ty]` in `pyproject.toml`). What it found when it was introduced is reported as warnings, which do not fail the check; anything else does. Fix a warning rather than add to them, and remove a rule from the `warn` list once its warnings are gone
- Runtime type checking via `@typechecked()` decorator from typeguard
- Every module, class and public function has a docstring (reST-style `:param:` / `:return:` where they add something)
- Windows-specific path handling in `robust_os_calls.py` (long paths with `\\?\` prefix, readonly removal, retry logic for filesystem ops)
- Logging via `balsa` library with Sentry integration for error tracking

## Key Dependencies

- `boto3` / `awsimple` - AWS access
- `github3.py` / `GitPython` - GitHub API and git operations
- `PyQt5` - GUI framework (also used for QThread in CLI path)
- `pref` / `sqlitedict` - Persistent preferences
- `balsa` - Logging
- `sentry_sdk` - Error tracking
