@echo off
REM Run the configured morning brief through the project's local virtual environment.
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo .venv was not found. Run scripts\setup_windows.bat first.
    exit /b 1
)

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
".venv\Scripts\python.exe" -m futures_intelligence.main morning-brief
