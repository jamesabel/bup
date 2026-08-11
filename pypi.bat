setlocal

call build.bat

if not exist dist\*.whl (
    echo ERROR: build failed - no wheel found in dist
    exit /b 1
)

call venv\Scripts\activate.bat

twine check --strict dist/*
if errorlevel 1 (
    echo ERROR: twine check failed - not uploading
    call deactivate
    exit /b 1
)

twine upload dist/*
if errorlevel 1 (
    echo ERROR: twine upload failed
    call deactivate
    exit /b 1
)

call deactivate
exit /b 0
