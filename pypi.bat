call build.bat
call venv\Scripts\activate.bat
twine upload dist/*
call deactivate
