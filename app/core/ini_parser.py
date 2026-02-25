"""
INI file parser with smart type-inference.
Ported from server.py.
"""

import os
import re


def extract_options_from_comment(text: str) -> list | None:
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
                    if label.endswith(')') and '(' not in label:
                        label = label.rstrip(')')
                    opts.append({"value": m.group(1).strip(), "label": label})
            if len(opts) >= 3:
                return opts
            if len(opts) == 2:
                vals = sorted(int(o["value"]) for o in opts)
                if vals[-1] - vals[0] <= 2:
                    return opts

    matches = re.findall(r'(\d+)\s*=\s*([A-Za-z][A-Za-z_ ()\-]*?)(?:\s{2,}|\s*$)', text)
    if len(matches) >= 2:
        vals = sorted(int(v) for v, _ in matches)
        if vals[-1] - vals[0] <= len(matches):
            return [{"value": v.strip(), "label": l.strip()} for v, l in matches]

    return None


def extract_range_from_comment(text: str) -> tuple:
    m = re.search(r'(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)', text, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'\((\d+)\s*=\s*\w+\s*\|\s*(\d+)\s*=\s*\w+', text)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        if high - low > 2:
            return low, high
    return None, None


def infer_field_meta(key: str, value: str, description: str) -> tuple:
    options = extract_options_from_comment(description) if description else None
    if options:
        return "select", options, None, None

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


def parse_ini_file(file_path: str, defaults_dict: dict = None) -> list:
    """
    Parse an INI file into structured sections with metadata.
    Returns list of {name, settings} dicts.
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

        if not stripped:
            comment_buffer = []
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1]
            current_section = {"name": section_name, "settings": []}
            sections.append(current_section)
            comment_buffer = []
            continue

        if stripped.startswith(";"):
            comment_buffer.append(stripped.lstrip("; ").strip())
            continue

        if "=" in stripped and current_section is not None:
            key, _, val = stripped.partition("=")
            key = key.strip()
            val = val.strip()
            description = " ".join(comment_buffer).strip()
            comment_buffer = []

            field_type, options, low, high = infer_field_meta(key, val, description)

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


def save_ini_settings(file_path: str, settings_dict: dict):
    """Write changed values back to INI preserving comments/formatting."""
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
