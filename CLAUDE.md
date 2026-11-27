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
- `S3Backup` - Uses awsimple's `S3Access.sync_to_directory()` to sync each bucket to a directory, in the bucket's own region (no AWS CLI; local files are never deleted). Per object outcomes: downloaded/failed/skipped (see README "S3 backup"). With the `s3_verify` preference (`--verify`), every local file is then checked against its S3 object's metadata - size, hash, mtime - by awsimple's `S3Access.verify_directory()`, which is given the sync result; bup only reports its outcomes (`S3Backup.verify_bucket()` runs it and `verification_out()` reports it), and ends the verification when S3 can no longer be reached (`VerifyWatch`, the verification's callback, in `bup/s3_verify.py`). With the `s3_fix_mtime` preference as well (`--fix_mtime`), a local file the verification finds to have the contents of its S3 object but another modification time gets the time of the S3 object (`S3Backup.fix_mtimes()`, `bup/s3_mtime_fix.py`): its hash is compared with the one S3 has, and an object S3 has no hash of is downloaded to a temporary directory in the backup directory (`s3_temp`, so on the backup drive) and compared, and the download is deleted as soon as it has been compared - the local file is never replaced, and one that is not a copy is an error
- `DynamoDBBackup` - Uses awsimple, exports tables to pickle and JSON
- `GithubBackup` - Uses github3.py for API access, GitPython for git operations (clone, then mirror every branch by `fetch --prune` + `reset --hard origin/<branch>` - never `git pull`, so force-pushed/orphan branches never trigger a re-clone). `run_backup()` -> `backup_repo()` -> `pull_repo()` or `clone_repo()`; `pull_branches()` -> `open_repo()`, `fetch()`, `reset_branch()` per branch, `switch_branch()`

**Shared pieces:** look here before writing something a second time. `BupBase` has what every backup does the same way: the output, the stop request, the transfer reporting, the history record, and the counts (`start_counts()`, `count_excluded()`). `get_backup_type_directory()` (`bup/backup_types.py`) is where a backup type's files go in the backup directory. `bup/aws_access.py` gives the S3 and DynamoDB backups their awsimple access arguments from the preferences (`get_aws_access_kwargs()`). `SQLiteStore` (`bup/sqlite_store.py`) is the base of the SQLite databases (`BackupHistory`, `AWSPriceCache`): its `connection()` is for reading and its `transaction()` for writing. `bup/gui/gui_util.py` holds the GUI helpers (`make_row()`, `make_table()`, `set_table_row()`, `to_positive_int()`, `get_local_time_string()`). A new module that logs for a backup type needs an entry in `log_sources_by_filename` (`bup/log_routing.py`), or its records go to the application pane and file. Tests patch `get_preferences` and `ExclusionPreferences` per backup module (e.g. `bup.s3_backup.get_preferences`), so each backup module keeps calling them by its own name.

**Preferences:** SQLite-backed via the `pref` library with `attrs` data classes. CLI and GUI have separate preference stores. Exclusion lists (per backup type) are sanitized by `ExclusionPreferences.get_no_comments()`: `#` starts a comment (whole-line or inline trailing), blank lines are dropped, and entries are whitespace-stripped (see README "Exclusions").

**GUI:** PyQt5 tabbed dialog (`BupDialog`) with `RunBackupWidget`, `PreferencesWidget` (its `PreferencesLineEdit` and `PreferenceCheckBox` widgets are each bound to one preference by name - a new option is one line there; its `CredentialCheckButton`s - "Test S3", "Test DynamoDB", "Test GitHub" - each run a check of `bup/credential_check.py` in a daemon thread and show its `CredentialCheck` in the status line: the check makes the first request of the backup of its type, and a failed check is a warning in the log, not an error), `LogWidget` (detailed application log via a logging handler), `TransferWidget` (bytes received and approximate AWS cost), `HistoryWidget` (the backup history, re-read on the `history_emitter` signal and when the tab is shown), and `BupAbout` tabs, and below the tabs the status line (`BupDialog.status_line`), which a tab writes to through `status_emitter` (`bup/gui/status_line.py`). Once a second `BupDialog.autobackup_tick()` shows when the next automatic backup is, and `start_backup_if_due()` is what decides to start it. A manual stop is acknowledged there ("stopping", then "stopped at") and in the countdown text; `RunBackupWidget.most_recent_backup` (what the automatic backup counts from) is also set by a stopped run so that it is not restarted right away, while only `most_recent_completed_backup` is saved to the preferences.

**Transfer accounting:** `bup/transfer.py` holds `TransferRecord`, the cost math, and the `transfer_emitter` signal. `bup/aws_prices.py` gets each AWS region's prices from the public AWS Price List files and caches them in a SQLite DB (refetched weekly; no user-entered prices; a cache table of an earlier bup, with other columns, is dropped and fetched again) - tests never fetch or touch the real cache (root `conftest.py`). Backups call `BupBase.transfer_out()` per bucket/table/repo that received data; the GUI shows these only in the Transfer tab and the log (not the Backup tab), the CLI prints them (see README "Transfer and approximate AWS cost"). An S3 cost is the data transfer, the S3 requests and the retrieval fee some storage classes have per GB read; awsimple counts the requests by request tier and storage class and the bytes S3 sent by storage class (`S3Access.usage`): `S3Backup.usage_out()` reports and resets the usage of a bucket's access, once after its sync and check and once after its verification (`<bucket> (verification)`), and also for a dry run. A tier 2 request is priced by the storage class of its object, and a tier 1 request (of bup: a listing) has one price.

**Backup history:** `bup/backup_history.py` keeps every backup run in a SQLite DB (`BackupHistory`, one row per backup type per run: start/end, `BackupStatus`, transfer total, error and warning counts, error messages, and `BackupCounts` - the buckets, tables or repos found, backed up and excluded, and for S3 the files in the backup and the files synced). Each backup sets `BupBase.counts` as it goes. A new column of the history table also needs adding to databases that exist (`BackupHistory.__init__` adds the count columns to a 0.17.0 database). `BupBase.run()` records the row when the run starts, updates it at each `transfer_out()` and completes it at the end, so a run that was cut short (crash, kill, power loss) stays on record as running; `BupDialog` calls `mark_interrupted_backups()` at startup, which marks those whose process (pid and process start time, via `psutil`) is gone as interrupted, and shows `get_interrupted_message()` in its status line. A backup that "Stop and Exit" has to terminate is recorded as stopped by `RunBackupWidget.wait_for_threads()`, so it is not taken for a cut-short one. Errors are counted in `BupBase.error_out()`, in the backup's thread (not in `_error_out()`, which in the GUI runs later in the GUI thread). Tests never touch the real history (root `conftest.py`).

## Code Style

- ruff formatter with **192-character line length**
- ruff lint: pycodestyle and pyflakes (`E`, `F`, `W`), ignoring E402, E501 and F401 (`[tool.ruff]` in `pyproject.toml`)
- ty type checks the `bup` package (`[tool.ty]` in `pyproject.toml`). The check passes with nothing reported: fix what it finds, and keep `# ty: ignore[rule]` (with the reason in a comment) for what ty gets wrong
- Runtime type checking via `@typechecked()` decorator from typeguard
- Every module, class, method and function has a docstring, private ones included (reST-style `:param:` / `:return:` where they add something)
- Windows-specific path handling in `robust_os_calls.py` (long paths with `\\?\` prefix, readonly removal, retry logic for filesystem ops)
- Logging via `balsa` library with Sentry integration for error tracking

## Key Dependencies

- `boto3` / `awsimple` - AWS access
- `github3.py` / `GitPython` - GitHub API and git operations
- `PyQt5` - GUI framework (also used for QThread in CLI path)
- `pref` / `sqlitedict` - Persistent preferences
- `psutil` - Whether the process that recorded a backup as running still is (backup history)
- `balsa` - Logging
- `sentry_sdk` - Error tracking
