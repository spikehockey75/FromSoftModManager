"""
Mod installer — backup/remove/extract/restore workflow.
Ported from mod_installer.py.
"""

import os
import re
import shutil
import zipfile
from datetime import datetime


def _extract_version_from_filename(filename: str) -> str | None:
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)
    matches = re.findall(r"v?(\d+\.\d+(?:\.\d+){0,2})", name, flags=re.IGNORECASE)
    return matches[-1] if matches else None


def _merge_ini_settings(new_ini_path: str, old_data: bytes) -> int:
    """Merge old INI values into new INI for keys that exist in both.

    Only carries over values where the key name exactly matches (case-insensitive).
    Preserves new INI structure, comments, and section headers.
    Returns count of keys whose values were carried over from the old file.
    """
    try:
        old_text = old_data.decode("utf-8", errors="replace")
        old_values: dict[str, str] = {}
        for line in old_text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", ";")):
                if "=" in stripped:
                    key, _, val = stripped.partition("=")
                    old_values[key.strip().lower()] = val.strip()

        if not old_values:
            return 0

        with open(new_ini_path, "r", encoding="utf-8", errors="replace") as f:
            new_lines = f.readlines()

        merged = []
        changed = 0
        for line in new_lines:
            stripped = line.strip()
            if "=" in stripped and stripped and not stripped.startswith(("#", ";")):
                key, _, val = stripped.partition("=")
                key_stripped = key.strip()
                key_norm = key_stripped.lower()
                if key_norm in old_values:
                    old_val = old_values[key_norm]
                    new_val = val.strip()
                    if old_val != new_val:
                        merged.append(f"{key_stripped} = {old_val}\n")
                        changed += 1
                        continue
            merged.append(line)

        if changed:
            with open(new_ini_path, "w", encoding="utf-8") as f:
                f.writelines(merged)
        return changed
    except Exception:
        return 0


