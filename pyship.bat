copy LICENSE LICENSE.txt
copy LICENSE bup\LICENSE
call venv\Scripts\activate.bat
call python -m pyship -p bup
deactivate
