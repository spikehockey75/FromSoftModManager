"""
Mod Engine 2 detection, game folder scanning, and migration to ME3.
Scans for ME2 installations and loose mods in game directories, then creates
equivalent ME3 profiles + registers discovered mods in the app config.
Non-destructive: never modifies or deletes ME2 files or game files.
"""

import glob
import os
import tomllib

from app.core.me3_service import (
    ME3_GAME_MAP, slugify, write_me3_profile,
)

# Map ME2 config filename suffixes → our internal game_id
ME2_GAME_MAP = {
    "armoredcore6": "ac6",
    "darksouls3": "ds3",
    "darksoulsremastered": "dsr",
    "eldenring": "er",
}

# Co-op launcher DLL stems — these are managed by the app already
_COOP_DLL_STEMS = {"ds3sc", "ersc", "nrsc", "ds1sc", "ac6_for_coop"}

# Folders to skip when scanning game directories for loose mods
# Includes base game asset directories (chr, parts, etc.) which contain .dcx
# files but are NOT mods.
_SKIP_GAME_DIRS = {
    "seamlesscoop", "ac6coop", "easyanticheat", "logs", "crashpad",
    "crashdumps", "movie", "locale",
    # Base game asset directories
    "chr", "parts", "param", "sfx", "map", "obj", "menu", "msg",
    "shader", "sound", "event", "script", "action",
}

# FromSoft asset subdirectory names that indicate a mod folder
_ASSET_SUBDIRS = {"chr", "parts", "param", "sfx", "map", "obj", "menu", "msg",
                  "shader", "sound", "event", "script", "action"}


# ---------------------------------------------------------------------------
# ME2 detection
# ---------------------------------------------------------------------------

def find_me2_installations(extra_paths: list[str] | None = None) -> list[str]:
    """Return directories containing a valid ME2 installation."""
    candidates: list[str] = []

    home = os.path.expanduser("~")
    for base in [home, os.path.join(home, "Desktop"), "C:\\"]:
        candidates.extend(glob.glob(os.path.join(base, "ModEngine-2*")))

    prog = os.environ.get("PROGRAMFILES", "")
    if prog:
        candidates.extend(glob.glob(os.path.join(prog, "ModEngine-2*")))

    if extra_paths:
        candidates.extend(extra_paths)

    confirmed = []
    seen = set()
    for path in candidates:
        normed = os.path.normpath(path).lower()
        if normed in seen:
            continue
        seen.add(normed)
        real = os.path.normpath(path)
        if os.path.isdir(real) and os.path.isfile(
            os.path.join(real, "modengine2_launcher.exe")
        ):
            confirmed.append(real)
    return confirmed


# ---------------------------------------------------------------------------
# ME2 TOML parsing
# ---------------------------------------------------------------------------

def parse_me2_config(toml_path: str, me2_dir: str) -> dict | None:
    """Parse a single ME2 config TOML file.

    Returns a dict with game_id, packages (asset mods), and natives (DLL mods),
    or None if the config has no real mod content.
    """
    basename = os.path.basename(toml_path)
    if not basename.startswith("config_") or not basename.endswith(".toml"):
        return None
    game_suffix = basename[len("config_"):-len(".toml")]
    game_id = ME2_GAME_MAP.get(game_suffix)
    if not game_id:
        return None

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    # Extract DLL mods (skip known co-op launchers)
    raw_dlls = data.get("modengine", {}).get("external_dlls", [])
    natives: list[str] = []
    for dll_path in raw_dlls:
        if not dll_path:
            continue
        abs_path = _resolve_path(dll_path, me2_dir)
        if not os.path.isfile(abs_path):
            continue
        stem = os.path.splitext(os.path.basename(abs_path))[0].lower()
        if stem in _COOP_DLL_STEMS:
            continue  # co-op DLL — already managed by the app
        natives.append(abs_path)

    # Extract asset mods
    mod_loader = data.get("extension", {}).get("mod_loader", {})
    raw_mods = mod_loader.get("mods", [])
    packages: list[dict] = []
    for entry in raw_mods:
        if not entry.get("enabled", True):
            continue
        mod_path = entry.get("path", "")
        if not mod_path:
            continue
        abs_path = _resolve_path(mod_path, me2_dir)
        if not os.path.isdir(abs_path):
            continue
        name = entry.get("name", os.path.basename(abs_path))
        # Skip the ME2 default template entry ("default" pointing to base mod/ dir)
        if name == "default" and os.path.normpath(abs_path) == os.path.normpath(
            os.path.join(me2_dir, "mod")
        ):
            continue
        packages.append({"name": name, "path": abs_path})

    if not natives and not packages:
        return None

    return {
        "game_id": game_id,
        "game_suffix": game_suffix,
        "packages": packages,
        "natives": natives,
    }


