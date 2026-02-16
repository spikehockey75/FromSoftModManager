import os
import sys
import json
import re
import string
import glob
import shutil
import socket
import subprocess
import zipfile
import webbrowser
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

GAME_DEFINITIONS = {
    "ac6": {
        "name": "Armored Core 6",
        "steam_app_id": 1888160,
        "steam_folder": "ARMORED CORE VI FIRES OF RUBICON",
        "config_relative": os.path.join("Game", "AC6Coop", "ac6_coop_settings.ini"),
        "mod_extract_relative": "Game",
        "save_appdata_folder": "ArmoredCore6",
        "save_prefix": "AC60000",
        "base_ext": ".sl2",
        "coop_ext": ".co2",
        "mod_name": "AC6 Seamless Co-op",
        "nexus_url": "https://www.nexusmods.com/armoredcore6firesofrubicon/mods/22",
        "zip_pattern": r"ac6.*coop.*\.zip$",
        "launcher_relative": os.path.join("Game", "ac6_for_coop_launcher.exe"),
        "mod_marker_relative": os.path.join("Game", "AC6Coop"),
        "defaults": {
            "enemy_health_scaling": "100",
            "enemy_posture_scaling": "100",
            "enemy_damage_scaling": "0",
            "display_party_members": "1",
            "enable_friendly_fire": "0",
            "auto_mission_failure_on_death": "0",
            "allow_evil_guest": "0",
            "mod_language_override": "",
        },
    },
    "ds3": {
        "name": "Dark Souls III",
        "steam_app_id": 374320,
        "steam_folder": "DARK SOULS III",
        "config_relative": os.path.join("Game", "SeamlessCoop", "ds3sc_settings.ini"),
        "mod_extract_relative": "Game",
        "save_appdata_folder": "DarkSoulsIII",
        "save_prefix": "DS30000",
        "base_ext": ".sl2",
        "coop_ext": ".co2",
        "mod_name": "DS3 Seamless Co-op",
        "nexus_url": "https://www.nexusmods.com/darksouls3/mods/1895",
        "zip_pattern": r"ds3.*coop.*\.zip$|seamless.*co-?op.*1895.*\.zip$",
        "launcher_relative": os.path.join("Game", "ds3sc_launcher.exe"),
        "mod_marker_relative": os.path.join("Game", "SeamlessCoop"),
        "defaults": {
            "allow_invaders": "1",
            "death_debuffs": "1",
            "overhead_player_display": "2",
            "skip_intros": "1",
            "sync_progress_as_guest": "1",
            "game_boot_volume": "5",
            "enemy_health_scaling": "35",
            "enemy_damage_scaling": "0",
            "enemy_posture_scaling": "15",
            "boss_health_scaling": "100",
            "boss_damage_scaling": "0",
            "boss_posture_scaling": "20",
            "cooppassword": "",
            "save_file_extension": "co2",
            "mod_language_override": "",
        },
    },
    "er": {
        "name": "Elden Ring",
        "steam_app_id": 1245620,
        "steam_folder": "ELDEN RING",
        "config_relative": os.path.join("Game", "SeamlessCoop", "ersc_settings.ini"),
        "mod_extract_relative": "Game",
        "save_appdata_folder": "EldenRing",
        "save_prefix": "ER0000",
        "base_ext": ".sl2",
        "coop_ext": ".co2",
        "mod_name": "Elden Ring Seamless Co-op",
        "nexus_url": "https://www.nexusmods.com/eldenring/mods/510",
        "zip_pattern": r"elden.*seamless.*\.zip$|ersc.*\.zip$|seamless.*co-?op.*510.*\.zip$",
        "launcher_relative": os.path.join("Game", "ersc_launcher.exe"),
        "mod_marker_relative": os.path.join("Game", "SeamlessCoop"),
        "defaults": {
            "allow_invaders": "1",
            "death_debuffs": "1",
            "allow_summons": "1",
            "overhead_player_display": "0",
            "skip_splash_screens": "1",
            "enemy_health_scaling": "35",
            "enemy_damage_scaling": "0",
            "enemy_posture_scaling": "15",
            "boss_health_scaling": "100",
            "boss_damage_scaling": "0",
            "boss_posture_scaling": "20",
            "cooppassword": "",
            "save_file_extension": "co2",
            "mod_language_override": "",
        },
    },
}

