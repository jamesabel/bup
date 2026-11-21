REM run from the project root, regardless of where this script is called from
pushd "%~dp0.."
mkdir temp
rmdir /S /Q venv
"C:\Program Files\Python315\python.exe" -m venv --clear venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -U setuptools
venv\Scripts\python -m pip install -U -e .[dev]
popd
