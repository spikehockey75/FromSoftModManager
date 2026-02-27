"""
App self-update service — check GitHub releases and download the installer.
"""

import os
import sys
import subprocess
import tempfile
import urllib.request

GITHUB_API = "https://api.github.com/repos/spikehockey75/FromSoftModManager/releases/latest"
USER_AGENT = "FromSoftModManager/2.0"


def get_current_version() -> str:
    """Read the app version from the bundled VERSION file."""
    if getattr(sys, "frozen", False):
        base = os.path.join(sys._MEIPASS)
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    version_file = os.path.join(base, "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"


def _parse_version(v: str) -> tuple:
    """Convert 'X.Y.Z' to a comparable tuple."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def get_latest_release() -> dict:
    """Fetch the latest release info from GitHub.

    Returns {"version", "download_url", "name"} on success,
    or {"error": str} on failure.
    """
    try:
        import json
        req = urllib.request.Request(
            GITHUB_API,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        tag = data.get("tag_name", "")
        assets = data.get("assets", [])

        # Prefer the Setup installer exe
        installer = next(
            (a for a in assets if "Setup" in a["name"] and a["name"].endswith(".exe")),
            None,
        )
        if not installer:
            # Fall back to any exe or zip
            installer = next(
                (a for a in assets if a["name"].endswith((".exe", ".zip"))),
                None,
            )

        return {
            "version": tag.lstrip("v"),
            "download_url": installer["browser_download_url"] if installer else "",
            "name": installer["name"] if installer else "",
        }
    except Exception as e:
        return {"error": str(e)}


def check_for_update() -> dict:
    """Compare current version with latest GitHub release.

    Returns {"has_update", "current", "latest", "download_url"}.
    On error returns {"has_update": False, "error": str}.
    """
    current = get_current_version()
    release = get_latest_release()

    if "error" in release:
        return {"has_update": False, "current": current, "error": release["error"]}

    latest = release.get("version", "")
    has_update = _parse_version(latest) > _parse_version(current)

    return {
        "has_update": has_update,
        "current": current,
        "latest": latest,
        "download_url": release.get("download_url", ""),
        "name": release.get("name", ""),
    }


def download_and_run_installer(download_url: str, progress_callback=None) -> dict:
    """Download the installer exe and launch it.

    progress_callback(message: str, percent: int)
    Returns {"success": bool, "message": str}.
    """
    if not download_url:
        return {"success": False, "message": "No download URL available"}

    if progress_callback:
        progress_callback("Downloading update…", 5)

    tmp_dir = tempfile.mkdtemp(prefix="fsmm_update_")
    filename = download_url.rsplit("/", 1)[-1] or "FromSoftModManager_Setup.exe"
    installer_path = os.path.join(tmp_dir, filename)

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp, \
             open(installer_path, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total and progress_callback:
                    pct = 5 + int((downloaded / total) * 85)
                    progress_callback(
                        f"Downloading… {downloaded // 1024}KB / {total // 1024}KB", pct
                    )
    except Exception as e:
        return {"success": False, "message": f"Download failed: {e}"}

    if progress_callback:
        progress_callback("Launching installer…", 95)

    try:
        # Launch the installer detached — it will close this app via CloseApplications
        subprocess.Popen(
            [installer_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.platform == "win32" else 0,
        )
        return {"success": True, "message": "Installer launched"}
    except Exception as e:
        return {"success": False, "message": f"Could not launch installer: {e}"}