# ---------------------------------------------------------------------------
# Drive / Steam library scanning
# ---------------------------------------------------------------------------

def get_windows_drives():
    """Return a list of available drive root paths (e.g. ['C:\\', 'D:\\'])."""
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
            # Fallback: brute-force check
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    drives.append(root)
    else:
        # Posix-ish fallback (WSL, Git Bash mapped drives)
        for letter in string.ascii_uppercase:
            for prefix in [f"/mnt/{letter.lower()}", f"/{letter.lower()}"]:
                if os.path.isdir(prefix):
                    drives.append(prefix)
    return drives


def parse_library_folders_vdf(vdf_path):
    """Extract Steam library paths from libraryfolders.vdf."""
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


def find_steam_libraries():
    """Return a de-duplicated list of Steam library root directories."""
    library_dirs = set()
    drives = get_windows_drives()

    # Common Steam install locations to probe on every drive
    probe_patterns = [
        "Steam",
        "SteamLibrary",
        os.path.join("Program Files", "Steam"),
        os.path.join("Program Files (x86)", "Steam"),
    ]

    for drive in drives:
        for pattern in probe_patterns:
            candidate = os.path.join(drive, pattern)
            if os.path.isdir(candidate):
                library_dirs.add(os.path.normpath(candidate))
                # Also try to parse libraryfolders.vdf for extra libraries
                vdf = os.path.join(candidate, "steamapps", "libraryfolders.vdf")
                if os.path.isfile(vdf):
                    for p in parse_library_folders_vdf(vdf):
                        if os.path.isdir(p):
                            library_dirs.add(os.path.normpath(p))

    return list(library_dirs)


def scan_for_games():
    """Scan all Steam libraries for FromSoft games (with or without mod). Returns dict."""
    libraries = find_steam_libraries()
    found_games = {}

    for lib_dir in libraries:
        steamapps_dir = os.path.join(lib_dir, "steamapps")
        common_dir = os.path.join(steamapps_dir, "common")
        if not os.path.isdir(common_dir):
            continue

        for game_id, gdef in GAME_DEFINITIONS.items():
            if game_id in found_games:
                continue  # already found this game
            game_dir = os.path.join(common_dir, gdef["steam_folder"])
            if not os.path.isdir(game_dir):
                continue
            # Verify the game is actually installed via Steam's appmanifest
            app_id = gdef.get("steam_app_id")
            if app_id:
                manifest = os.path.join(steamapps_dir, f"appmanifest_{app_id}.acf")
                if not os.path.isfile(manifest):
                    continue  # leftover folder from uninstall

            # Check if mod is installed
            config_path = os.path.join(game_dir, gdef["config_relative"])
            mod_installed = os.path.isfile(config_path)
            launcher_path = os.path.join(game_dir, gdef["launcher_relative"])
            mod_marker = os.path.join(game_dir, gdef["mod_marker_relative"])

            # Detect save directory
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
            }

    return found_games


