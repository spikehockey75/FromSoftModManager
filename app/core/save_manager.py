"""
Save file manager — backup, restore, transfer.
Ported from server.py saves section.
"""

import os
import re
import glob
import shutil
from datetime import datetime


def _get_backup_dir(save_dir: str, game_id: str) -> str:
    backup_dir = os.path.join(save_dir, f"{game_id.upper()}_Backups")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def list_save_files(save_dir: str, prefix: str, ext: str) -> list[dict]:
    """Return list of file info dicts matching prefix+ext."""
    pattern = os.path.join(save_dir, f"{prefix}{ext}*")
    results = []
    for f in glob.glob(pattern):
        if os.path.isfile(f):
            stat = os.stat(f)
            results.append({
                "name": os.path.basename(f),
                "path": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return results


def parse_backup_timestamps(backup_dir: str) -> list[str]:
    ts_set = set()
    ts_re = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})$')
    if not os.path.isdir(backup_dir):
        return []
    for name in os.listdir(backup_dir):
        m = ts_re.search(name)
        if m:
            ts_set.add(m.group(1))
    return sorted(ts_set, reverse=True)


def get_saves_info(game_info: dict, game_id: str) -> dict:
    save_dir = game_info.get("save_dir")
    if not save_dir or not os.path.isdir(save_dir):
        return {"error": f"Save directory not found: {save_dir}"}

    prefix = game_info["save_prefix"]
    base_ext = game_info["base_ext"]
    coop_ext = game_info["coop_ext"]
    backup_dir = _get_backup_dir(save_dir, game_id)

    base_files = list_save_files(save_dir, prefix, base_ext)
    coop_files = list_save_files(save_dir, prefix, coop_ext)

    timestamps = parse_backup_timestamps(backup_dir)
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

    return {
        "save_dir": save_dir,
        "backup_dir": backup_dir,
        "base_ext": base_ext,
        "coop_ext": coop_ext,
        "base_files": base_files,
        "coop_files": coop_files,
        "backups": backups,
    }


def transfer_save(game_info: dict, game_id: str, direction: str) -> dict:
    """direction: 'base_to_coop' or 'coop_to_base'"""
    save_dir = game_info.get("save_dir")
    if not save_dir or not os.path.isdir(save_dir):
        return {"success": False, "message": "Save directory not found"}

    prefix = game_info["save_prefix"]
    base_ext = game_info["base_ext"]
    coop_ext = game_info["coop_ext"]
    backup_dir = _get_backup_dir(save_dir, game_id)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if direction == "base_to_coop":
        src_ext, dst_ext = base_ext, coop_ext
        src_label, dst_label = "Base Game", "Co-op"
    else:
        src_ext, dst_ext = coop_ext, base_ext
        src_label, dst_label = "Co-op", "Base Game"

    dest_files = list_save_files(save_dir, prefix, dst_ext)
    for f in dest_files:
        fname = os.path.basename(f["path"])
        shutil.copy2(f["path"], os.path.join(backup_dir, f"{fname}_{ts}"))

    src_files = list_save_files(save_dir, prefix, src_ext)
    transferred = 0
    for src in src_files:
        fname = os.path.basename(src["path"])
        dst_name = fname.replace(f"{prefix}{src_ext}", f"{prefix}{dst_ext}")
        shutil.copy(src["path"], os.path.join(save_dir, dst_name))
        transferred += 1

    if transferred == 0:
        return {"success": False, "message": f"No {src_label} save files found."}

    return {
        "success": True,
        "message": f"Transferred {transferred} file(s): {src_label} → {dst_label}",
        "transferred": transferred,
    }


def create_backup(game_info: dict, game_id: str) -> dict:
    save_dir = game_info.get("save_dir")
    if not save_dir or not os.path.isdir(save_dir):
        return {"success": False, "message": "Save directory not found"}

    prefix = game_info["save_prefix"]
    base_ext = game_info["base_ext"]
    coop_ext = game_info["coop_ext"]
    backup_dir = _get_backup_dir(save_dir, game_id)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    count = 0
    for ext in (base_ext, coop_ext):
        for f in list_save_files(save_dir, prefix, ext):
            fname = os.path.basename(f["path"])
            shutil.copy2(f["path"], os.path.join(backup_dir, f"{fname}_{ts}"))
            count += 1

    if count == 0:
        return {"success": False, "message": "No save files found to backup."}

    return {"success": True, "message": f"Backed up {count} file(s)", "timestamp": ts, "count": count}


def restore_backup(game_info: dict, game_id: str, timestamp: str, dest_type: str) -> dict:
    """dest_type: 'base' or 'coop'"""
    save_dir = game_info.get("save_dir")
    if not save_dir or not os.path.isdir(save_dir):
        return {"success": False, "message": "Save directory not found"}

    prefix = game_info["save_prefix"]
    base_ext = game_info["base_ext"]
    coop_ext = game_info["coop_ext"]
    backup_dir = _get_backup_dir(save_dir, game_id)
    now_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dst_ext = base_ext if dest_type == "base" else coop_ext

    for f in list_save_files(save_dir, prefix, dst_ext):
        fname = os.path.basename(f["path"])
        shutil.copy2(f["path"], os.path.join(backup_dir, f"{fname}_{now_ts}"))

    restored = 0
    for name in os.listdir(backup_dir):
        if not name.endswith(timestamp) or not name.startswith(prefix):
            continue
        backup_path = os.path.join(backup_dir, name)
        original_name = name[:-(len(timestamp) + 1)]
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
        return {"success": False, "message": f"No backup files for timestamp: {timestamp}"}

    dest_label = "Base Game" if dest_type == "base" else "Co-op"
    return {"success": True, "message": f"Restored {restored} file(s) to {dest_label}"}


def delete_backup(game_info: dict, game_id: str, timestamp: str) -> dict:
    save_dir = game_info.get("save_dir")
    backup_dir = _get_backup_dir(save_dir, game_id)
    deleted = 0
    for name in os.listdir(backup_dir):
        if name.endswith(timestamp):
            os.remove(os.path.join(backup_dir, name))
            deleted += 1
    if deleted == 0:
        return {"success": False, "message": "No files found for that timestamp."}
    return {"success": True, "message": f"Deleted {deleted} backup file(s)"}
