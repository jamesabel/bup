REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
mkdir temp
rmdir /S /Q .venv
REM --upgrade: the newest version of every dependency (uv.lock is not checked in, so it would otherwise keep old ones)
REM --no-managed-python: the installed Python 3.15 (python.org), not one that uv downloaded
uv sync --upgrade --python 3.15 --no-managed-python
popd
