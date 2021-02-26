call build.bat
rmdir /S /Q app
rmdir /S /Q installers
call venv\Scripts\activate.bat
python -m pyship -p default
deactivate
