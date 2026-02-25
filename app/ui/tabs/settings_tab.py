"""
ME3 Profile tab — structured viewer for the ME3 TOML profile.
"""

import os
import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame, QTextEdit,
                                QSizePolicy)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QFont, QDesktopServices
from app.config.config_manager import ConfigManager
from app.core.me3_service import ME3_GAME_MAP, get_me3_profile_path, find_me3_executable


def _parse_toml_profile(text: str) -> dict:
    """Parse a simple ME3 TOML profile into structured data.

    Returns {"game": str, "natives": [dict], "packages": [dict]}.
    """
    result = {"game": "", "natives": [], "packages": []}
    current_section = None
    current_item = {}

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Section header
        if stripped == "[[natives]]":
            if current_section == "natives" and current_item:
                result["natives"].append(current_item)
            current_section = "natives"
            current_item = {}
            continue
        if stripped == "[[packages]]":
            if current_section == "packages" and current_item:
                result["packages"].append(current_item)
            current_section = "packages"
            current_item = {}
            continue
        if stripped == "[[supports]]":
            if current_section == "natives" and current_item:
                result["natives"].append(current_item)
            elif current_section == "packages" and current_item:
                result["packages"].append(current_item)
            current_section = "supports"
            current_item = {}
            continue

        # Key = value
        m = re.match(r'(\w+)\s*=\s*(.*)', stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()

        # Strip quotes
        if (val.startswith("'") and val.endswith("'")) or \
           (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]

        if current_section == "supports" and key == "game":
            result["game"] = val
        elif current_section in ("natives", "packages"):
            if key == "enabled":
                current_item[key] = val.lower() == "true"
            elif key == "optional":
                current_item[key] = val.lower() == "true"
            elif key == "load_early":
                current_item[key] = val.lower() == "true"
            else:
                current_item[key] = val

    # Flush last item
    if current_section == "natives" and current_item:
        result["natives"].append(current_item)
    elif current_section == "packages" and current_item:
        result["packages"].append(current_item)

    return result


class ME3ProfileTab(QWidget):
    log_message = Signal(str, str)

    def __init__(self, game_id: str, game_info: dict, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._toml_expanded = False
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(12)

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

        self._populate()

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate(self):
        self._clear()

        me3_path = find_me3_executable(self._config.get_me3_path())
        if not me3_path:
            self._add_placeholder("ME3 not found — install Mod Engine 3 or set its path in App Settings")
            return

        toml_path = get_me3_profile_path(self._game_id, me3_path)
        if not toml_path:
            self._add_placeholder("No ME3 profile — install or enable a mod to generate one")
            return

        try:
            with open(toml_path, "r", encoding="utf-8") as f:
                raw_toml = f.read()
        except Exception as e:
            self._add_placeholder(f"Error reading profile: {e}")
            return

        data = _parse_toml_profile(raw_toml)

        # ── Profile Info card ────────────────────────────
        self._layout.addWidget(self._build_info_card(toml_path, data))

        # ── Native DLLs section ──────────────────────────
        self._layout.addWidget(self._build_section_header("NATIVE DLLS"))
        if data["natives"]:
            self._layout.addWidget(self._build_natives_card(data["natives"]))
        else:
            self._layout.addWidget(self._build_empty_card("No native DLLs configured"))

        # ── Asset Packages section ───────────────────────
        self._layout.addWidget(self._build_section_header("ASSET PACKAGES"))
        if data["packages"]:
            self._layout.addWidget(self._build_packages_card(data["packages"]))
        else:
            self._layout.addWidget(self._build_empty_card("No asset packages configured"))

        # ── Collapsible Raw TOML ─────────────────────────
        self._layout.addWidget(self._build_raw_toml(raw_toml))

        # ── Refresh button ───────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setObjectName("btn_blue")
        refresh_btn.clicked.connect(self._on_refresh)
        btn_row.addWidget(refresh_btn)
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    def _add_placeholder(self, text: str):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#8888aa;font-size:13px;padding:40px;")
        lbl.setWordWrap(True)
        self._layout.addWidget(lbl)
        self._layout.addStretch()

    # ── Card builders ────────────────────────────────────

    def _build_info_card(self, toml_path: str, data: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        # Row 1: filename + status
        row1 = QHBoxLayout()
        filename = os.path.basename(toml_path)
        name_lbl = QLabel(f"Profile: {filename}")
        name_lbl.setStyleSheet("font-weight:700;font-size:13px;color:#e0e0ec;")
        row1.addWidget(name_lbl)
        row1.addStretch()

        status_lbl = QLabel("● Active")
        status_lbl.setStyleSheet(
            "color:#4ecca3;font-weight:600;font-size:11px;"
            "background:rgba(78,204,163,0.12);padding:2px 8px;"
            "border-radius:8px;"
        )
        row1.addWidget(status_lbl)
        lay.addLayout(row1)

        # Row 2: game name
        if data.get("game"):
            game_lbl = QLabel(f"Game: {data['game']}")
            game_lbl.setStyleSheet("color:#8888aa;font-size:12px;")
            lay.addWidget(game_lbl)

        # Row 3: path + open folder
        row3 = QHBoxLayout()
        path_lbl = QLabel(toml_path)
        path_lbl.setStyleSheet("color:#555577;font-size:11px;")
        path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row3.addWidget(path_lbl, stretch=1)

        open_btn = QPushButton("Open Folder")
        open_btn.setFixedHeight(24)
        open_btn.setStyleSheet(
            "QPushButton{font-size:11px;padding:2px 10px;border:1px solid #2a2a4a;"
            "border-radius:3px;background:transparent;color:#7b8cde;}"
            "QPushButton:hover{background:#1e1e3a;color:#e0e0ec;}"
        )
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(toml_path))
        ))
        row3.addWidget(open_btn)
        lay.addLayout(row3)

        return card

    def _build_section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#7b8cde;font-weight:700;font-size:11px;"
            "letter-spacing:0.08em;padding:0 2px;background:transparent;"
        )
        return lbl

    def _build_natives_card(self, natives: list) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        for i, native in enumerate(natives):
            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 8, 14, 8)
            rl.setSpacing(8)

            path = native.get("path", "")
            dll_name = os.path.basename(path) if path else "(unknown)"

            # Left: name + path
            info = QVBoxLayout()
            info.setSpacing(1)
            name_lbl = QLabel(f"●  {dll_name}")
            name_lbl.setStyleSheet("font-weight:600;font-size:12px;color:#e0e0ec;")
            info.addWidget(name_lbl)

            path_lbl = QLabel(path)
            path_lbl.setStyleSheet("font-size:10px;color:#555577;")
            path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info.addWidget(path_lbl)
            rl.addLayout(info, stretch=1)

            # Right: enabled badge
            enabled = native.get("enabled", True)
            badge = QLabel("enabled" if enabled else "disabled")
            badge.setStyleSheet(
                f"color:{'#4ecca3' if enabled else '#8888aa'};"
                f"font-size:10px;font-weight:600;"
                f"background:{'rgba(78,204,163,0.1)' if enabled else 'rgba(136,136,170,0.1)'};"
                f"padding:2px 6px;border-radius:6px;"
            )
            rl.addWidget(badge, alignment=Qt.AlignTop)

            lay.addWidget(row)

            # Separator between items
            if i < len(natives) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("color:#2a2a4a;")
                sep.setFixedHeight(1)
                lay.addWidget(sep)

        return card

    def _build_packages_card(self, packages: list) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        for i, pkg in enumerate(packages):
            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 8, 14, 8)

            path = pkg.get("path", "")
            folder_name = os.path.basename(path) if path else "(unknown)"

            info = QVBoxLayout()
            info.setSpacing(1)
            name_lbl = QLabel(f"📁  {folder_name}")
            name_lbl.setStyleSheet("font-weight:600;font-size:12px;color:#e0e0ec;")
            info.addWidget(name_lbl)

            path_lbl = QLabel(path)
            path_lbl.setStyleSheet("font-size:10px;color:#555577;")
            path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info.addWidget(path_lbl)
            rl.addLayout(info, stretch=1)

            lay.addWidget(row)

            if i < len(packages) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("color:#2a2a4a;")
                sep.setFixedHeight(1)
                lay.addWidget(sep)

        return card

    def _build_empty_card(self, text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#555577;font-size:12px;")
        lay.addWidget(lbl)
        return card

    def _build_raw_toml(self, raw_toml: str) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Toggle button
        self._toml_toggle = QPushButton("▶  Raw TOML")
        self._toml_toggle.setStyleSheet(
            "QPushButton{text-align:left;font-size:11px;font-weight:600;"
            "color:#8888aa;background:transparent;border:none;padding:4px 2px;}"
            "QPushButton:hover{color:#e0e0ec;}"
        )
        self._toml_toggle.setCursor(Qt.PointingHandCursor)
        self._toml_toggle.clicked.connect(self._toggle_toml)
        lay.addWidget(self._toml_toggle)

        # TOML text (hidden by default)
        self._toml_edit = QTextEdit()
        self._toml_edit.setReadOnly(True)
        self._toml_edit.setFont(QFont("Consolas", 10))
        self._toml_edit.setPlainText(raw_toml)
        self._toml_edit.setStyleSheet(
            "QTextEdit{background:#0e0e1a;color:#c0c0d8;border:1px solid #2a2a4a;"
            "border-radius:6px;padding:8px;font-size:11px;}"
        )
        self._toml_edit.setFixedHeight(180)
        self._toml_edit.setVisible(False)
        lay.addWidget(self._toml_edit)

        return container

    def _toggle_toml(self):
        self._toml_expanded = not self._toml_expanded
        self._toml_edit.setVisible(self._toml_expanded)
        arrow = "▼" if self._toml_expanded else "▶"
        self._toml_toggle.setText(f"{arrow}  Raw TOML")

    def _on_refresh(self):
        self._toml_expanded = False
        self._populate()

    def refresh(self, game_info: dict):
        self._game_info = game_info
        self._toml_expanded = False
        self._populate()
