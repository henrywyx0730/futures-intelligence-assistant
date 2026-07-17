@echo off
REM Set up a local Windows virtual environment and install project dependencies.
setlocal

cd /d "%~dp0.."

REM Prefer the Python launcher, with python.exe as a fallback.
py -3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo Python 3 was not found. Install Python 3 and try again.
        exit /b 1
    )
    set "PYTHON_COMMAND=python"
) else (
    set "PYTHON_COMMAND=py -3"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv...
    %PYTHON_COMMAND% -m venv .venv
    if errorlevel 1 exit /b 1
)

echo Installing requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo Setup complete.
