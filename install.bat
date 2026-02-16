@echo off
setlocal enabledelayedexpansion
title FromSoft Co-op Settings Manager - Installer
color 0B

echo.
echo  +==============================================================+
echo  :                                                              :
echo  :      FromSoft Co-op Settings Manager - Installer             :
echo  :                                                              :
echo  :   This will set up everything you need automatically.        :
echo  :                                                              :
echo  +==============================================================+
echo.

cd /d "%~dp0"

REM --- Step 1: Check for Python -----------------------------------
echo  [1/5] Checking for Python...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  Python is NOT installed. Attempting to install automatically...
    echo.

    REM Try winget first (built into Windows 10 1709+ and Windows 11)
    winget --version >nul 2>&1
    if !errorlevel!==0 (
        echo  Installing Python via winget...
        echo.
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        if !errorlevel! neq 0 (
            echo.
            echo  [ERROR] winget install failed. Trying direct download...
            goto :try_curl
        )
        goto :python_installed
    )

    :try_curl
    REM Fallback: download the installer with curl (built into Windows 10 1709+)
    echo  Downloading Python installer...
    echo.
    set "PY_INSTALLER=%TEMP%\python-installer.exe"
    curl -L -o "!PY_INSTALLER!" "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    if !errorlevel! neq 0 (
        echo.
        echo  [ERROR] Could not download Python installer.
        echo          Please install Python manually from https://www.python.org/downloads/
        echo          Make sure to check "Add python.exe to PATH" during install.
        pause
        exit /b 1
    )

    echo  Running Python installer silently...
    echo  This may take a minute...
    echo.
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    if !errorlevel! neq 0 (
        echo.
        echo  [ERROR] Python installer failed.
        echo          Please install Python manually from https://www.python.org/downloads/
        echo          Make sure to check "Add python.exe to PATH" during install.
        pause
        exit /b 1
    )
    del "!PY_INSTALLER!" >nul 2>&1

    :python_installed
    echo.
    echo  Python installed successfully. Refreshing environment...
    echo.

    REM Refresh PATH so we can find python in this session
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
    for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
    set "PATH=!USER_PATH!;!SYS_PATH!"

    python --version >nul 2>&1
    if errorlevel 1 (
        echo  [ERROR] Python was installed but cannot be found in PATH.
        echo          Please close this window, open a NEW command prompt,
        echo          and run install.bat again.
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo         Found: %PYVER%
echo.

REM --- Step 2: Create virtual environment -------------------------
echo  [2/5] Setting up virtual environment...
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo        Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        echo          Try running: python -m venv .venv
        pause
        exit /b 1
    )
    echo        Virtual environment created.
) else (
    echo        Virtual environment already exists.
)
echo.

REM --- Step 3: Install dependencies -------------------------------
echo  [3/5] Installing dependencies...
echo.

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
set "REQ_FILE=%~dp0requirements.txt"
if exist "%REQ_FILE%" (
    python -m pip install -r "%REQ_FILE%"
) else (
    echo        requirements.txt not found. Installing base dependencies...
    python -m pip install flask Pillow
)
if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo.

REM --- Step 4: Convert icon PNG -> ICO ----------------------------
echo  [4/5] Preparing application icon...
echo.

set "ICON_PNG=%~dp0FSSIcon.png"
set "ICON_ICO=%~dp0FSSIcon.ico"

if exist "%ICON_PNG%" (
    if not exist "%ICON_ICO%" (
        echo        Converting icon to .ico format...
        python -c "from PIL import Image; img = Image.open(r'%ICON_PNG%'); img.save(r'%ICON_ICO%', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
        if exist "%ICON_ICO%" (
            echo        Icon converted successfully.
        ) else (
            echo        Icon conversion failed ^(not critical^).
        )
    ) else (
        echo        Icon already exists.
    )
) else (
    echo        No FSSIcon.png found, skipping icon setup.
)
echo.

REM --- Step 5: Create desktop shortcut ----------------------------
echo  [5/5] Creating desktop shortcut...
echo.

set "SCRIPT_DIR=%~dp0"

REM Write a temp PowerShell script (avoids quoting issues)
REM NOTE: ^) is used inside if/else blocks to escape ) for cmd.exe
set "PS_SCRIPT=%TEMP%\fss_shortcut.ps1"
echo $ws = New-Object -ComObject WScript.Shell > "%PS_SCRIPT%"
echo $desktop = [Environment]::GetFolderPath('Desktop'^) >> "%PS_SCRIPT%"
if exist "%ICON_ICO%" (
    echo $s = $ws.CreateShortcut("$desktop\FromSoft Seamless Co-op Manager.lnk"^) >> "%PS_SCRIPT%"
    echo $s.TargetPath = "wscript.exe" >> "%PS_SCRIPT%"
    echo $s.Arguments = '"%SCRIPT_DIR%launch.vbs"' >> "%PS_SCRIPT%"
    echo $s.WorkingDirectory = "%SCRIPT_DIR%" >> "%PS_SCRIPT%"
    echo $s.IconLocation = "%ICON_ICO%" >> "%PS_SCRIPT%"
    echo $s.Description = "FromSoft Co-op Settings Manager" >> "%PS_SCRIPT%"
    echo $s.Save(^) >> "%PS_SCRIPT%"
) else (
    echo $s = $ws.CreateShortcut("$desktop\FromSoft Seamless Co-op Manager.lnk"^) >> "%PS_SCRIPT%"
    echo $s.TargetPath = "wscript.exe" >> "%PS_SCRIPT%"
    echo $s.Arguments = '"%SCRIPT_DIR%launch.vbs"' >> "%PS_SCRIPT%"
    echo $s.WorkingDirectory = "%SCRIPT_DIR%" >> "%PS_SCRIPT%"
    echo $s.Description = "FromSoft Co-op Settings Manager" >> "%PS_SCRIPT%"
    echo $s.Save(^) >> "%PS_SCRIPT%"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" >nul 2>&1
del "%PS_SCRIPT%" >nul 2>&1

REM Check if shortcut was created (handles OneDrive Desktop too)
set "SHORTCUT_FOUND=0"
if exist "%USERPROFILE%\Desktop\FromSoft Seamless Co-op Manager.lnk" set "SHORTCUT_FOUND=1"
if exist "%USERPROFILE%\OneDrive\Desktop\FromSoft Seamless Co-op Manager.lnk" set "SHORTCUT_FOUND=1"

if "%SHORTCUT_FOUND%"=="1" (
    echo        Desktop shortcut created!
) else (
    echo        Could not create shortcut ^(not critical^).
    echo        You can always run "run.bat" directly.
)
echo.

REM --- Done -------------------------------------------------------
echo.
echo  +==============================================================+
echo  :                                                              :
echo  :   Installation complete!                                     :
echo  :                                                              :
echo  :   To start the app:                                          :
echo  :     - Double-click the desktop shortcut                      :
echo  :     - Or run "run.bat" in this folder                        :
echo  :                                                              :
echo  :   Your browser will open automatically.                      :
echo  :                                                              :
echo  +==============================================================+
echo.

choice /c YN /n /m "  Launch the app now? (Y/N) "
if errorlevel 2 goto :done
if errorlevel 1 (
    wscript "%~dp0launch.vbs"
)

:done
echo.
echo  Goodbye!
pause
exit /b 0
