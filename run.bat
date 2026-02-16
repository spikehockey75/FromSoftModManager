@echo off
title FromSoft Co-op Settings Manager

cd /d "%~dp0"

REM ─── Check if installed ─────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo  First time? Running installer...
    echo.
    call install.bat
    exit /b
)

REM ─── Activate virtual environment ───────────────────────────────
call .venv\Scripts\activate.bat

REM ─── Start the app ──────────────────────────────────────────────
REM Use pythonw (no console window) when available, fall back to python
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw server.py
) else (
    python server.py
)
