"""
ME3 CLI service — detect, install, and use Mod Engine 3.
"""

import os
import subprocess
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

ME3_GITHUB_API = "https://api.github.com/repos/garyttierney/me3/releases/latest"
ME3_DEFAULT_INSTALL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "me3")
ME3_EXE_NAME = "me3.exe"
ME3_PROFILE_PREFIX = "fsmm_"

# Map our game IDs to ME3 game names
import re as _re


def slugify(name: str) -> str:
    """Convert a mod name to a filesystem-safe slug."""
    return _re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
ME3_GAME_MAP = {
    "ac6": "armoredcore6",
    "ds3": "darksouls3",
    "er": "eldenring",
    "ern": "nightreign",
}


def find_me3_executable(custom_path: str = "") -> str | None:
    """Search for me3.exe in common locations."""
    if custom_path and os.path.isfile(custom_path):
        return custom_path

    # Fast path: direct location
    direct = os.path.join(ME3_DEFAULT_INSTALL, ME3_EXE_NAME)
    if os.path.isfile(direct):
        return direct

    # Recursive search inside ME3_DEFAULT_INSTALL — handles zip extraction with subdirectory
    if os.path.isdir(ME3_DEFAULT_INSTALL):
        for root, _dirs, files in os.walk(ME3_DEFAULT_INSTALL):
            if ME3_EXE_NAME in files:
                return os.path.join(root, ME3_EXE_NAME)

    # Other common locations
    for path in [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "me3", ME3_EXE_NAME),
        shutil.which("me3") or "",
    ]:
        if path and os.path.isfile(path):
            return path

    return None


def is_me3_installed(custom_path: str = "") -> bool:
    return find_me3_executable(custom_path) is not None


