@echo off
cd /d "%~dp0"

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Running setup...
    call Setup_FromSoft_Coop_Manager.bat
    exit /b
)

REM Use pythonw.exe from venv to run without console window
REM The start command with empty title ("") launches in a new process
if exist ".venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0server.py"
) else (
    start "" "%~dp0.venv\Scripts\python.exe" "%~dp0server.py"
) 