def get_available_zips(game_def: dict) -> list[dict]:
    """Scan Downloads folder for zip files matching this game's pattern."""
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    available = []
    if not os.path.isdir(downloads_dir):
        return available
    pattern = re.compile(game_def["zip_pattern"], re.IGNORECASE)
    for fname in os.listdir(downloads_dir):
        if pattern.search(fname):
            full = os.path.join(downloads_dir, fname)
            if os.path.isfile(full):
                stat = os.stat(full)
                available.append({
                    "name": fname,
                    "path": full,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    available.sort(key=lambda x: x["modified"], reverse=True)
    return available


def install_mod_from_zip(
    zip_path: str,
    game_install_path: str,
    game_def: dict,
    target_dir: str | None = None,
) -> dict:
    """
    Full install/update workflow:
    1. Backup INI files in-memory + write physical dated copies to mod_backups/
    2. Remove old mod files
    3. Extract new zip
    4. Smart-merge user settings into new INIs; restore any INIs not provided by zip

    target_dir: if provided (ME3 games), extract here. For non-ME3 (AC6), target_dir
                is None and files go to game_install_path/mod_extract_relative.
    Returns {'success': bool, 'message': str, 'steps': [...], 'version': str|None}
    """
    if not os.path.isfile(zip_path):
        return {"success": False, "message": f"Zip not found: {zip_path}", "steps": []}
    if not zipfile.is_zipfile(zip_path):
        return {"success": False, "message": "Not a valid zip file", "steps": []}

    steps = []

    # Compute paths early — needed by both backup and extract steps
    if target_dir:
        # ME3 games: extract into the dedicated mod subdirectory
        extract_target = target_dir
        scan_root = target_dir
        clean_dir = target_dir
    else:
        # Non-ME3 (AC6): extract into game_install_path/mod_extract_relative
        extract_target = os.path.join(game_install_path, game_def["mod_extract_relative"])
        scan_root = os.path.join(game_install_path, game_def.get("mod_marker_relative", ""))
        clean_dir = scan_root

    extract_target_norm = os.path.normpath(extract_target)

    # ── Step 1: Backup INI files in-memory + write physical dated copies ──────
    ini_backup: dict[str, bytes] = {}  # abs_path -> contents
    if scan_root and os.path.isdir(scan_root):
        for root, _dirs, files in os.walk(scan_root):
            for fname in files:
                if fname.endswith(".ini"):
                    full = os.path.join(root, fname)
                    try:
                        with open(full, "rb") as fh:
                            ini_backup[full] = fh.read()
                    except Exception:
                        pass

    backed = len(ini_backup)
    if ini_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(clean_dir, "mod_backups")
        try:
            os.makedirs(backup_dir, exist_ok=True)
            for abs_path, data in ini_backup.items():
                fname = os.path.basename(abs_path)
                try:
                    with open(os.path.join(backup_dir, f"{ts}_{fname}"), "wb") as fh:
                        fh.write(data)
                except Exception:
                    pass
        except Exception:
            pass

    steps.append({"step": "backup", "success": True, "message": f"Backed up {backed} INI file(s)"})

    # ── Step 2: Remove old files from clean_dir ───────────────────────────────
    removed = 0
    if os.path.isdir(clean_dir):
        for item in os.listdir(clean_dir):
            if item.endswith('.ini') or item == 'mod_backups':
                continue
            item_path = os.path.join(clean_dir, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                    removed += 1
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    removed += 1
            except Exception:
                pass
    steps.append({"step": "remove_old", "success": True, "message": f"Removed {removed} old files"})

    # ── Step 3: Extract ───────────────────────────────────────────────────────
    os.makedirs(extract_target, exist_ok=True)
    extracted = 0
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            file_list = zf.namelist()
            root_folder = None
            if file_list:
                first_part = file_list[0].split('/')[0]
                if all(f.startswith(first_part + '/') or f == first_part for f in file_list):
                    root_folder = first_part

            for file_info in zf.infolist():
                file_path = file_info.filename
                if file_path.endswith('/'):
                    continue
                if root_folder and file_path.startswith(root_folder + '/'):
                    file_path = file_path[len(root_folder) + 1:]
                elif root_folder and file_path == root_folder:
                    continue
                target_path = os.path.join(extract_target, file_path)
                # Security: no path traversal
                if not os.path.realpath(target_path).startswith(os.path.realpath(extract_target)):
                    continue
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(file_info) as src, open(target_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                extracted += 1
        steps.append({"step": "extract", "success": True, "message": f"Extracted {extracted} files"})
    except Exception as e:
        steps.append({"step": "extract", "success": False, "message": str(e)})
        return {"success": False, "message": f"Extraction failed: {e}", "steps": steps}

    # ── Step 4: Restore / smart-merge INI settings ───────────────────────────
    # Compute each dest relative to extract_target (not scan_root) so paths are
    # correct for non-ME3 games where scan_root ≠ extract_target.
    restored = 0
    merged_keys = 0
    for abs_path, data in ini_backup.items():
        rel = os.path.relpath(os.path.normpath(abs_path), extract_target_norm)
        if rel.startswith(".."):
            # abs_path is outside extract_target — compute via scan_root instead
            scan_rel = os.path.relpath(os.path.normpath(abs_path), os.path.normpath(scan_root))
            rel = os.path.join(os.path.relpath(scan_root, extract_target), scan_rel)
        dest = os.path.normpath(os.path.join(extract_target_norm, rel))
        # Safety: skip if dest escapes extract_target tree
        if os.path.relpath(dest, extract_target_norm).startswith(".."):
            continue
        if os.path.isfile(dest):
            # New zip provided this INI — merge user's old values in
            merged_keys += _merge_ini_settings(dest, data)
        else:
            # New zip didn't include this INI — restore from backup
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(data)
                restored += 1
            except Exception:
                pass

    msg_parts = []
    if merged_keys:
        msg_parts.append(f"merged {merged_keys} setting(s)")
    if restored:
        msg_parts.append(f"restored {restored} INI(s)")
    if msg_parts:
        steps.append({"step": "restore", "success": True, "message": f"Settings: {', '.join(msg_parts)}"})

    detected_version = _extract_version_from_filename(zip_path)
    return {
        "success": True,
        "message": f"Installed successfully ({extracted} files). Settings preserved.",
        "steps": steps,
        "version": detected_version,
    }


def delete_zip(zip_path: str) -> dict:
    if not os.path.isfile(zip_path):
        return {"success": False, "message": "File not found"}
    os.remove(zip_path)
    return {"success": True, "message": "Zip deleted"}
