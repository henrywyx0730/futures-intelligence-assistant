@echo off
REM Create or replace a daily Task Scheduler entry for the morning brief.
REM Usage: scripts\install_daily_task.bat [HH:MM] [TaskName]
REM Example: scripts\install_daily_task.bat 07:30 FuturesIntelligenceMorningBrief
setlocal

set "RUN_TIME=%~1"
if "%RUN_TIME%"=="" set "RUN_TIME=07:00"

set "TASK_NAME=%~2"
if "%TASK_NAME%"=="" set "TASK_NAME=FuturesIntelligenceMorningBrief"

set "LAUNCHER=%~dp0run_morning_brief.bat"
if not exist "%LAUNCHER%" (
    echo Launcher not found: %LAUNCHER%
    exit /b 1
)

REM cmd.exe preserves paths containing spaces when Task Scheduler runs the launcher.
set "TASK_ACTION=%ComSpec% /c call ""%LAUNCHER%"""

schtasks.exe /Create /TN "%TASK_NAME%" /TR "%TASK_ACTION%" /SC DAILY /ST "%RUN_TIME%" /F
if errorlevel 1 exit /b 1

echo Installed daily task "%TASK_NAME%" at %RUN_TIME%.
