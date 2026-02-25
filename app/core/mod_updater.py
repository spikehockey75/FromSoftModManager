"""
Mod version detection and update checking.
Ported from mod_updater.py with API key support.
"""

import os
import re
import struct


def extract_dll_version(dll_path: str) -> tuple | None:
    if not os.path.isfile(dll_path):
        return None
    try:
        with open(dll_path, 'rb') as f:
            data = f.read(4096)
        version_pattern = rb'(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?'
        matches = re.findall(version_pattern, data)
        if matches:
            major, minor, patch, build = matches[0]
            return (int(major), int(minor), int(patch), int(build) if build else 0)
    except Exception:
        pass
    return None


FSMM_VERSION_FILE = "fsmm_version.txt"


def write_fsmm_version(version_dir: str, version: str) -> bool:
    """Write our own version file to version_dir/fsmm_version.txt. Returns True on success."""
    if not version:
        return False
    try:
        os.makedirs(version_dir, exist_ok=True)
        with open(os.path.join(version_dir, FSMM_VERSION_FILE), "w", encoding="utf-8") as f:
            f.write(version.strip())
        return True
    except Exception:
        return False


def read_fsmm_version(version_dir: str) -> str | None:
    """Read version from version_dir/fsmm_version.txt, or None if not present."""
    path = os.path.join(version_dir, FSMM_VERSION_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            v = f.read().strip()
        return v if v else None
    except Exception:
        return None


def read_version_file(mod_dir: str) -> str | None:
    for vf in [os.path.join(mod_dir, "VERSION"), os.path.join(mod_dir, "version.txt")]:
        if os.path.isfile(vf):
            try:
                with open(vf, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                    for line in content.splitlines():
                        line = line.strip()
                        if line and re.match(r'^\d+\.\d+', line):
                            return line
            except Exception:
                pass
    return None


def guess_installed_version(game_install_path: str, game_def: dict) -> str | None:
    mod_dir = os.path.join(game_install_path, game_def.get("mod_marker_relative", ""))
    if not os.path.isdir(mod_dir):
        return None

    version = read_version_file(mod_dir)
    if version:
        return version

    try:
        for file in os.listdir(mod_dir):
            if file.endswith('.dll'):
                dll_version = extract_dll_version(os.path.join(mod_dir, file))
                if dll_version:
                    major, minor, patch, build = dll_version
                    return f"{major}.{minor}.{patch}.{build}" if build > 0 else f"{major}.{minor}.{patch}"
    except Exception:
        pass

    return None


def version_compare(v1: str, v2: str) -> int:
    """Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
    def normalize(v):
        parts = []
        for part in v.split('.'):
            try:
                parts.append(int(part))
            except ValueError:
                break
        return parts

    p1, p2 = normalize(v1), normalize(v2)
    max_len = max(len(p1), len(p2))
    p1 += [0] * (max_len - len(p1))
    p2 += [0] * (max_len - len(p2))

    for a, b in zip(p1, p2):
        if a < b:
            return -1
        elif a > b:
            return 1
    return 0
