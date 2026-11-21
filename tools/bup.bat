REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
call venv\Scripts\activate.bat
python -m bup
call deactivate
popd
