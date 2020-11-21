mkdir temp
rmdir /S /Q venv
"C:\Program Files\Python38\python.exe" -m venv --clear venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip  install -U setuptools
venv\Scripts\python -m pip  install -U -r requirements-dev.txt
