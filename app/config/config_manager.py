"""
Configuration manager — handles app-level config (config.json) and QSettings.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

APP_NAME = "FromSoftModManager"

# When running as a PyInstaller build, __file__ resolves inside _internal/
# which is wrong for user data.  Use the exe directory instead so that
# config.json and mods/ live next to the exe and persist across updates.
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_FILE = os.path.join(_APP_DIR, "config.json")
_DEFAULT_MODS_DIR = os.path.join(_APP_DIR, "mods")


class ConfigManager:
    def __init__(self):
        self._migrate_legacy_config()
        self._config = self._load()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------
    @staticmethod
    def _migrate_legacy_config():
        """Move config.json out of _internal/ if it was created there by an
        older build.  Only relevant for PyInstaller builds."""
        if not getattr(sys, "frozen", False):
            return
        legacy = os.path.join(os.path.dirname(sys.executable), "_internal", "config.json")
        if os.path.isfile(legacy) and not os.path.isfile(CONFIG_FILE):
            try:
                import shutil
                shutil.move(legacy, CONFIG_FILE)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Low-level load / save
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if os.path.isfile(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"games": {}, "last_scan": None}

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2)

    def reload(self):
        self._config = self._load()

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------
    def get_games(self) -> dict:
        return self._config.get("games", {})

    def set_games(self, games: dict):
        # Preserve app-managed fields that the scanner doesn't know about
        existing = self._config.get("games", {})
        _preserve = ("mods", "installed_mod_version")
        for game_id, new_info in games.items():
            if game_id in existing:
                for key in _preserve:
                    if key in existing[game_id]:
                        new_info[key] = existing[game_id][key]
        self._config["games"] = games
        self._config["last_scan"] = datetime.now().isoformat()
        self.save()

    def get_game(self, game_id: str) -> dict | None:
        return self._config.get("games", {}).get(game_id)

    def update_game(self, game_id: str, data: dict):
        if "games" not in self._config:
            self._config["games"] = {}
        if game_id not in self._config["games"]:
            self._config["games"][game_id] = {}
        self._config["games"][game_id].update(data)
        self.save()

    def get_last_scan(self) -> str | None:
        return self._config.get("last_scan")

    # ------------------------------------------------------------------
    # Nexus
    # ------------------------------------------------------------------
    def get_nexus_api_key(self) -> str:
        return self._config.get("nexus_api_key", "")

    def set_nexus_api_key(self, key: str):
        self._config["nexus_api_key"] = key
        self.save()

    def get_nexus_user_info(self) -> dict:
        return self._config.get("nexus_user", {})

    def set_nexus_user_info(self, info: dict):
        self._config["nexus_user"] = info
        self.save()

    def clear_nexus_auth(self):
        self._config.pop("nexus_api_key", None)
        self._config.pop("nexus_user", None)
        self.save()

    # ------------------------------------------------------------------
    # ME3
    # ------------------------------------------------------------------
    def get_me3_path(self) -> str:
        return self._config.get("me3_path", "")

    def set_me3_path(self, path: str):
        self._config["me3_path"] = path
        self.save()

    def get_use_me3(self) -> bool:
        return self._config.get("use_me3", True)

    def set_use_me3(self, value: bool):
        self._config["use_me3"] = value
        self.save()

    # ------------------------------------------------------------------
    # Mods directory
    # ------------------------------------------------------------------
    def get_mods_dir(self) -> str:
        return self._config.get("mods_dir", _DEFAULT_MODS_DIR)

    def set_mods_dir(self, path: str):
        self._config["mods_dir"] = path
        self.save()

    def get_game_mod_dir(self, game_id: str) -> str:
        return os.path.join(self.get_mods_dir(), game_id)

    # ------------------------------------------------------------------
    # Per-game mod list (multi-mod support)
    # ------------------------------------------------------------------
    def get_game_mods(self, game_id: str) -> list:
        """Return installed mods list for a game. Auto-migrates legacy config."""
        game = self.get_game(game_id) or {}
        mods = game.get("mods")
        if mods is not None:
            return mods
        # Migrate legacy single-mod config
        if game.get("mod_installed"):
            from app.config.game_definitions import GAME_DEFINITIONS
            gdef = GAME_DEFINITIONS.get(game_id, {})
            # Prefer the app's managed mod dir; fall back to the game's on-disk
            # marker directory so a fresh install finds the actual DLLs.
            mod_dir = os.path.join(self.get_game_mod_dir(game_id), f"{game_id}-coop")
            if not os.path.isdir(mod_dir):
                marker_rel = gdef.get("mod_marker_relative", "")
                install_path = game.get("install_path", "")
                if marker_rel and install_path:
                    candidate = os.path.join(install_path, marker_rel)
                    if os.path.isdir(candidate):
                        mod_dir = candidate
            migrated = {
                "id": f"{game_id}-coop",
                "name": gdef.get("mod_name", "Co-op Mod"),
                "version": game.get("installed_mod_version"),
                "path": mod_dir,
                "nexus_domain": gdef.get("nexus_domain", ""),
                "nexus_mod_id": gdef.get("nexus_mod_id", 0),
                "enabled": True,
            }
            self.update_game(game_id, {"mods": [migrated]})
            return [migrated]
        return []

    def add_or_update_game_mod(self, game_id: str, mod_dict: dict):
        """Upsert a mod entry by id."""
        game = self.get_game(game_id) or {}
        mods = game.get("mods", [])
        idx = next((i for i, m in enumerate(mods) if m["id"] == mod_dict["id"]), None)
        if idx is not None:
            mods[idx] = mod_dict
        else:
            mods.append(mod_dict)
        self.update_game(game_id, {"mods": mods})

    def remove_game_mod(self, game_id: str, mod_id: str):
        """Remove a mod entry by id."""
        game = self.get_game(game_id) or {}
        mods = [m for m in game.get("mods", []) if m["id"] != mod_id]
        self.update_game(game_id, {"mods": mods})

    def set_mod_enabled(self, game_id: str, mod_id: str, enabled: bool):
        """Toggle enabled flag on a mod entry."""
        game = self.get_game(game_id) or {}
        mods = game.get("mods", [])
        for m in mods:
            if m["id"] == mod_id:
                m["enabled"] = enabled
                break
        self.update_game(game_id, {"mods": mods})

    # ------------------------------------------------------------------
    # UI preferences
    # ------------------------------------------------------------------
    def get_ui_scale(self) -> float:
        return float(self._config.get("ui_scale", 1.0))

    def set_ui_scale(self, scale: float):
        self._config["ui_scale"] = scale
        self.save()

    # ------------------------------------------------------------------
    # Raw access
    # ------------------------------------------------------------------
    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def set(self, key: str, value):
        self._config[key] = value
        self.save()