def scan_me2_installation(me2_dir: str) -> list[dict]:
    """Scan an ME2 directory for all game configs with real mods."""
    results = []
    for toml_file in sorted(glob.glob(os.path.join(me2_dir, "config_*.toml"))):
        parsed = parse_me2_config(toml_file, me2_dir)
        if parsed:
            results.append(parsed)
    return results


# ---------------------------------------------------------------------------
# Game folder scanning
# ---------------------------------------------------------------------------

def scan_game_folders(config) -> list[dict]:
    """Scan game install directories for loose mod folders not yet registered.

    Looks for subdirectories in {install_path}/Game/ that contain
    FromSoft asset structure (chr/, parts/, param/, etc.) or regulation.bin.
    """
    from app.config.game_definitions import GAME_DEFINITIONS

    results = []
    games = config.get_games()

    for game_id, game_info in games.items():
        install_path = game_info.get("install_path", "")
        if not install_path or not os.path.isdir(install_path):
            continue

        game_dir = os.path.join(install_path, "Game")
        if not os.path.isdir(game_dir):
            continue

        existing_mods = config.get_game_mods(game_id)
        existing_paths = {os.path.normpath(m.get("path", "")).lower()
                          for m in existing_mods}

        # Also skip the game's own mod marker directory
        gdef = GAME_DEFINITIONS.get(game_id, {})
        marker_rel = gdef.get("mod_marker_relative", "")
        if marker_rel:
            marker_abs = os.path.normpath(
                os.path.join(install_path, marker_rel)
            ).lower()
            existing_paths.add(marker_abs)

        packages: list[dict] = []
        for entry in os.scandir(game_dir):
            if not entry.is_dir():
                continue
            if entry.name.lower() in _SKIP_GAME_DIRS:
                continue
            entry_norm = os.path.normpath(entry.path).lower()
            if entry_norm in existing_paths:
                continue

            # Check if this looks like a mod folder
            if _is_mod_folder(entry.path):
                packages.append({"name": entry.name, "path": entry.path})

        if packages:
            results.append({
                "game_id": game_id,
                "game_suffix": "",
                "packages": packages,
                "natives": [],
            })

    return results


def _is_mod_folder(path: str) -> bool:
    """Check if a directory looks like a FromSoft mod folder."""
    try:
        entries = set(e.name.lower() for e in os.scandir(path))
    except OSError:
        return False

    # Has FromSoft asset subdirs?
    if entries & _ASSET_SUBDIRS:
        return True

    # Contains regulation.bin?
    if "regulation.bin" in entries:
        return True

    # Contains .dcx files?
    for name in entries:
        if name.endswith(".dcx"):
            return True

    return False


# ---------------------------------------------------------------------------
# Merge scan results
# ---------------------------------------------------------------------------

def merge_scan_results(*sources: list[dict]) -> dict[str, dict]:
    """Merge multiple scan result lists into a dict keyed by game_id.

    Deduplicates packages by normalized path (case-insensitive on Windows).
    """
    merged: dict[str, dict] = {}
    for source in sources:
        for gc in source:
            gid = gc["game_id"]
            if gid not in merged:
                merged[gid] = {"game_id": gid, "packages": [], "natives": []}
            seen_paths = {os.path.normpath(p["path"]).lower()
                          for p in merged[gid]["packages"]}
            for pkg in gc["packages"]:
                if os.path.normpath(pkg["path"]).lower() not in seen_paths:
                    merged[gid]["packages"].append(pkg)
                    seen_paths.add(os.path.normpath(pkg["path"]).lower())
            seen_dlls = {os.path.normpath(d).lower()
                         for d in merged[gid]["natives"]}
            for dll in gc["natives"]:
                if os.path.normpath(dll).lower() not in seen_dlls:
                    merged[gid]["natives"].append(dll)
                    seen_dlls.add(os.path.normpath(dll).lower())
    return merged


# ---------------------------------------------------------------------------
# Migration (selective)
# ---------------------------------------------------------------------------

