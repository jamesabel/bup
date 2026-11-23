REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
REM the rules that are checked and ignored are in pyproject.toml
venv\Scripts\ruff.exe check bup test_bup tools conftest.py
popd
