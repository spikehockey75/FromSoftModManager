@echo off
setlocal enabledelayedexpansion
title FromSoft Co-op Manager - Uninstaller
color 0C

echo.
echo  +==============================================================+
echo  :                                                              :
echo  :      FromSoft Co-op Manager — Uninstaller                    :
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

REM Kill any running Python processes from this app
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
echo  Stopped any running instances.
echo.

REM Install directory
set "INSTALL_DIR=%LOCALAPPDATA%\FromSoftCoopManager"

echo  Removing installation folder...
echo  Path: %INSTALL_DIR%
echo.

if exist "%INSTALL_DIR%" (
    rd /s /q "%INSTALL_DIR%"
    if errorlevel 1 (
        echo  [WARNING] Could not fully delete install folder.
        echo            Some files may still exist.
    ) else (
        echo  Installation folder deleted.
    )
) else (
    echo  Install folder not found (already removed?).
)
echo.

echo  Removing desktop shortcuts...
echo.

REM Delete from regular Desktop
if exist "%USERPROFILE%\Desktop\FromSoft Seamless Co-op Manager.lnk" (
    del "%USERPROFILE%\Desktop\FromSoft Seamless Co-op Manager.lnk"
    echo  Deleted: FromSoft Seamless Co-op Manager.lnk
)

REM Delete from OneDrive Desktop (if it exists)
if exist "%USERPROFILE%\OneDrive\Desktop\FromSoft Seamless Co-op Manager.lnk" (
    del "%USERPROFILE%\OneDrive\Desktop\FromSoft Seamless Co-op Manager.lnk"
    echo  Deleted: FromSoft Seamless Co-op Manager.lnk (OneDrive)
)

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
