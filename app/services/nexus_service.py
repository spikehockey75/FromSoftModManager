"""
Nexus Mods API service — mod info, updates, downloads.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from app.core.mod_updater import version_compare

NEXUS_API_BASE = "https://api.nexusmods.com/v1"
APPLICATION_NAME = "FromSoft Mod Manager"


def _read_version() -> str:
    """Read app version from the VERSION file."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    version_path = os.path.join(base, "VERSION")
    try:
        with open(version_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "2.0.0"


APPLICATION_VERSION = _read_version()


def parse_nexus_url(url: str) -> "tuple[str, int] | None":
    """Extract (domain, mod_id) from a Nexus Mods URL, or None if not parseable."""
    import re
    m = re.match(r'https?://www\.nexusmods\.com/([^/]+)/mods/(\d+)', url.strip())
    return (m.group(1), int(m.group(2))) if m else None


class NexusService:
    def __init__(self, access_token: str = "", config=None):
        self.access_token = access_token
        self._config = config  # ConfigManager for auto-refresh

    def _ensure_token(self):
        """Refresh the access token if expired. Updates self and config."""
        if not self._config or not self.access_token:
            return
        if not self._config.is_nexus_token_expired():
            return
        tokens = self._config.get_nexus_tokens()
        refresh_token = tokens.get("refresh_token", "")
        if not refresh_token:
            return
        from app.services.nexus_oauth import refresh_access_token
        new_tokens = refresh_access_token(refresh_token)
        if "error" in new_tokens:
            # Token revoked — clear auth so UI shows login button
            self._config.clear_nexus_auth()
            self.access_token = ""
            return
        self._config.set_nexus_tokens(new_tokens)
        self.access_token = new_tokens.get("access_token", "")

    def _headers(self) -> dict:
        h = {
            "Application-Name": APPLICATION_NAME,
            "Application-Version": APPLICATION_VERSION,
            "User-Agent": f"FromSoftModManager/{APPLICATION_VERSION}",
            "Accept": "application/json",
        }
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _get(self, path: str) -> dict:
        self._ensure_token()
        url = f"{NEXUS_API_BASE}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"error": "Nexus authorization invalid or expired", "requires_auth": True}
            elif e.code == 429:
                return {"error": "Rate limited. Try again later."}
            elif e.code == 404:
                return {"error": "Mod not found on Nexus"}
            return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}

    def validate_user(self) -> dict:
        """Validate token and get user info."""
        return self._get("/users/validate.json")

    def get_mod_info(self, game_domain: str, mod_id: int) -> dict:
        """Get mod metadata including latest version."""
        return self._get(f"/games/{game_domain}/mods/{mod_id}.json")

    def get_game_categories(self, game_domain: str) -> list[dict]:
        """Fetch mod categories for a game. Each has category_id, name."""
        result = self._get(f"/games/{game_domain}.json")
        if isinstance(result, dict) and "error" not in result:
            cats = result.get("categories", [])
            return cats if isinstance(cats, list) else []
        return []

    def get_trending_mods(self, game_domain: str) -> list[dict]:
        """Fetch trending mods for a game domain."""
        self._ensure_token()
        url = f"{NEXUS_API_BASE}/games/{game_domain}/mods/trending.json"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def get_mod_files(self, game_domain: str, mod_id: int) -> dict:
        """Get list of files for a mod."""
        return self._get(f"/games/{game_domain}/mods/{mod_id}/files.json")

    def get_download_links(self, game_domain: str, mod_id: int, file_id: int) -> list:
        """Get download URLs for a specific file (requires Premium or NXM)."""
        result = self._get(f"/games/{game_domain}/mods/{mod_id}/files/{file_id}/download_link.json")
        if isinstance(result, list):
            return result
        return []

    def check_mod_update(self, game_id: str, game_def: dict, installed_version: str | None) -> dict:
        """Check if there's an update for a mod. Returns update info dict."""
        domain = game_def.get("nexus_domain", "")
        mod_id = game_def.get("nexus_mod_id", 0)

        if not domain or not mod_id:
            return {"error": "No Nexus info for this game", "has_update": False}

        mod_info = self.get_mod_info(domain, mod_id)
        if "error" in mod_info:
            return {**mod_info, "has_update": False, "installed_version": installed_version}

        latest = mod_info.get("version", "unknown")
        has_update = False
        if installed_version and latest and latest != "unknown":
            has_update = version_compare(installed_version, latest) < 0
        elif latest and latest != "unknown":
            has_update = True

        return {
            "game_id": game_id,
            "installed_version": installed_version,
            "latest_version": latest,
            "has_update": has_update,
            "nexus_url": game_def.get("nexus_url", ""),
            "mod_name": mod_info.get("name", game_def.get("mod_name", "")),
        }

    def get_latest_file(self, game_domain: str, mod_id: int) -> dict | None:
        """Get the latest main file for a mod."""
        files_data = self.get_mod_files(game_domain, mod_id)
        if "error" in files_data:
            return None
        files = files_data.get("files", [])
        # Prefer "MAIN" category files
        main_files = [f for f in files if f.get("category_name") == "MAIN"]
        if not main_files:
            main_files = files
        if not main_files:
            return None
        # Sort by upload time (newest first)
        main_files.sort(key=lambda f: f.get("uploaded_timestamp", 0), reverse=True)
        return main_files[0]

    def download_latest_mod(
        self,
        game_id: str,
        game_def: dict,
        temp_dir: str,
        progress_callback=None,
    ) -> dict:
        """
        Download the latest mod file from Nexus to temp_dir.
        Requires Premium API key for direct download links.
        Returns:
          {"success": True, "zip_path": ..., "version": ..., "file_name": ...}
          {"success": False, "error": ..., "nexus_url": ..., "requires_premium": bool}
        """
        domain = game_def.get("nexus_domain", "")
        mod_id = game_def.get("nexus_mod_id", 0)
        nexus_url = game_def.get("nexus_url", "")

        if not domain or not mod_id:
            return {"success": False, "error": "No Nexus info configured for this game", "nexus_url": nexus_url}

        if progress_callback:
            progress_callback(5, "Fetching latest file info…")

        latest_file = self.get_latest_file(domain, mod_id)
        if not latest_file:
            return {"success": False, "error": "Could not retrieve file list from Nexus", "nexus_url": nexus_url}

        file_id = latest_file.get("file_id")
        file_name = latest_file.get("file_name", f"mod_{game_id}.zip")
        file_version = latest_file.get("version") or latest_file.get("mod_version", "")

        if progress_callback:
            progress_callback(10, f"Getting download link for {file_name}…")

        links = self.get_download_links(domain, mod_id, file_id)
        if not links:
            return {
                "success": False,
                "error": "Download links unavailable — Nexus Premium required for direct downloads",
                "nexus_url": nexus_url,
                "requires_premium": True,
            }

        # Pick the CDN with lowest latency or first available
        download_url = links[0].get("URI", "")
        if not download_url:
            return {"success": False, "error": "No download URL returned", "nexus_url": nexus_url}

        os.makedirs(temp_dir, exist_ok=True)
        dest_path = os.path.join(temp_dir, file_name)

        if progress_callback:
            progress_callback(15, f"Downloading {file_name}…")

        def _inner_progress(pct):
            if progress_callback:
                # Map download progress (0-100) into 15-95 range
                progress_callback(15 + int(pct * 0.80), f"Downloading… {pct}%")

        result = self.download_file(download_url, dest_path, progress_callback=_inner_progress)
        if not result.get("success"):
            return {"success": False, "error": result.get("message", "Download failed"), "nexus_url": nexus_url}

        if progress_callback:
            progress_callback(95, "Download complete")

        # Fetch the canonical mod-page version from the Nexus API so callers
        # can store it as the single source of truth for version comparison.
        mod_info = self.get_mod_info(domain, mod_id)
        api_version = mod_info.get("version", "") if "error" not in mod_info else ""

        return {
            "success": True,
            "zip_path": dest_path,
            "version": file_version,
            "file_name": file_name,
            "api_version": api_version,
        }

    def download_file(self, url: str, dest_path: str, progress_callback=None) -> dict:
        """Download a file from a URL with progress reporting."""
        self._ensure_token()
        try:
            # Encode any non-ASCII / space characters in the URL path+query while
            # leaving the scheme, host, and already-encoded sequences intact.
            parsed = urllib.parse.urlsplit(url)
            encoded_path = urllib.parse.quote(parsed.path, safe="/:@!$&'()*+,;=")
            url = urllib.parse.urlunsplit(parsed._replace(path=encoded_path))
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            progress_callback(int(downloaded / total * 100))
            return {"success": True, "path": dest_path}
        except Exception as e:
            return {"success": False, "message": str(e)}
