@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set /p PORT=Port: 

if "%PORT%"=="" (
    echo No port specified.
    pause
    exit /b
)

set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING 2^>nul') do (
    set FOUND=1
    for /f "tokens=1" %%b in ('tasklist /FI "PID eq %%a" /NH 2^>nul ^| findstr /V "INFO:"') do (
        echo [%%a] %%b
    )
    taskkill /PID %%a /F >nul 2>&1
    if !errorlevel!==0 (
        echo Killed PID %%a
    ) else (
        echo Failed to kill %%a (try run as Admin)
    )
)

if !FOUND!==0 (
    echo No process listening on port %PORT%
)

pause
