rmdir /Q /S app
rmdir /Q /S build
rmdir /Q /S dist
copy LICENSE LICENSE.txt
copy LICENSE bup\LICENSE
call venv\Scripts\activate.bat
call python -m pyship -p bup
deactivate