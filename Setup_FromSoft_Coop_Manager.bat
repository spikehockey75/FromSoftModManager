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

REM --- Configuration ----------------------------------------------
set "REPO_URL=https://github.com/spikehockey75/FromSoftSeamlessCoOpManager/archive/refs/heads/main.zip"
set "APP_NAME=FromSoft Seamless Co-op Manager"
set "INSTALL_DIR=%LOCALAPPDATA%\FromSoftCoopManager"
set "ZIP_FILE=%TEMP%\fromsoft_coop_manager.zip"
set "EXTRACT_DIR=%TEMP%\fromsoft_coop_extract"

REM If we're already inside the installed app folder, skip download
if exist "%~dp0server.py" (
    echo  Detected existing app files. Running in-place setup...
    set "INSTALL_DIR=%~dp0"
    REM Remove trailing backslash
    if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"
    goto :skip_download
)

REM --- Step 1: Check for Python -----------------------------------
echo  [1/6] Checking for Python...
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
        echo          and run Setup_FromSoft_Coop_Manager.bat again.
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo         Found: %PYVER%
echo.

REM --- Step 2: Download application files -------------------------
echo  [2/6] Downloading application files...
echo.

if exist "%EXTRACT_DIR%" rd /s /q "%EXTRACT_DIR%"

echo        Downloading from GitHub...
curl -L -o "%ZIP_FILE%" "%REPO_URL%"
if errorlevel 1 (
    echo.
    echo  [ERROR] Could not download the application files.
    echo          Check your internet connection and try again.
    pause
    exit /b 1
)
echo        Download complete.
echo.

REM --- Step 3: Extract and install --------------------------------
echo  [3/6] Installing application...
echo.

echo        Extracting files...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Failed to extract application files.
    pause
    exit /b 1
)

REM GitHub ZIP extracts to a subfolder like RepoName-main/
set "EXTRACTED_INNER="
for /d %%D in ("%EXTRACT_DIR%\*") do set "EXTRACTED_INNER=%%D"

if not defined EXTRACTED_INNER (
    echo  [ERROR] Could not find extracted files.
    pause
    exit /b 1
)

REM Create install directory and copy files
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy /s /e /y /q "!EXTRACTED_INNER!\*" "%INSTALL_DIR%\" >nul
if errorlevel 1 (
    echo  [ERROR] Failed to copy files to install directory.
    pause
    exit /b 1
)

REM Cleanup temp files
del "%ZIP_FILE%" >nul 2>&1
rd /s /q "%EXTRACT_DIR%" >nul 2>&1

echo        Installed to: %INSTALL_DIR%
echo.

:skip_download

REM Change to the install directory for remaining steps
cd /d "%INSTALL_DIR%"

REM --- Step 4: Create virtual environment -------------------------
echo  [4/6] Setting up virtual environment...
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

REM --- Step 5: Install dependencies -------------------------------
echo  [5/6] Installing dependencies...
echo.

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
if exist "requirements.txt" (
    python -m pip install -r "requirements.txt"
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

REM --- Step 6: Create launcher scripts ----------------------------
echo  [6/6] Creating launcher scripts and desktop shortcut...
echo.

set "SCRIPT_DIR=%INSTALL_DIR%\"
set "ICON_ICO=%INSTALL_DIR%\FSSIcon.ico"

REM Create launch.vbs (silent launcher - no console window)
echo Set WshShell = CreateObject("WScript.Shell"^) > "%INSTALL_DIR%\launch.vbs"
echo scriptDir = CreateObject("Scripting.FileSystemObject"^).GetParentFolderName(WScript.ScriptFullName^) >> "%INSTALL_DIR%\launch.vbs"
echo WshShell.Run Chr(34^) ^& scriptDir ^& "\run.bat" ^& Chr(34^), 0, False >> "%INSTALL_DIR%\launch.vbs"

if exist "%INSTALL_DIR%\launch.vbs" (
    echo        launch.vbs created.
) else (
    echo        [WARNING] Could not create launch.vbs.
)

REM Create run.bat
echo @echo off > "%INSTALL_DIR%\run.bat"
echo title FromSoft Co-op Settings Manager >> "%INSTALL_DIR%\run.bat"
echo cd /d "%%~dp0" >> "%INSTALL_DIR%\run.bat"
echo if not exist ".venv\Scripts\activate.bat" ^( >> "%INSTALL_DIR%\run.bat"
echo     call Setup_FromSoft_Coop_Manager.bat >> "%INSTALL_DIR%\run.bat"
echo     exit /b >> "%INSTALL_DIR%\run.bat"
echo ^) >> "%INSTALL_DIR%\run.bat"
echo call .venv\Scripts\activate.bat >> "%INSTALL_DIR%\run.bat"
echo where pythonw ^>nul 2^>^&1 >> "%INSTALL_DIR%\run.bat"
echo if %%errorlevel%%==0 ^( >> "%INSTALL_DIR%\run.bat"
echo     start "" pythonw server.py >> "%INSTALL_DIR%\run.bat"
echo ^) else ^( >> "%INSTALL_DIR%\run.bat"
echo     python server.py >> "%INSTALL_DIR%\run.bat"
echo ^) >> "%INSTALL_DIR%\run.bat"
echo        run.bat created.
echo.

REM Create desktop shortcut

REM Write a temp PowerShell script (avoids quoting issues)
REM NOTE: ^) is used inside if/else blocks to escape ) for cmd.exe
set "PS_SCRIPT=%TEMP%\fss_shortcut.ps1"
echo $ws = New-Object -ComObject WScript.Shell > "%PS_SCRIPT%"
echo $desktop = [Environment]::GetFolderPath('Desktop'^) >> "%PS_SCRIPT%"
if exist "%ICON_ICO%" (
    echo $s = $ws.CreateShortcut("$desktop\%APP_NAME%.lnk"^) >> "%PS_SCRIPT%"
    echo $s.TargetPath = "wscript.exe" >> "%PS_SCRIPT%"
    echo $s.Arguments = '"%SCRIPT_DIR%launch.vbs"' >> "%PS_SCRIPT%"
    echo $s.WorkingDirectory = "%SCRIPT_DIR%" >> "%PS_SCRIPT%"
    echo $s.IconLocation = "%ICON_ICO%" >> "%PS_SCRIPT%"
    echo $s.Description = "FromSoft Co-op Settings Manager" >> "%PS_SCRIPT%"
    echo $s.Save(^) >> "%PS_SCRIPT%"
) else (
    echo $s = $ws.CreateShortcut("$desktop\%APP_NAME%.lnk"^) >> "%PS_SCRIPT%"
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
if exist "%USERPROFILE%\Desktop\%APP_NAME%.lnk" set "SHORTCUT_FOUND=1"
if exist "%USERPROFILE%\OneDrive\Desktop\%APP_NAME%.lnk" set "SHORTCUT_FOUND=1"

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
echo  :   Installed to:                                              :
echo  :     %INSTALL_DIR%
echo  :                                                              :
echo  :   To start the app:                                          :
echo  :     - Double-click the desktop shortcut                      :
echo  :     - Or run "run.bat" in the install folder                 :
echo  :                                                              :
echo  :   Your browser will open automatically.                      :
echo  :                                                              :
echo  +==============================================================+
echo.

choice /c YN /n /m "  Launch the app now? (Y/N) "
if errorlevel 2 goto :done
if errorlevel 1 (
    wscript "%INSTALL_DIR%\launch.vbs"
)

:done
echo.
echo  Goodbye!
pause
exit /b 0
