@echo off
rem Closes Claude pet (he waves goodbye first)
if not exist "%~dp0pet.pid" (
    echo Pet is not running.
    exit /b
)
set /p PID=<"%~dp0pet.pid"
taskkill /pid %PID% >nul 2>&1 || taskkill /f /pid %PID% >nul 2>&1
