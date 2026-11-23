REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
REM what is checked (the bup package) and the rules are in pyproject.toml
.venv\Scripts\ty.exe check
popd
