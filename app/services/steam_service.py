"""
Steam API service — player counts and cover art.
"""

import json
import urllib.request
from pathlib import Path

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps"


def get_player_count(steam_app_id: int) -> int | None:
    if not steam_app_id:
        return None
    try:
        url = f"{STEAM_API_BASE}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={steam_app_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "FromSoftModManager/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("response", {}).get("result") == 1:
                return data["response"].get("player_count", 0)
    except Exception:
        pass
    return None


def get_cover_art_url(steam_app_id: int) -> str:
    return f"{STEAM_CDN}/{steam_app_id}/library_600x900.jpg"


def download_cover_art(steam_app_id: int, save_path: str) -> bool:
    """Download cover art to save_path. Returns True on success."""
    url = get_cover_art_url(steam_app_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FromSoftModManager/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(data)
            return True
    except Exception:
        return False