def detect_save_dir(appdata_folder):
    """Find the save directory under %APPDATA%/<folder>/<SteamID>/."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    base = os.path.join(appdata, appdata_folder)
    if not os.path.isdir(base):
        return None
    # Find first subfolder that looks like a Steam ID (numeric or hex)
    for entry in os.listdir(base):
        full = os.path.join(base, entry)
        if os.path.isdir(full) and re.fullmatch(r'[0-9a-fA-F]+', entry):
            return os.path.normpath(full)
    return None


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def load_config():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"games": {}, "last_scan": None}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# INI parser – reads file preserving comment → setting association
# ---------------------------------------------------------------------------

def extract_options_from_comment(text):
    """Try to pull selectable options from a comment string.

    Looks for patterns like:
      ``0=FALSE  1=TRUE``
      ``0 = Disabled | 1 = Enabled (no lock-on) | 2 = Enabled (with lock-on)``
    Returns list of {value, label} dicts or None.
    """
    # Pipe-separated: "0 = A | 1 = B | 2 = C"
    # First, find the options substring (everything from the first "N =" pattern onward)
    opts_start = re.search(r'(\d+)\s*=\s*', text)
    if opts_start:
        opts_text = text[opts_start.start():]
        pipe_parts = re.split(r'\s*\|\s*', opts_text)
        if len(pipe_parts) >= 2:
            opts = []
            for part in pipe_parts:
                m = re.match(r'(\d+)\s*=\s*(.+)', part.strip())
                if m:
                    label = m.group(2).strip()
                    # Strip trailing ) only if it's an unmatched close-paren
                    if label.endswith(')') and '(' not in label:
                        label = label.rstrip(')')
                    opts.append({"value": m.group(1).strip(), "label": label})
            # Only treat as select if we have at least 3 options OR
            # all option values are consecutive small integers (enum-like)
            if len(opts) >= 3:
                return opts
            if len(opts) == 2:
                vals = sorted(int(o["value"]) for o in opts)
                # If values are 0,1 or similar small consecutive → select
                # If values span a wide range (e.g. 0,10) → probably a range, not a select
                if vals[-1] - vals[0] <= 2:
                    return opts

    # Space/double-space separated: "0=FALSE  1=TRUE"
    matches = re.findall(r'(\d+)\s*=\s*([A-Za-z][A-Za-z_ ()\-]*?)(?:\s{2,}|\s*$)', text)
    if len(matches) >= 2:
        vals = sorted(int(v) for v, _ in matches)
        if vals[-1] - vals[0] <= len(matches):
            return [{"value": v.strip(), "label": l.strip()} for v, l in matches]

    return None


def extract_range_from_comment(text):
    """Try to pull min/max from comment text."""
    m = re.search(r'(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)', text, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Also look for "(0 = Mute | 10 = max)" style range hints
    m = re.search(r'\((\d+)\s*=\s*\w+\s*\|\s*(\d+)\s*=\s*\w+', text)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        if high - low > 2:  # wide range, treat as min/max
            return low, high
    return None, None


def infer_field_meta(key, value, description):
    """Return (type, options, min, max) for a setting."""
    options = extract_options_from_comment(description) if description else None
    if options:
        return "select", options, None, None

    # Boolean-style: comment says "If enabled" / "if set to 1" and value is 0 or 1
    if description and value.strip() in ("0", "1"):
        if re.search(r'(if enabled|if set to 1|0\s*=\s*false)', description, re.IGNORECASE):
            bool_opts = [{"value": "0", "label": "Disabled"}, {"value": "1", "label": "Enabled"}]
            return "select", bool_opts, None, None

    low, high = extract_range_from_comment(description) if description else (None, None)

    if value.strip().lstrip('-').isdigit():
        return "number", None, low, high

    if "password" in key.lower():
        return "text", None, None, None

    return "text", None, None, None


def parse_ini_file(file_path, defaults_dict=None):
    """Parse an INI file into structured sections with metadata.
    
    If defaults_dict is provided, each setting will include a 'default' field.
    Also extracts defaults from comments containing '(Default: N)' patterns.
    """
    if defaults_dict is None:
        defaults_dict = {}
    sections = []
    current_section = None
    comment_buffer = []

    with open(file_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    for raw_line in lines:
        line = raw_line.rstrip("\n\r")
        stripped = line.strip()

        # Blank line → reset comment buffer
        if not stripped:
            comment_buffer = []
            continue

        # Section header
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1]
            current_section = {"name": section_name, "settings": []}
            sections.append(current_section)
            comment_buffer = []
            continue

        # Comment line
        if stripped.startswith(";"):
            comment_buffer.append(stripped.lstrip("; ").strip())
            continue

        # Key = value
        if "=" in stripped and current_section is not None:
            key, _, val = stripped.partition("=")
            key = key.strip()
            val = val.strip()
            description = " ".join(comment_buffer).strip()
            comment_buffer = []

            field_type, options, low, high = infer_field_meta(key, val, description)

            # Determine default value: hardcoded > comment-extracted
            default_val = defaults_dict.get(key)
            if default_val is None and description:
                m = re.search(r'\bdefault[:\s]+(\d+)', description, re.IGNORECASE)
                if m:
                    default_val = m.group(1)

            setting = {
                "key": key,
                "value": val,
                "description": description,
                "type": field_type,
            }
            if default_val is not None:
                setting["default"] = default_val
            if options:
                setting["options"] = options
            if low is not None:
                setting["min"] = low
            if high is not None:
                setting["max"] = high

            current_section["settings"].append(setting)

    return sections


def save_ini_settings(file_path, settings_dict):
    """Write changed values back to INI while preserving comments/format."""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    new_lines = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped and not stripped.startswith(";") and not stripped.startswith("[") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in settings_dict:
                indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
                new_lines.append(f"{indent}{key} = {settings_dict[key]}\n")
                continue
        new_lines.append(raw_line)

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/games")
def api_games():
    """Return currently known games, pruning any that are no longer installed."""
    cfg = load_config()
    games = cfg.get("games", {})
    pruned = []
    for gid in list(games.keys()):
        install_path = games[gid].get("install_path", "")
        if not install_path or not os.path.isdir(install_path):
            pruned.append(games.pop(gid))
            continue
        # Check Steam appmanifest — the folder can linger after uninstall
        app_id = games[gid].get("steam_app_id")
        if app_id:
            steamapps_dir = os.path.normpath(os.path.join(install_path, "..", ".."))
            manifest = os.path.join(steamapps_dir, f"appmanifest_{app_id}.acf")
            if not os.path.isfile(manifest):
                pruned.append(games.pop(gid))
                continue
    if pruned:
        save_config(cfg)           # persist the cleanup
    return jsonify(cfg)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scan all drives for FromSoft co-op mods, update config."""
    found = scan_for_games()
    cfg = {
        "games": found,
        "last_scan": datetime.now().isoformat(),
    }
    save_config(cfg)
    return jsonify(cfg)