def migrate_selected(
    game_configs: dict[str, dict],
    selected_game_ids: set[str],
    me3_exe_path: str,
    config,
) -> dict:
    """Migrate selected games' mods to ME3 profiles and register in app config.

    game_configs: merged dict from merge_scan_results() keyed by game_id
    selected_game_ids: set of game_ids the user chose to import
    """
    games_migrated = []
    mods_imported = []

    for game_id in selected_game_ids:
        gc = game_configs.get(game_id)
        if not gc or game_id not in ME3_GAME_MAP:
            continue

        existing_mods = config.get_game_mods(game_id)
        existing_paths = {os.path.normpath(m.get("path", "")).lower()
                          for m in existing_mods}

        game_had_new = False

        # Process asset packages
        for pkg in gc["packages"]:
            abs_path = os.path.normpath(pkg["path"])
            if abs_path.lower() in existing_paths:
                continue
            mod_id = slugify(pkg["name"])
            config.add_or_update_game_mod(game_id, {
                "id": mod_id,
                "name": pkg["name"],
                "version": None,
                "path": abs_path,
                "nexus_domain": "",
                "nexus_mod_id": 0,
                "enabled": True,
            })
            mods_imported.append({"game": game_id, "name": pkg["name"], "type": "package"})
            game_had_new = True

        # Process native DLLs
        for dll in gc["natives"]:
            abs_dll = os.path.normpath(dll)
            if abs_dll.lower() in existing_paths:
                continue
            dll_name = os.path.basename(os.path.dirname(abs_dll))
            if not dll_name:
                dll_name = os.path.splitext(os.path.basename(abs_dll))[0]
            mod_id = slugify(dll_name)
            config.add_or_update_game_mod(game_id, {
                "id": mod_id,
                "name": dll_name,
                "version": None,
                "path": abs_dll,
                "nexus_domain": "",
                "nexus_mod_id": 0,
                "enabled": True,
            })
            mods_imported.append({"game": game_id, "name": dll_name, "type": "native"})
            game_had_new = True

        if game_had_new:
            _rebuild_me3_profile(game_id, me3_exe_path, config)
            games_migrated.append(game_id)

    return {
        "success": True,
        "games_migrated": games_migrated,
        "mods_imported": mods_imported,
    }


def _rebuild_me3_profile(game_id: str, me3_exe_path: str, config):
    """Rebuild ME3 profile for a game from all enabled mods in config."""
    all_mods = config.get_game_mods(game_id)
    pkg_paths = []
    native_paths = []
    for m in all_mods:
        if not m.get("enabled", True):
            continue
        p = m.get("path", "")
        if not p:
            continue
        if p.lower().endswith(".dll"):
            native_paths.append(p)
        elif os.path.isdir(p):
            # Scan for DLLs to load as natives
            dlls = _find_dlls_in_mod(p)
            if dlls:
                native_paths.extend(dlls)
            # Only add as package if it has asset content
            if _has_asset_content(p):
                pkg_paths.append(p)
    write_me3_profile(game_id, pkg_paths, me3_exe_path, native_dlls=native_paths)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_dlls_in_mod(mod_dir: str) -> list[str]:
    """Find DLL files in a mod directory (one level deep)."""
    dlls = []
    try:
        for entry in os.scandir(mod_dir):
            if entry.is_file() and entry.name.lower().endswith(".dll"):
                dlls.append(entry.path)
            elif entry.is_dir():
                for sub in os.scandir(entry.path):
                    if sub.is_file() and sub.name.lower().endswith(".dll"):
                        dlls.append(sub.path)
    except OSError:
        pass
    return dlls


def _has_asset_content(mod_dir: str) -> bool:
    """Check if a mod directory has FromSoft asset override content."""
    try:
        entries = {e.name.lower() for e in os.scandir(mod_dir)}
    except OSError:
        return False
    if entries & _ASSET_SUBDIRS:
        return True
    if "regulation.bin" in entries:
        return True
    return any(n.endswith(".dcx") for n in entries)


def _resolve_path(rel_path: str, base_dir: str) -> str:
    """Resolve a potentially relative path against a base directory."""
    cleaned = rel_path.replace("/", os.sep).replace("\\", os.sep)
    if os.path.isabs(cleaned):
        return os.path.normpath(cleaned)
    return os.path.normpath(os.path.join(base_dir, cleaned))
