"""
Steam library scanning and game detection.
Ported from server.py.
"""

import os
import re
import sys
import string
from app.config.game_definitions import GAME_DEFINITIONS


def get_windows_drives() -> list[str]:
    drives = []
    if sys.platform == "win32":
        try:
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(f"{letter}:\\")
                bitmask >>= 1
        except Exception:
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    drives.append(root)
    else:
        for letter in string.ascii_uppercase:
            for prefix in [f"/mnt/{letter.lower()}", f"/{letter.lower()}"]:
                if os.path.isdir(prefix):
                    drives.append(prefix)
    return drives


def parse_library_folders_vdf(vdf_path: str) -> list[str]:
    paths = []
    try:
        with open(vdf_path, "r", encoding="utf-8") as f:
            content = f.read()
        for match in re.finditer(r'"path"\s+"([^"]+)"', content):
            p = match.group(1).replace("\\\\", "\\")
            paths.append(p)
    except Exception:
        pass
    return paths


def _get_steam_path_from_registry() -> str | None:
    """Read Steam install path from the Windows registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        for hive, subkey, value in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam", "SteamPath"),
        ]:
            try:
                key = winreg.OpenKey(hive, subkey)
                path, _ = winreg.QueryValueEx(key, value)
                winreg.CloseKey(key)
                path = path.replace("/", "\\")
                if os.path.isdir(path):
                    return path
            except Exception:
                continue
    except Exception:
        pass
    return None


def find_steam_libraries() -> list[str]:
    library_dirs: set[str] = set()

    def _add_steam_root(steam_root: str):
        """Add a Steam root and all its library folders from the VDF."""
        if not os.path.isdir(steam_root):
            return
        library_dirs.add(os.path.normpath(steam_root))
        vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            for p in parse_library_folders_vdf(vdf):
                if os.path.isdir(p):
                    library_dirs.add(os.path.normpath(p))

    # 1. Registry — most reliable, finds Steam wherever it was installed
    registry_path = _get_steam_path_from_registry()
    if registry_path:
        _add_steam_root(registry_path)

    # 2. Common drive probe — catches additional libraries on other drives
    probe_patterns = [
        "Steam",
        "SteamLibrary",
        os.path.join("Program Files", "Steam"),
        os.path.join("Program Files (x86)", "Steam"),
    ]
    for drive in get_windows_drives():
        for pattern in probe_patterns:
            candidate = os.path.join(drive, pattern)
            if os.path.isdir(candidate):
                _add_steam_root(candidate)

    return list(library_dirs)


def detect_save_dir(appdata_folder: str) -> str | None:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    base = os.path.join(appdata, appdata_folder)
    if not os.path.isdir(base):
        return None
    for entry in os.listdir(base):
        full = os.path.join(base, entry)
        if os.path.isdir(full) and re.fullmatch(r'[0-9a-fA-F]+', entry):
            return os.path.normpath(full)
    return None


def scan_for_games(progress_callback=None) -> dict:
    """
    Scan all Steam libraries for supported games.
    progress_callback(message: str) called with status updates.
    Returns dict of game_id -> game_info.
    """
    if progress_callback:
        progress_callback("Finding Steam libraries…")

    libraries = find_steam_libraries()
    found_games = {}

    for lib_dir in libraries:
        steamapps_dir = os.path.join(lib_dir, "steamapps")
        common_dir = os.path.join(steamapps_dir, "common")
        if not os.path.isdir(common_dir):
            continue

        for game_id, gdef in GAME_DEFINITIONS.items():
            if game_id in found_games:
                continue

            if progress_callback:
                progress_callback(f"Checking {gdef['name']}…")

            game_dir = os.path.join(common_dir, gdef["steam_folder"])
            if not os.path.isdir(game_dir):
                continue

            app_id = gdef.get("steam_app_id")
            if app_id:
                manifest = os.path.join(steamapps_dir, f"appmanifest_{app_id}.acf")
                if not os.path.isfile(manifest):
                    continue

            config_path = os.path.join(game_dir, gdef["config_relative"])
            mod_installed = os.path.isfile(config_path)
            launcher_path = os.path.join(game_dir, gdef["launcher_relative"])
            save_dir = detect_save_dir(gdef["save_appdata_folder"])

            found_games[game_id] = {
                "name": gdef["name"],
                "steam_app_id": gdef.get("steam_app_id"),
                "install_path": os.path.normpath(game_dir),
                "config_path": os.path.normpath(config_path) if mod_installed else None,
                "save_prefix": gdef["save_prefix"],
                "base_ext": gdef["base_ext"],
                "coop_ext": gdef["coop_ext"],
                "save_dir": save_dir,
                "mod_installed": mod_installed,
                "mod_name": gdef["mod_name"],
                "nexus_url": gdef["nexus_url"],
                "launcher_exists": os.path.isfile(launcher_path),
                "launcher_path": os.path.normpath(launcher_path) if os.path.isfile(launcher_path) else None,
                "installed_mod_version": None,
            }

    return found_games
