@echo off
setlocal
set "APP_DIR=%~dp0Main App"

if not exist "%APP_DIR%\.venv\Scripts\python.exe" (
    echo Virtual environment not found: "%APP_DIR%\.venv"
    pause
    exit /b 1
)

pushd "%APP_DIR%"
"%APP_DIR%\.venv\Scripts\python.exe" -m streamlit run main.py
set "APP_EXIT=%ERRORLEVEL%"
popd
exit /b %APP_EXIT%
