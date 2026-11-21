REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
call venv\Scripts\activate.bat
python -m black -l 192 bup test_bup
call deactivate
popd
