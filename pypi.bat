setlocal

REM use %~dp0 so the sibling scripts are found no matter how this script is invoked
REM (a bare "call build.bat" can fail to resolve in some shells, and the stale
REM contents of dist would then get uploaded)
call "%~dp0build.bat"
if errorlevel 1 (
    echo ERROR: build.bat failed - not uploading
    exit /b 1
)

REM determine the current version so a stale wheel in dist can't satisfy the check below
set version=
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"__version__" "%~dp0bup\__version__.py"') do set version=%%v
set version=%version: =%
set version=%version:"=%
if "%version%"=="" (
    echo ERROR: could not determine the version from bup\__version__.py - not uploading
    exit /b 1
)

if not exist "%~dp0dist\bup-%version%-*.whl" (
    echo ERROR: build failed - no bup-%version% wheel found in dist
    exit /b 1
)

call "%~dp0venv\Scripts\activate.bat"

twine check --strict "%~dp0dist/*"
if errorlevel 1 (
    echo ERROR: twine check failed - not uploading
    call deactivate
    exit /b 1
)

twine upload "%~dp0dist/*"
if errorlevel 1 (
    echo ERROR: twine upload failed
    call deactivate
    exit /b 1
)

call deactivate
exit /b 0
