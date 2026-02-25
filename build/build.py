"""
PyInstaller build script for FromSoft Mod Manager.
Run from the project root: python build/build.py
"""

import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build_pyinstaller")

APP_NAME = "FromSoftModManager"
ENTRY_POINT = os.path.join(BASE_DIR, "main.py")
ICON = os.path.join(BASE_DIR, "FSSIcon.ico")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", APP_NAME,
    "--onedir",            # --onefile is smaller but slower to start
    "--windowed",          # no console window
    "--clean",
    "--noconfirm",
    f"--distpath={DIST_DIR}",
    f"--workpath={BUILD_DIR}",
    # Data files
    "--add-data", f"{os.path.join(BASE_DIR, 'resources')};resources",
    "--add-data", f"{os.path.join(BASE_DIR, 'VERSION')};.",
    # Hidden imports
    "--hidden-import", "PySide6.QtCore",
    "--hidden-import", "PySide6.QtGui",
    "--hidden-import", "PySide6.QtWidgets",
    "--hidden-import", "app.config.game_definitions",
    "--hidden-import", "app.config.config_manager",
    "--hidden-import", "app.core.game_scanner",
    "--hidden-import", "app.core.ini_parser",
    "--hidden-import", "app.core.save_manager",
    "--hidden-import", "app.core.mod_installer",
    "--hidden-import", "app.core.mod_updater",
    "--hidden-import", "app.core.me3_service",
    "--hidden-import", "app.services.nexus_service",
    "--hidden-import", "app.services.nexus_sso",
    "--hidden-import", "app.services.steam_service",
]

if os.path.isfile(ICON):
    cmd.extend(["--icon", ICON])

cmd.append(ENTRY_POINT)

print(f"Building {APP_NAME}…")
print(f"Entry: {ENTRY_POINT}")
result = subprocess.run(cmd, cwd=BASE_DIR)

if result.returncode == 0:
    exe_path = os.path.join(DIST_DIR, APP_NAME, f"{APP_NAME}.exe")
    if os.path.isfile(exe_path):
        print(f"\n✓ Build successful: {exe_path}")
    else:
        print(f"\n✓ Build complete. Output in: {DIST_DIR}")
else:
    print(f"\n✗ Build failed (exit code {result.returncode})")
    sys.exit(1)
