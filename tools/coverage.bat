REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
set PYTHONPATH=%CD%
.venv\Scripts\pytest.exe --cov-report=html --cov
set PYTHONPATH=
popd
