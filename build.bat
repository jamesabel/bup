rmdir /S /Q bup.egg-info
rmdir /S /Q build
rmdir /S /Q dist
copy /Y LICENSE LICENSE.txt
call venv\Scripts\activate.bat
python.exe setup.py bdist_wheel
rmdir /S /Q bup.egg-info
rmdir /S /Q build
call deactivate
