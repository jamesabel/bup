copy LICENSE LICENSE.txt
copy LICENSE bup\LICENSE
call build.bat
rmdir /S /Q app
rmdir /S /Q installers
call venv\Scripts\activate.bat
call python -m pyship -p bup
deactivate
