@echo off
setlocal enabledelayedexpansion
title FromSoft Co-op Manager - Uninstaller
color 0C

echo.
echo  +==============================================================+
echo  :                                                              :
echo  :      FromSoft Co-op Manager - Uninstaller                    :
echo  :                                                              :
echo  :   This will remove the app and all shortcuts.                :
echo  :                                                              :
echo  +==============================================================+
echo.

REM Confirm before uninstalling
choice /c YN /n /m "  Are you sure you want to uninstall? (Y/N) "
if errorlevel 2 goto :cancel
if errorlevel 1 goto :confirmed

:cancel
echo.
echo  Uninstall cancelled.
pause
exit /b 0

:confirmed
echo.
echo  Stopping any running instances...
echo.

REM Kill any running Python processes from this app (more targeted approach)
REM Only kill processes that are running from the install directory
set "INSTALL_DIR=%LOCALAPPDATA%\FromSoftCoopManager"

REM Use WMIC to find and kill only Python processes from our install directory
for /f "tokens=2" %%p in ('wmic process where "name='pythonw.exe' and commandline like '%%FromSoftCoopManager%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=2" %%p in ('wmic process where "name='python.exe' and commandline like '%%FromSoftCoopManager%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /F /PID %%p >nul 2>&1
)

REM Wait a moment for processes to fully exit and release file handles
timeout /t 2 /nobreak >nul 2>&1

echo  Stopped any running instances.
echo.

echo  Removing installation folder...
echo  Path: %INSTALL_DIR%
echo.

if exist "%INSTALL_DIR%" (
    rd /s /q "%INSTALL_DIR%" >nul 2>&1
    
    REM Verify deletion succeeded
    if exist "%INSTALL_DIR%" (
        echo  [WARNING] Could not fully delete install folder on first attempt.
        echo            Retrying...
        timeout /t 1 /nobreak >nul 2>&1
        rd /s /q "%INSTALL_DIR%" >nul 2>&1
        
        if exist "%INSTALL_DIR%" (
            echo  [WARNING] Some files may still exist at:
            echo            %INSTALL_DIR%
            echo            You may need to manually delete this folder.
        ) else (
            echo  Installation folder deleted.
        )
    ) else (
        echo  Installation folder deleted.
    )
) else (
    echo  Install folder not found (already removed?).
)
echo.

echo  Removing desktop shortcuts...
echo.

REM Set the shortcut name
set "SHORTCUT_NAME=FromSoft Seamless Co-op Manager.lnk"
set "SHORTCUT_DELETED=0"

REM Get actual desktop path from PowerShell
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"') do set "DESKTOP_PATH=%%i"
echo  Looking in: %DESKTOP_PATH%
echo.

REM Delete shortcuts by name
if exist "%DESKTOP_PATH%\%SHORTCUT_NAME%" (
    del /F /Q "%DESKTOP_PATH%\%SHORTCUT_NAME%"
    echo  Deleted: %SHORTCUT_NAME%
    set "SHORTCUT_DELETED=1"
)

REM Use PowerShell to find and delete any shortcut that targets launch.vbs (check both standard and OneDrive Desktop)
powershell -NoProfile -Command "$desktops = @([Environment]::GetFolderPath('Desktop'), \"$env:USERPROFILE\OneDrive\Desktop\"); foreach ($desktop in $desktops) { if (Test-Path $desktop) { Write-Host \"  Checking: $desktop\"; Get-ChildItem -Path $desktop -Filter '*.lnk' -ErrorAction SilentlyContinue | ForEach-Object { $shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut($_.FullName); Write-Host \"    Found shortcut: $($_.Name)\"; Write-Host \"      Target: $($shortcut.TargetPath)\"; Write-Host \"      Arguments: $($shortcut.Arguments)\"; if ($shortcut.TargetPath -match 'wscript' -and $shortcut.Arguments -match 'launch\.vbs') { Remove-Item $_.FullName -Force; Write-Host \"      DELETED: $($_.Name)\"; } } } }"

echo.
echo  Desktop shortcut removal complete.
echo.

REM Delete game shortcuts (AC6, DS3, ER, DSR, ERN)
set "GAMES=Armored Core 6 Dark Souls III Dark Souls Remastered Elden Ring Elden Ring Nightreign"
for %%G in (%GAMES%) do (
    if exist "%USERPROFILE%\Desktop\%%G Co-op.lnk" (
        del "%USERPROFILE%\Desktop\%%G Co-op.lnk"
        echo  Deleted: %%G Co-op.lnk
    )
    if exist "%USERPROFILE%\OneDrive\Desktop\%%G Co-op.lnk" (
        del "%USERPROFILE%\OneDrive\Desktop\%%G Co-op.lnk"
        echo  Deleted: %%G Co-op.lnk (OneDrive)
    )
)

echo.

REM Optional: Remove Python if installed by the app
REM (We won't auto-remove it since it might be needed elsewhere)

echo.
echo  +==============================================================+
echo  :                                                              :
echo  :   Uninstallation complete!                                   :
echo  :                                                              :
echo  :   All files and shortcuts have been removed.                 :
echo  :                                                              :
echo  :   Python (if installed) was NOT removed, as it may be        :
echo  :   needed by other applications.                              :
echo  :   To remove it manually, go to:                              :
echo  :     Settings → Apps → Python                                 :
echo  :                                                              :
echo  +==============================================================+
echo.

pause
exit /b 0
