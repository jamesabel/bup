# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bup is a cross-platform backup utility for AWS S3 buckets, AWS DynamoDB tables, and GitHub repositories. It provides both a CLI and a PyQt5-based GUI. Licensed under GPL v3.

## Common Commands

All commands are Windows batch scripts. The virtual environment uses Python 3.13.

```bash
# Create virtual environment
make_venv.bat

# Run tests with coverage
coverage.bat
# Equivalent to: set PYTHONPATH=%CD% && venv\Scripts\pytest.exe --cov-report=html --cov

# Run a single test
venv\Scripts\pytest.exe test_bup\test_preferences.py::test_preferences

# Format code (Black, 192-char line length)
blackify.bat

# Lint
run_flake8.bat

# Build wheel
build.bat

# Run the application
bup.bat                    # GUI (no args)
python -m bup <path> -s    # CLI with S3 backup
```

## Architecture

**Entry point:** `bup/__main__.py` routes to CLI or GUI based on command-line arguments.

**Threading model:** All backup operations inherit from `BupBase` (a `QThread` subclass) and communicate with the UI via Qt signals (`info_out_signal`, `warning_out_signal`, `error_out_signal`). Backups run in separate threads and are joined on completion.

**Three backup implementations:**
- `S3Backup` - Uses awsimple + AWS CLI subprocess for bucket syncing
- `DynamoDBBackup` - Uses awsimple, exports tables to pickle and JSON
- `GithubBackup` - Uses github3.py for API access, GitPython for git operations (clone/pull all branches)

**Preferences:** SQLite-backed via the `pref` library with `attrs` data classes. CLI and GUI have separate preference stores. Exclusion lists (per backup type) support comment lines starting with `#`.

**GUI:** PyQt5 tabbed dialog (`BupDialog`) with `RunBackupWidget`, `PreferencesWidget`, and `BupAbout` tabs.

## Code Style

- Black formatter with **192-character line length**
- flake8 ignores: E402, F401, W503, E203, E501
- Runtime type checking via `@typechecked()` decorator from typeguard
- Windows-specific path handling in `robust_os_calls.py` (long paths with `\\?\` prefix, readonly removal, retry logic for filesystem ops)
- Logging via `balsa` library with Sentry integration for error tracking

## Key Dependencies

- `boto3` / `awsimple` / `awscli` - AWS access
- `github3.py` / `GitPython` - GitHub API and git operations
- `PyQt5` - GUI framework (also used for QThread in CLI path)
- `pref` / `sqlitedict` - Persistent preferences
- `balsa` - Logging
- `sentry_sdk` - Error tracking
