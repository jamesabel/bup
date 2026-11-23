REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
REM the line length (192) is in pyproject.toml
.venv\Scripts\ruff.exe format bup test_bup tools conftest.py
popd