@app.route("/api/settings/<game_id>")
def api_get_settings(game_id):
    """Read settings from a game's INI file."""
    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return jsonify({"error": "Game not found in config"}), 404
    config_path = game["config_path"]
    if not os.path.isfile(config_path):
        return jsonify({"error": f"Config file not found: {config_path}"}), 404

    gdef = GAME_DEFINITIONS.get(game_id, {})
    defaults_dict = gdef.get("defaults", {})
    sections = parse_ini_file(config_path, defaults_dict)
    return jsonify({
        "game_id": game_id,
        "name": game["name"],
        "config_path": config_path,
        "sections": sections,
    })


@app.route("/api/settings/<game_id>", methods=["POST"])
def api_save_settings(game_id):
    """Save settings back to a game's INI file."""
    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return jsonify({"error": "Game not found in config"}), 404
    config_path = game["config_path"]
    if not os.path.isfile(config_path):
        return jsonify({"error": f"Config file not found: {config_path}"}), 404

    settings_dict = request.json
    if not settings_dict or not isinstance(settings_dict, dict):
        return jsonify({"error": "Invalid payload"}), 400

    save_ini_settings(config_path, settings_dict)
    return jsonify({"status": "ok", "message": f"Settings saved for {game['name']}"})


# ---------------------------------------------------------------------------
# Save Manager functions
# ---------------------------------------------------------------------------

def _get_game_save_info(game_id):
    """Return game dict + save dir + prefix/ext info, or (None, error_msg)."""
    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return None, "Game not found in config. Run a scan first."
    save_dir = game.get("save_dir")
    if not save_dir or not os.path.isdir(save_dir):
        return None, f"Save directory not found: {save_dir}. Make sure the game has been launched at least once."
    return game, None


def _get_backup_dir(game, game_id):
    backup_dir = os.path.join(game["save_dir"], f"{game_id.upper()}_Backups")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _list_save_files(save_dir, prefix, ext):
    """Return list of files matching prefix+ext* (e.g. AC60000.sl2, AC60000.sl2.bak)."""
    pattern = os.path.join(save_dir, f"{prefix}{ext}*")
    return [f for f in glob.glob(pattern) if os.path.isfile(f)]


def _parse_backup_timestamps(backup_dir):
    """Return sorted list of unique timestamps found in backup dir."""
    ts_set = set()
    ts_re = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})$')
    if not os.path.isdir(backup_dir):
        return []
    for name in os.listdir(backup_dir):
        m = ts_re.search(name)
        if m:
            ts_set.add(m.group(1))
    return sorted(ts_set, reverse=True)


# ---------------------------------------------------------------------------
# Save Manager API routes
# ---------------------------------------------------------------------------