def get_me3_version(custom_path: str = "") -> str | None:
    me3_path = find_me3_executable(custom_path)
    if not me3_path:
        return None
    try:
        result = subprocess.run(
            [me3_path, "--version"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception:
        return None


def get_latest_me3_release() -> dict | None:
    """Fetch latest release info from GitHub API. Returns None on failure."""
    try:
        import json
        req = urllib.request.Request(
            ME3_GITHUB_API,
            headers={"User-Agent": "FromSoftModManager/2.0", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            assets = data.get("assets", [])
            windows_asset = next(
                (a for a in assets if "windows" in a["name"].lower() and a["name"].endswith(".zip")),
                None
            )
            if not windows_asset:
                windows_asset = next(
                    (a for a in assets if a["name"].endswith(".zip")),
                    None
                )
            return {
                "version": data.get("tag_name", ""),
                "download_url": windows_asset["browser_download_url"] if windows_asset else "",
                "name": windows_asset["name"] if windows_asset else "",
            }
    except Exception as e:
        return {"error": str(e), "download_url": ""}


def download_and_install_me3(progress_callback=None) -> dict:
    """
    Download latest ME3 from GitHub and install to LOCALAPPDATA/me3.
    progress_callback(message: str, percent: int)
    """
    if progress_callback:
        progress_callback("Fetching ME3 release info…", 5)

    release = get_latest_me3_release()
    if not release or not release.get("download_url"):
        error_detail = release.get("error", "") if release else "network error"
        return {
            "success": False,
            "message": f"Could not fetch ME3 release info ({error_detail}). Install manually from github.com/garyttierney/me3",
        }

    download_url = release["download_url"]
    install_dir = ME3_DEFAULT_INSTALL
    os.makedirs(install_dir, exist_ok=True)

    zip_path = os.path.join(install_dir, "me3_download.zip")

    if progress_callback:
        progress_callback(f"Downloading ME3 {release['version']}…", 20)

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "FromSoftModManager/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, 'wb') as f:
            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total and progress_callback:
                    pct = 20 + int((downloaded / total) * 60)
                    progress_callback(f"Downloading… {downloaded // 1024}KB / {total // 1024}KB", pct)
    except Exception as e:
        return {"success": False, "message": f"Download failed: {e}"}

    if progress_callback:
        progress_callback("Extracting ME3…", 85)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(install_dir)
        os.remove(zip_path)
    except Exception as e:
        return {"success": False, "message": f"Extraction failed: {e}"}

    me3_path = find_me3_executable()
    if not me3_path:
        # Last-ditch recursive search in case extraction landed somewhere unexpected
        for root, _dirs, files in os.walk(install_dir):
            if ME3_EXE_NAME in files:
                me3_path = os.path.join(root, ME3_EXE_NAME)
                break
    if not me3_path:
        return {
            "success": False,
            "message": (
                f"ME3 extracted to {install_dir} but me3.exe was not found. "
                "Try installing manually from github.com/garyttierney/me3"
            ),
        }

    if progress_callback:
        progress_callback("ME3 installed successfully!", 100)

    return {"success": True, "message": f"ME3 {release['version']} installed", "path": me3_path}


def get_me3_profiles_dir(me3_exe_path: str) -> str:
    """Return (and create) the profiles directory next to the me3 executable."""
    profiles_dir = os.path.join(os.path.dirname(me3_exe_path), "profiles")
    os.makedirs(profiles_dir, exist_ok=True)
    return profiles_dir


def write_me3_profile(
    game_id: str,
    mod_dirs: "list[str] | str",
    me3_exe_path: str,
    native_dlls: "list[str] | None" = None,
) -> str | None:
    """
    Write a ME3 v1 TOML profile with [[packages]] and [[natives]] blocks.
    Uses single-quoted TOML literal strings for paths (no backslash escaping).
    Returns the profile file path on success, None if game not in ME3_GAME_MAP.
    """
    if game_id not in ME3_GAME_MAP:
        return None

    if isinstance(mod_dirs, str):
        mod_dirs = [mod_dirs]

    profiles_dir = get_me3_profiles_dir(me3_exe_path)
    profile_path = os.path.join(profiles_dir, f"{ME3_PROFILE_PREFIX}{game_id}.toml")

    me3_game = ME3_GAME_MAP[game_id]
    lines = [
        'profileVersion = "v1"\n',
    ]

    # Packages section
    if mod_dirs:
        for mod_dir in mod_dirs:
            lines.append(f"\n[[packages]]\npath = '{mod_dir}'\n")
    else:
        lines.append("packages = []\n")

    # Game support
    lines.append(f'\n[[supports]]\ngame = "{me3_game}"\n')

    # Natives section — include all required fields ME3 expects
    for dll in (native_dlls or []):
        lines.append(
            f"\n[[natives]]\n"
            f"path = '{dll}'\n"
            f"optional = false\n"
            f"enabled = true\n"
            f"load_before = []\n"
            f"load_after = []\n"
            f"load_early = false\n"
        )

    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return profile_path
    except Exception:
        return None


def get_me3_profile_path(game_id: str, me3_exe_path: str) -> str | None:
    """Return the profile path if it exists, else None."""
    if game_id not in ME3_GAME_MAP:
        return None
    profiles_dir = os.path.join(os.path.dirname(me3_exe_path), "profiles")
    path = os.path.join(profiles_dir, f"{ME3_PROFILE_PREFIX}{game_id}.toml")
    return path if os.path.isfile(path) else None


def launch_game_with_me3(game_id: str, me3_path: str, terminal_callback=None) -> subprocess.Popen | None:
    """Launch a game using ME3 CLI.

    Waits briefly for ME3 to finish attaching, then checks for errors.
    Returns the Popen on success, None if ME3 failed (caller can fall back).
    """
    import threading
    import time

    me3_game_name = ME3_GAME_MAP.get(game_id)
    if not me3_game_name:
        return None
    if not me3_path or not os.path.isfile(me3_path):
        return None

    cmd = [me3_path, "launch", "-g", me3_game_name]

    # Use app-managed profile if it exists
    profile_path = get_me3_profile_path(game_id, me3_path)
    if profile_path:
        cmd += ["--profile", profile_path]

    if terminal_callback:
        terminal_callback(f"$ {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        # Read ME3 output to detect attach errors.  ME3 exits quickly on
        # failure, so we collect output with a short timeout.
        output_lines: list[str] = []
        has_error = False

        def _collect():
            nonlocal has_error
            try:
                for line in proc.stdout:
                    output_lines.append(line)
                    if "ERROR" in line or "panicked" in line:
                        has_error = True
                proc.stdout.close()
            except Exception:
                pass

        reader = threading.Thread(target=_collect, daemon=True)
        reader.start()

        # Give ME3 a moment to start and report errors
        reader.join(timeout=6)

        if has_error or (proc.poll() is not None and proc.returncode != 0):
            if terminal_callback:
                terminal_callback("[ME3] Attach failed — ME3 may need an update")
            return None

        return proc
    except Exception as e:
        if terminal_callback:
            terminal_callback(f"[Error] {e}")
        return None


def launch_game_direct(launcher_path: str, terminal_callback=None) -> subprocess.Popen | None:
    """Launch the co-op launcher .exe directly."""
    if not launcher_path or not os.path.isfile(launcher_path):
        return None

    if terminal_callback:
        terminal_callback(f"$ {launcher_path}")

    try:
        proc = subprocess.Popen(
            [launcher_path],
            cwd=os.path.dirname(launcher_path),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return proc
    except Exception as e:
        if terminal_callback:
            terminal_callback(f"[Error] {e}")
        return None


def create_desktop_shortcut(game_name: str, launcher_path: str, icon_path: str = "") -> dict:
    """Create a Windows desktop shortcut using PowerShell."""
    if not launcher_path or not os.path.isfile(launcher_path):
        return {"success": False, "message": "Launcher not found"}

    try:
        desktop = subprocess.check_output(
            ["powershell", "-Command", "[Environment]::GetFolderPath('Desktop')"],
            text=True
        ).strip()
        shortcut_path = os.path.join(desktop, f"{game_name}.lnk")

        ps_script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{shortcut_path}')
$shortcut.TargetPath = '{launcher_path}'
$shortcut.WorkingDirectory = '{os.path.dirname(launcher_path)}'
"""
        if icon_path and os.path.isfile(icon_path):
            ps_script += f"$shortcut.IconLocation = '{icon_path}'\n"
        ps_script += "$shortcut.Save()"

        subprocess.run(["powershell", "-Command", ps_script], check=True, capture_output=True)
        return {"success": True, "message": f"Shortcut created: {shortcut_path}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
