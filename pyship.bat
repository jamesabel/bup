rmdir /Q /S app
rmdir /Q /S build
rmdir /Q /S dist
copy LICENSE LICENSE.txt
copy LICENSE bup\LICENSE
call venv\Scripts\activate.bat
call python -m pyship -p bup
REM capture pyship's exit code before deactivate resets errorlevel, so a failed ship (e.g. signing aborted) is reported to the caller
set pyship_exit=%errorlevel%
call deactivate
if not "%pyship_exit%"=="0" (
    echo ERROR: pyship failed with exit code %pyship_exit%
    exit /b %pyship_exit%
)
exit /b 0