@app.route("/api/saves/<game_id>")
def api_get_saves(game_id):
    """Return save file info and list of backups for a game."""
    game, err = _get_game_save_info(game_id)
    if err:
        return jsonify({"error": err}), 404

    save_dir = game["save_dir"]
    prefix = game["save_prefix"]
    base_ext = game["base_ext"]
    coop_ext = game["coop_ext"]
    backup_dir = _get_backup_dir(game, game_id)

    # Current save files
    base_files = []
    for f in _list_save_files(save_dir, prefix, base_ext):
        stat = os.stat(f)
        base_files.append({
            "name": os.path.basename(f),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    coop_files = []
    for f in _list_save_files(save_dir, prefix, coop_ext):
        stat = os.stat(f)
        coop_files.append({
            "name": os.path.basename(f),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    # Backups
    timestamps = _parse_backup_timestamps(backup_dir)
    backups = []
    for ts in timestamps:
        base_count = len([n for n in os.listdir(backup_dir)
                         if n.startswith(prefix) and base_ext in n and n.endswith(ts)])
        coop_count = len([n for n in os.listdir(backup_dir)
                         if n.startswith(prefix) and coop_ext in n and n.endswith(ts)])
        backups.append({
            "timestamp": ts,
            "base_count": base_count,
            "coop_count": coop_count,
        })

    return jsonify({
        "game_id": game_id,
        "name": game["name"],
        "save_dir": save_dir,
        "backup_dir": backup_dir,
        "base_ext": base_ext,
        "coop_ext": coop_ext,
        "base_files": base_files,
        "coop_files": coop_files,
        "backups": backups,
    })


@app.route("/api/saves/<game_id>/transfer", methods=["POST"])
def api_transfer(game_id):
    """Transfer saves: base->coop or coop->base."""
    game, err = _get_game_save_info(game_id)
    if err:
        return jsonify({"error": err}), 404

    body = request.json or {}
    direction = body.get("direction")  # "base_to_coop" or "coop_to_base"
    if direction not in ("base_to_coop", "coop_to_base"):
        return jsonify({"error": "Invalid direction. Use base_to_coop or coop_to_base."}), 400

    save_dir = game["save_dir"]
    prefix = game["save_prefix"]
    base_ext = game["base_ext"]
    coop_ext = game["coop_ext"]
    backup_dir = _get_backup_dir(game, game_id)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if direction == "base_to_coop":
        src_ext, dst_ext = base_ext, coop_ext
        src_label, dst_label = "Base Game", "Co-op"
    else:
        src_ext, dst_ext = coop_ext, base_ext
        src_label, dst_label = "Co-op", "Base Game"

    # Backup destination files first
    dest_files = _list_save_files(save_dir, prefix, dst_ext)
    backed_up = 0
    for f in dest_files:
        fname = os.path.basename(f)
        shutil.copy2(f, os.path.join(backup_dir, f"{fname}_{ts}"))
        backed_up += 1

    # Transfer: copy src → dst (use copy, not copy2, so timestamps update)
    src_files = _list_save_files(save_dir, prefix, src_ext)
    transferred = 0
    for src in src_files:
        fname = os.path.basename(src)
        dst_name = fname.replace(f"{prefix}{src_ext}", f"{prefix}{dst_ext}")
        shutil.copy(src, os.path.join(save_dir, dst_name))
        transferred += 1

    if transferred == 0:
        return jsonify({"error": f"No {src_label} save files found to transfer."}), 404

    return jsonify({
        "status": "ok",
        "message": f"Transferred {transferred} file(s): {src_label} → {dst_label}",
        "backed_up": backed_up,
        "transferred": transferred,
        "backup_timestamp": ts,
    })


@app.route("/api/saves/<game_id>/backup", methods=["POST"])
def api_backup(game_id):
    """Create a backup of all save files."""
    game, err = _get_game_save_info(game_id)
    if err:
        return jsonify({"error": err}), 404

    save_dir = game["save_dir"]
    prefix = game["save_prefix"]
    base_ext = game["base_ext"]
    coop_ext = game["coop_ext"]
    backup_dir = _get_backup_dir(game, game_id)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    count = 0
    for ext in (base_ext, coop_ext):
        for f in _list_save_files(save_dir, prefix, ext):
            fname = os.path.basename(f)
            shutil.copy2(f, os.path.join(backup_dir, f"{fname}_{ts}"))
            count += 1

    if count == 0:
        return jsonify({"error": "No save files found to backup."}), 404

    return jsonify({
        "status": "ok",
        "message": f"Backed up {count} file(s)",
        "timestamp": ts,
        "count": count,
    })


@app.route("/api/saves/<game_id>/restore", methods=["POST"])
def api_restore(game_id):
    """Restore saves from a backup timestamp."""
    game, err = _get_game_save_info(game_id)
    if err:
        return jsonify({"error": err}), 404

    body = request.json or {}
    timestamp = body.get("timestamp")
    dest_type = body.get("dest_type")  # "base" or "coop"

    if not timestamp:
        return jsonify({"error": "timestamp is required."}), 400
    if dest_type not in ("base", "coop"):
        return jsonify({"error": "dest_type must be 'base' or 'coop'."}), 400

    save_dir = game["save_dir"]
    prefix = game["save_prefix"]
    base_ext = game["base_ext"]
    coop_ext = game["coop_ext"]
    backup_dir = _get_backup_dir(game, game_id)
    now_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    dst_ext = base_ext if dest_type == "base" else coop_ext
    dest_label = "Base Game" if dest_type == "base" else "Co-op"

    # Safety: backup current destination files before overwriting
    current_dest = _list_save_files(save_dir, prefix, dst_ext)
    for f in current_dest:
        fname = os.path.basename(f)
        shutil.copy2(f, os.path.join(backup_dir, f"{fname}_{now_ts}"))

    # Find backup files matching the requested timestamp
    restored = 0
    for name in os.listdir(backup_dir):
        if not name.endswith(timestamp):
            continue
        if not name.startswith(prefix):
            continue

        backup_path = os.path.join(backup_dir, name)
        # Strip the _timestamp suffix to get original filename
        original_name = name[:-(len(timestamp) + 1)]  # remove _YYYY-MM-DD_HH-MM-SS

        # Convert extension to destination type
        # The backup could be base or coop — map to requested dest
        if base_ext in original_name:
            src_ext_in_file = base_ext
        elif coop_ext in original_name:
            src_ext_in_file = coop_ext
        else:
            continue

        dest_name = original_name.replace(f"{prefix}{src_ext_in_file}", f"{prefix}{dst_ext}")
        shutil.copy2(backup_path, os.path.join(save_dir, dest_name))
        restored += 1

    if restored == 0:
        return jsonify({"error": f"No backup files found for timestamp: {timestamp}"}), 404

    return jsonify({
        "status": "ok",
        "message": f"Restored {restored} file(s) to {dest_label}",
        "restored": restored,
    })


@app.route("/api/saves/<game_id>/backup/<timestamp>", methods=["DELETE"])
def api_delete_backup(game_id, timestamp):
    """Delete all backup files for a specific timestamp."""
    game, err = _get_game_save_info(game_id)
    if err:
        return jsonify({"error": err}), 404

    backup_dir = _get_backup_dir(game, game_id)
    deleted = 0
    for name in os.listdir(backup_dir):
        if name.endswith(timestamp):
            os.remove(os.path.join(backup_dir, name))
            deleted += 1

    if deleted == 0:
        return jsonify({"error": "No files found for that timestamp."}), 404

    return jsonify({
        "status": "ok",
        "message": f"Deleted {deleted} backup file(s)",
        "deleted": deleted,
    })


# ---------------------------------------------------------------------------
# Mod Installer API routes
# ---------------------------------------------------------------------------

def _get_downloads_folder():
    """Return the user's Downloads folder path."""
    return os.path.join(os.path.expanduser("~"), "Downloads")


@app.route("/api/mod/<game_id>/status")
def api_mod_status(game_id):
    """Check mod installation status and scan Downloads for matching zips."""
    gdef = GAME_DEFINITIONS.get(game_id)
    if not gdef:
        return jsonify({"error": "Unknown game"}), 404

    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return jsonify({"error": "Game not found. Run a scan first."}), 404

    install_path = game["install_path"]
    mod_installed = game.get("mod_installed", False)
    launcher_exists = game.get("launcher_exists", False)

    # Scan Downloads folder for matching zips
    downloads_dir = _get_downloads_folder()
    available_zips = []
    if os.path.isdir(downloads_dir):
        pattern = re.compile(gdef["zip_pattern"], re.IGNORECASE)
        for fname in os.listdir(downloads_dir):
            if pattern.search(fname):
                full = os.path.join(downloads_dir, fname)
                if os.path.isfile(full):
                    stat = os.stat(full)
                    available_zips.append({
                        "name": fname,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
        # Sort by modified desc (newest first)
        available_zips.sort(key=lambda x: x["modified"], reverse=True)

    extract_target = os.path.normpath(
        os.path.join(install_path, gdef["mod_extract_relative"])
    )

    return jsonify({
        "game_id": game_id,
        "mod_name": gdef["mod_name"],
        "nexus_url": gdef["nexus_url"],
        "mod_installed": mod_installed,
        "launcher_exists": launcher_exists,
        "install_path": install_path,
        "extract_target": extract_target,
        "downloads_dir": os.path.normpath(downloads_dir),
        "available_zips": available_zips,
    })


@app.route("/api/mod/<game_id>/install", methods=["POST"])
def api_mod_install(game_id):
    """Extract a mod zip from Downloads into the game directory."""
    gdef = GAME_DEFINITIONS.get(game_id)
    if not gdef:
        return jsonify({"error": "Unknown game"}), 404

    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return jsonify({"error": "Game not found. Run a scan first."}), 404

    body = request.json or {}
    zip_name = body.get("zip_name")
    if not zip_name:
        return jsonify({"error": "zip_name is required."}), 400

    # Security: only allow files from Downloads folder, no path traversal
    safe_name = os.path.basename(zip_name)
    downloads_dir = _get_downloads_folder()
    zip_path = os.path.join(downloads_dir, safe_name)

    if not os.path.isfile(zip_path):
        return jsonify({"error": f"File not found: {safe_name}"}), 404

    if not zipfile.is_zipfile(zip_path):
        return jsonify({"error": f"Not a valid zip file: {safe_name}"}), 400

    extract_target = os.path.join(game["install_path"], gdef["mod_extract_relative"])
    os.makedirs(extract_target, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Security: check for path traversal in zip entries
            for member in zf.namelist():
                resolved = os.path.realpath(os.path.join(extract_target, member))
                if not resolved.startswith(os.path.realpath(extract_target)):
                    return jsonify({"error": f"Zip contains unsafe path: {member}"}), 400

            zf.extractall(extract_target)
            extracted_count = len([n for n in zf.namelist() if not n.endswith("/")])
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500

    # Re-check mod status and update config
    config_path = os.path.join(game["install_path"], gdef["config_relative"])
    launcher_path = os.path.join(game["install_path"], gdef["launcher_relative"])
    mod_installed = os.path.isfile(config_path)

    if game_id in cfg.get("games", {}):
        cfg["games"][game_id]["mod_installed"] = mod_installed
        cfg["games"][game_id]["config_path"] = os.path.normpath(config_path) if mod_installed else None
        cfg["games"][game_id]["launcher_exists"] = os.path.isfile(launcher_path)
        cfg["games"][game_id]["launcher_path"] = os.path.normpath(launcher_path) if os.path.isfile(launcher_path) else None
        save_config(cfg)

    return jsonify({
        "status": "ok",
        "message": f"Installed {extracted_count} file(s) from {safe_name}",
        "extracted": extracted_count,
        "zip_name": safe_name,
        "mod_installed": mod_installed,
        "launcher_exists": os.path.isfile(launcher_path),
    })


@app.route("/api/mod/<game_id>/cleanup", methods=["POST"])
def api_mod_cleanup(game_id):
    """Delete a mod zip from the Downloads folder."""
    body = request.json or {}
    zip_name = body.get("zip_name")
    if not zip_name:
        return jsonify({"error": "zip_name is required."}), 400

    safe_name = os.path.basename(zip_name)
    downloads_dir = _get_downloads_folder()
    zip_path = os.path.join(downloads_dir, safe_name)

    if not os.path.isfile(zip_path):
        return jsonify({"error": f"File not found: {safe_name}"}), 404

    try:
        os.remove(zip_path)
        return jsonify({"status": "ok", "message": f"Deleted {safe_name} from Downloads"})
    except Exception as e:
        return jsonify({"error": f"Failed to delete: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

@app.route("/api/launch/<game_id>", methods=["POST"])
def api_launch_game(game_id):
    """Launch the co-op mod launcher for a game."""
    gdef = GAME_DEFINITIONS.get(game_id)
    if not gdef:
        return jsonify({"error": "Unknown game"}), 404

    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return jsonify({"error": "Game not found. Run a scan first."}), 404

    launcher_path = game.get("launcher_path")
    if not launcher_path or not os.path.isfile(launcher_path):
        # Fallback: rebuild from install_path
        launcher_path = os.path.join(game["install_path"], gdef["launcher_relative"])
    if not os.path.isfile(launcher_path):
        return jsonify({"error": "Launcher not found. Is the mod installed?"}), 404

    try:
        subprocess.Popen(
            [launcher_path],
            cwd=os.path.dirname(launcher_path),
            creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0),
        )
        return jsonify({"status": "ok", "message": f"Launched {os.path.basename(launcher_path)}"})
    except Exception as e:
        return jsonify({"error": f"Failed to launch: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Desktop shortcut
# ---------------------------------------------------------------------------

@app.route("/api/shortcut/<game_id>", methods=["POST"])
def api_create_shortcut(game_id):
    """Create a desktop shortcut for the co-op launcher."""
    gdef = GAME_DEFINITIONS.get(game_id)
    if not gdef:
        return jsonify({"error": "Unknown game"}), 404

    cfg = load_config()
    game = cfg.get("games", {}).get(game_id)
    if not game:
        return jsonify({"error": "Game not found. Run a scan first."}), 404

    launcher_path = game.get("launcher_path")
    if not launcher_path or not os.path.isfile(launcher_path):
        launcher_path = os.path.join(game["install_path"], gdef["launcher_relative"])
    if not os.path.isfile(launcher_path):
        return jsonify({"error": "Launcher not found. Is the mod installed?"}), 404

    launcher_path = os.path.normpath(launcher_path)
    shortcut_name = f"{gdef['name']} Co-op"

    # ── Get or create a game-specific .ico from the Steam cover art ──
    app_dir = os.path.dirname(os.path.abspath(__file__))
    icons_dir = os.path.join(app_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    icon_path = os.path.join(icons_dir, f"{game_id}.ico")

    if not os.path.isfile(icon_path):
        steam_app_id = gdef.get("steam_app_id")
        if steam_app_id:
            try:
                # Download the Steam library cover art (600x900 portrait)
                cdn_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{steam_app_id}/library_600x900.jpg"
                tmp_jpg = os.path.join(icons_dir, f"{game_id}_cover.jpg")
                urllib.request.urlretrieve(cdn_url, tmp_jpg)

                # Convert to a square .ico with multiple sizes using Pillow
                from PIL import Image
                img = Image.open(tmp_jpg).convert("RGBA")
                # Center-crop to a square (take the middle portion)
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
                img.save(icon_path, format="ICO",
                         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

                # Clean up temp file
                os.remove(tmp_jpg)
            except Exception:
                pass  # fall through to fallback below

    # Fallback: use FSSIcon.ico, then the launcher exe itself
    if not os.path.isfile(icon_path):
        icon_path = os.path.join(app_dir, "FSSIcon.ico")
    if not os.path.isfile(icon_path):
        icon_path = launcher_path

    # Build a small PowerShell script to create the shortcut
    # Uses [Environment]::GetFolderPath('Desktop') to handle OneDrive Desktop
    ps_lines = [
        '$ws = New-Object -ComObject WScript.Shell',
        '$desktop = [Environment]::GetFolderPath("Desktop")',
        f'$s = $ws.CreateShortcut("$desktop\\{shortcut_name}.lnk")',
        f'$s.TargetPath = "{launcher_path}"',
        f'$s.WorkingDirectory = "{os.path.dirname(launcher_path)}"',
        f'$s.IconLocation = "{icon_path}"',
        f'$s.Description = "Launch {gdef["name"]} Seamless Co-op"',
        '$s.Save()',
    ]
    ps_script = "; ".join(ps_lines)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return jsonify({"error": f"PowerShell error: {result.stderr.strip()}"}), 500
        return jsonify({"status": "ok", "message": f"Desktop shortcut \"{shortcut_name}\" created!"})
    except Exception as e:
        return jsonify({"error": f"Failed to create shortcut: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")


def is_port_in_use(port):
    """Check if a port is already bound (i.e. the server is already running)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


if __name__ == "__main__":
    port = 5000

    # If the server is already running, just open the browser and exit
    if is_port_in_use(port):
        print(f"Server is already running on http://127.0.0.1:{port}")
        print("Opening browser...")
        open_browser()
        sys.exit(0)

    # Auto-open browser after a short delay
    threading.Timer(1.2, open_browser).start()
    print(f"Starting FromSoft Co-op Settings Manager on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
