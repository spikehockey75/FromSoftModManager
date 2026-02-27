"""
Mods tab — per-mod action list with Install/Update/Manage/Uninstall + Activate/Deactivate.
"""

import os
import shutil
import threading
import queue as _queue
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame, QProgressBar,
                                QFileDialog, QDialog, QSizePolicy, QInputDialog,
                                QLineEdit)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QIcon, QFont, QPixmap, QPainter, QColor
from app.config.config_manager import ConfigManager

_MDL2 = "Segoe MDL2 Assets"


def _mdl2_icon(char: str, size: int = 16, color: str = "#c0c0d8") -> QIcon:
    px = QPixmap(size, size)
    px.fill(QColor("transparent"))
    p = QPainter(px)
    p.setFont(QFont(_MDL2, int(size * 0.75)))
    p.setPen(QColor(color))
    p.drawText(px.rect(), Qt.AlignCenter, char)
    p.end()
    return QIcon(px)
from app.config.game_definitions import GAME_DEFINITIONS
from app.core.mod_installer import install_mod_from_zip
from app.core.me3_service import write_me3_profile, find_me3_executable, ME3_GAME_MAP, slugify
from app.core.mod_updater import write_fsmm_version, read_fsmm_version
from app.services.nexus_service import NexusService
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.widgets.toggle_switch import ToggleSwitch

# Known FromSoft asset subdirectory names
_ASSET_SUBDIRS = {"chr", "parts", "param", "sfx", "map", "obj", "menu", "msg",
                  "shader", "sound", "event", "script", "action"}


def _find_native_dlls(mod_dir: str) -> list[str]:
    """Find DLL files in a mod directory (recursively, one level deep)."""
    dlls = []
    try:
        for entry in os.scandir(mod_dir):
            if entry.is_file() and entry.name.lower().endswith(".dll"):
                dlls.append(entry.path)
            elif entry.is_dir():
                # Check one level deeper (e.g. SeamlessCoop/ersc.dll)
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
    # Has known asset subdirs?
    if entries & _ASSET_SUBDIRS:
        return True
    # Has .dcx files or regulation.bin?
    if "regulation.bin" in entries:
        return True
    for name in entries:
        if name.endswith(".dcx"):
            return True
    return False


# ──────────────────────────────────────────────────────────────────────
# Mod card widget
# ──────────────────────────────────────────────────────────────────────
class _ModCard(QFrame):
    """
    A card for a single mod.
    All user interactions put messages into the shared `pending` queue —
    the card itself never touches Qt from background threads.
    """

    def __init__(self, mod: dict, game_id: str, is_me3_game: bool,
                 pending: _queue.SimpleQueue, parent=None):
        super().__init__(parent)
        self._mod = dict(mod)
        self._game_id = game_id
        self._is_me3_game = is_me3_game
        self._pending = pending
        self._virtual = bool(mod.get("_virtual"))   # not yet installed
        self._has_update = False
        self._latest_version = ""
        self.setObjectName("card")
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # ── Top row: name + version ─────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        self._name_lbl = QLabel(self._mod.get("name", "Unknown Mod"))
        self._name_lbl.setStyleSheet("font-size:13px;font-weight:700;color:#e0e0ec;")
        top.addWidget(self._name_lbl)

        ver = self._mod.get("version") or ""
        self._ver_lbl = QLabel(f"v{ver}" if ver else "—")
        self._ver_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        top.addWidget(self._ver_lbl)
        top.addStretch()

        # Manage button (cog wheel) — installed mods with INI settings
        self._manage_btn = QPushButton()
        self._manage_btn.setIcon(_mdl2_icon("\uE713", 16, "#c0c0d8"))
        self._manage_btn.setIconSize(QSize(16, 16))
        self._manage_btn.setFixedSize(30, 30)
        self._manage_btn.setToolTip("Manage Settings")
        self._manage_btn.setStyleSheet(
            "QPushButton{background:#1e1e3a;"
            "border:1px solid #3a3a5a;border-radius:6px;}"
            "QPushButton:hover{background:#2a2a4a;border-color:#7b8cde;}"
        )
        self._manage_btn.clicked.connect(
            lambda: self._pending.put(("manage", self._mod["id"]))
        )
        top.addWidget(self._manage_btn)

        # Uninstall button (delete icon) — installed mods without INI
        self._uninstall_btn = QPushButton()
        self._uninstall_btn.setIcon(_mdl2_icon("\uE74D", 16, "#e74c3c"))
        self._uninstall_btn.setIconSize(QSize(16, 16))
        self._uninstall_btn.setFixedSize(30, 30)
        self._uninstall_btn.setToolTip("Uninstall")
        self._uninstall_btn.setStyleSheet(
            "QPushButton{background:transparent;"
            "border:1px solid #e74c3c;border-radius:6px;}"
            "QPushButton:hover{background:#e74c3c;}"
        )
        self._uninstall_btn.clicked.connect(
            lambda: self._pending.put(("uninstall", self._mod["id"]))
        )
        top.addWidget(self._uninstall_btn)

        # Update button (sync icon) — visible only when update available
        self._update_btn = QPushButton()
        self._update_btn.setIcon(_mdl2_icon("\uE72C", 16, "#ff9800"))
        self._update_btn.setIconSize(QSize(16, 16))
        self._update_btn.setFixedSize(30, 30)
        self._update_btn.setStyleSheet(
            "QPushButton{background:transparent;"
            "border:1px solid #ff9800;border-radius:6px;}"
            "QPushButton:hover{background:#ff9800;}"
        )
        self._update_btn.clicked.connect(
            lambda: self._pending.put(("update", self._mod["id"]))
        )
        top.addWidget(self._update_btn)

        # Install button (text) — virtual/uninstalled mods only
        self._install_btn = QPushButton("Install")
        self._install_btn.setFixedHeight(30)
        self._install_btn.setMinimumWidth(90)
        self._install_btn.setObjectName("btn_accent")
        self._install_btn.clicked.connect(
            lambda: self._pending.put(("install", self._mod["id"]))
        )
        top.addWidget(self._install_btn)

        # Activate / Deactivate toggle (ME3 games, installed mods only)
        self._toggle_sw = ToggleSwitch(checked=self._mod.get("enabled", True))
        self._toggle_sw.toggled.connect(self._on_toggle_switch)
        top.addWidget(self._toggle_sw)

        layout.addLayout(top)

        # ── Status row ──────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        layout.addWidget(self._status_lbl)

        # ── Nexus link (shown for trending / virtual mods with nexus info) ──
        self._nexus_link = QLabel("")
        self._nexus_link.setOpenExternalLinks(True)
        self._nexus_link.setStyleSheet("font-size:11px;")
        self._nexus_link.setVisible(False)
        layout.addWidget(self._nexus_link)
        self._build_nexus_link()

        # ── "Link to Nexus" button for unlinked installed mods ──
        self._link_btn = QPushButton("Link to Nexus")
        self._link_btn.setObjectName("btn_blue")
        self._link_btn.setFixedHeight(26)
        self._link_btn.setFixedWidth(120)
        self._link_btn.setVisible(False)
        self._link_btn.clicked.connect(self._on_link_to_nexus)
        layout.addWidget(self._link_btn)
        if not self._virtual and not self._mod.get("nexus_mod_id"):
            self._link_btn.setVisible(True)

        # ── Progress bar (hidden by default) ────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Initial button state
        self._refresh_buttons()
        self._refresh_toggle_btn()

        # Show checking status if installed and has nexus info
        if not self._virtual and self._mod.get("nexus_mod_id"):
            self._status_lbl.setText("Checking for updates…")

    # ------------------------------------------------------------------
    # Button state helpers
    # ------------------------------------------------------------------
    def _refresh_buttons(self):
        if self._virtual:
            self._install_btn.setVisible(True)
            self._manage_btn.setVisible(False)
            self._uninstall_btn.setVisible(False)
            self._update_btn.setVisible(False)
        else:
            self._install_btn.setVisible(False)
            has_ini = self._has_ini()
            self._manage_btn.setVisible(has_ini)
            self._uninstall_btn.setVisible(not has_ini)
            if self._has_update:
                tip = f"Update to v{self._latest_version}" if self._latest_version else "Update"
                self._update_btn.setToolTip(tip)
                self._update_btn.setVisible(True)
            else:
                self._update_btn.setVisible(False)

    def _refresh_toggle_btn(self):
        show = self._is_me3_game and not self._virtual
        self._toggle_sw.setVisible(show)
        if show:
            enabled = self._mod.get("enabled", True)
            self._toggle_sw.setChecked(enabled, animate=False)

    def _on_toggle_switch(self, checked: bool):
        self._mod["enabled"] = checked
        self._pending.put(("toggle", self._mod["id"], checked))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_nexus_link(self):
        domain = self._mod.get("nexus_domain", "")
        nid = self._mod.get("nexus_mod_id", 0)
        if domain and nid and self._virtual:
            url = f"https://www.nexusmods.com/{domain}/mods/{nid}"
            self._nexus_link.setText(
                f'<a href="{url}" style="color:#7b8cde;">View on Nexus Mods</a>'
            )
            self._nexus_link.setVisible(True)

    def _on_link_to_nexus(self):
        url, ok = QInputDialog.getText(
            self, "Link to Nexus",
            f"Paste Nexus Mods URL for \"{self._mod.get('name', '')}\":",
            QLineEdit.Normal, ""
        )
        if not ok or not url.strip():
            return
        from app.services.nexus_service import parse_nexus_url
        parsed = parse_nexus_url(url.strip())
        if not parsed:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid URL",
                                "Could not parse that URL.\n"
                                "Expected format: https://www.nexusmods.com/{game}/mods/{id}")
            return
        domain, mod_id_num = parsed
        self._mod["nexus_domain"] = domain
        self._mod["nexus_mod_id"] = mod_id_num
        self._link_btn.setVisible(False)
        # Show Nexus link
        nexus_url = f"https://www.nexusmods.com/{domain}/mods/{mod_id_num}"
        self._nexus_link.setText(
            f'<a href="{nexus_url}" style="color:#7b8cde;">View on Nexus Mods</a>'
        )
        self._nexus_link.setVisible(True)
        self._pending.put(("link_nexus", self._mod["id"], domain, mod_id_num))

    def _has_ini(self) -> bool:
        path = self._mod.get("path", "")
        if not path or not os.path.isdir(path):
            return False
        for root, _dirs, files in os.walk(path):
            if any(f.endswith(".ini") for f in files):
                return True
        return False

    def get_ini_path(self) -> str | None:
        path = self._mod.get("path", "")
        if not path or not os.path.isdir(path):
            return None
        for root, _dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".ini"):
                    return os.path.join(root, f)
        return None

    # ------------------------------------------------------------------
    # External state updates (called from ModsTab on main thread)
    # ------------------------------------------------------------------
    def set_update_status(self, result: dict):
        if "error" in result:
            self._status_lbl.setText(f"Update check failed")
            self._status_lbl.setStyleSheet("font-size:11px;color:#555577;")
            return
        latest = result.get("latest_version", "")
        has_update = result.get("has_update", False)
        self._has_update = has_update
        self._latest_version = latest
        self._refresh_buttons()
        if has_update:
            self._status_lbl.setText(f"🔔 Update available: v{latest}")
            self._status_lbl.setStyleSheet("font-size:11px;color:#ff9800;font-weight:600;")
        else:
            self._status_lbl.setText(f"✓ Up to date" + (f" (v{latest})" if latest else ""))
            self._status_lbl.setStyleSheet("font-size:11px;color:#4ecca3;")

    def set_installing(self, visible: bool, pct: int = 0, msg: str = ""):
        self._progress.setVisible(visible)
        if visible:
            self._progress.setValue(pct)
            if msg:
                self._status_lbl.setText(msg)
                self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        enabled = not visible
        self._install_btn.setEnabled(enabled)
        self._manage_btn.setEnabled(enabled)
        self._uninstall_btn.setEnabled(enabled)
        self._update_btn.setEnabled(enabled)

    def on_install_done(self, result: dict, new_version: str = ""):
        self.set_installing(False)
        if result.get("success"):
            self._virtual = False
            ver = new_version or result.get("version") or ""
            if ver:
                self._mod["version"] = ver
                self._ver_lbl.setText(f"v{ver}")
            self._has_update = False
            self._refresh_buttons()
            self._refresh_toggle_btn()
            self._status_lbl.setText("✓ Installed successfully")
            self._status_lbl.setStyleSheet("font-size:11px;color:#4ecca3;")
        else:
            self._status_lbl.setText(f"✗ {result.get('message', 'Install failed')}")
            self._status_lbl.setStyleSheet("font-size:11px;color:#e74c3c;")

    def update_mod_data(self, mod: dict):
        self._mod = dict(mod)
        self._refresh_toggle_btn()

    @property
    def mod(self) -> dict:
        return self._mod

    @property
    def is_virtual(self) -> bool:
        return self._virtual


# ──────────────────────────────────────────────────────────────────────
# ModsTab
# ──────────────────────────────────────────────────────────────────────
class ModsTab(QWidget):
    log_message = Signal(str, str)
    mod_installed = Signal()
    auth_changed = Signal()

    def __init__(self, game_id: str, game_info: dict, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._gdef = GAME_DEFINITIONS.get(game_id, {})
        self._is_me3_game = game_id in ME3_GAME_MAP
        self._cards: dict[str, _ModCard] = {}   # mod_id → card

        self._pending: _queue.SimpleQueue = _queue.SimpleQueue()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_updates)
        self._poll_timer.start(100)

        self._trending_cards: dict[str, _ModCard] = {}
        self._trending_separator: QLabel | None = None
        self._trending_loaded = False

        self._auto_detect_coop_mod()
        self._build()

        # Ensure ME3 profile exists on first load if game has enabled mods
        if self._is_me3_game:
            mods = self._config.get_game_mods(game_id)
            if any(m.get("enabled") and m.get("path") for m in mods):
                self._rewrite_profile()

        QTimer.singleShot(400, self._start_update_checks)
        QTimer.singleShot(600, self._start_trending_fetch)

    # ------------------------------------------------------------------
    # Auto-detect existing co-op mod on disk
    # ------------------------------------------------------------------
    def _auto_detect_coop_mod(self):
        """If the co-op mod files exist on disk but aren't tracked in config, register them.

        Also repairs stale paths — if the co-op mod is registered but its path
        no longer exists, update it to the game's on-disk marker directory.
        """
        coop_id = f"{self._game_id}-coop"
        installed = self._config.get_game_mods(self._game_id)
        coop_mod = next((m for m in installed if m["id"] == coop_id), None)

        marker_rel = self._gdef.get("mod_marker_relative", "")
        install_path = self._game_info.get("install_path", "")
        if not marker_rel or not install_path:
            return
        marker_path = os.path.join(install_path, marker_rel)

        if coop_mod:
            # Already registered — check if path is stale
            if coop_mod.get("path") and os.path.isdir(coop_mod["path"]):
                return  # Path is valid, nothing to fix
            # Path is stale — repair it using the game's marker directory
            if os.path.isdir(marker_path):
                coop_mod["path"] = marker_path
                self._config.add_or_update_game_mod(self._game_id, coop_mod)
                print(f"[MODS] Repaired stale path for {coop_mod.get('name', coop_id)} → {marker_path}", flush=True)
            return

        # Not registered — check if mod exists on disk
        if not os.path.isdir(marker_path):
            return

        mod_dict = {
            "id": coop_id,
            "name": self._gdef.get("mod_name", "Co-op Mod"),
            "version": "",
            "path": marker_path,
            "nexus_domain": self._gdef.get("nexus_domain", ""),
            "nexus_mod_id": self._gdef.get("nexus_mod_id", 0),
            "enabled": True,
        }
        self._config.add_or_update_game_mod(self._game_id, mod_dict)
        print(f"[MODS] Auto-detected {self._gdef.get('mod_name', coop_id)} on disk for {self._game_id}", flush=True)

    # ------------------------------------------------------------------
    # Queue drain
    # ------------------------------------------------------------------
    def _poll_updates(self):
        try:
            while True:
                item = self._pending.get_nowait()
                tag = item[0]
                if tag == "action":
                    self._route_action(item[1])
                elif tag == "manage":
                    ini = self._get_mod_ini_path(item[1])
                    if ini:
                        self._do_manage(item[1])
                elif tag == "update":
                    if self._ensure_me3_available():
                        self._do_update(item[1])
                elif tag == "uninstall":
                    self._do_uninstall(item[1])
                elif tag == "install":
                    if self._ensure_me3_available():
                        self._do_install(item[1])
                elif tag == "toggle":
                    _, mod_id, enabled = item
                    self._config.set_mod_enabled(self._game_id, mod_id, enabled)
                    self._rewrite_profile()
                    card = self._cards.get(mod_id)
                    mod_name = card.mod.get("name", mod_id) if card else mod_id
                    state = "Activated" if enabled else "Deactivated"
                    self.log_message.emit(f"{state} {mod_name}", "info")
                    if self._is_me3_game:
                        mods = self._config.get_game_mods(self._game_id)
                        enabled_list = [m["name"] for m in mods if m.get("enabled")]
                        disabled_list = [m["name"] for m in mods if not m.get("enabled")]
                        if enabled_list:
                            self.log_message.emit(f"  ME3 profile: {', '.join(enabled_list)}", "info")
                        if disabled_list:
                            self.log_message.emit(f"  Disabled: {', '.join(disabled_list)}", "info")
                elif tag == "update_result":
                    _, mod_id, result = item
                    if mod_id in self._cards:
                        self._cards[mod_id].set_update_status(result)
                elif tag == "install_progress":
                    _, mod_id, pct, msg = item
                    card = self._cards.get(mod_id) or self._trending_cards.get(mod_id)
                    if card:
                        card.set_installing(True, pct, msg)
                elif tag == "install_done":
                    _, mod_id, result, mod_dict = item
                    self._on_install_done(mod_id, result, mod_dict)
                elif tag == "update_progress":
                    _, mod_id, pct, msg = item
                    card = self._cards.get(mod_id) or self._trending_cards.get(mod_id)
                    if card:
                        card.set_installing(True, pct, msg)
                elif tag == "update_done":
                    _, mod_id, result, version = item
                    self._on_update_done(mod_id, result, version)
                elif tag == "link_nexus":
                    _, mod_id, domain, nexus_mod_id = item
                    self._on_link_nexus(mod_id, domain, nexus_mod_id)
                elif tag == "nexus_validated":
                    _, result = item
                    self._config.set_nexus_user_info({
                        "name": result.get("name", ""),
                        "is_premium": result.get("is_premium", False),
                        "is_supporter": result.get("is_supporter", False),
                        "profile_url": result.get("profile_url", ""),
                    })
                    self.auth_changed.emit()
                elif tag == "trending_result":
                    _, trending_mods, excluded_cats = item
                    self._on_trending_result(trending_mods, excluded_cats)
        except _queue.Empty:
            pass

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(18, 14, 18, 18)
        self._layout.setSpacing(8)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._build_header()

        # "Add Mod" button — created before cards so they insert above it
        self._add_btn_widget = QWidget()
        btn_row = QHBoxLayout(self._add_btn_widget)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        add_btn = QPushButton("+ Add Mod")
        add_btn.setObjectName("btn_accent")
        add_btn.setFixedHeight(30)
        add_btn.clicked.connect(self._on_add_mod)
        btn_row.addWidget(add_btn)
        self._layout.addWidget(self._add_btn_widget)

        self._populate_mod_list()

        self._layout.addStretch()

    def _build_header(self):
        # Section header matching the "Other Popular Mods" style
        self._header_lbl = QLabel("Mods Installed")
        self._header_lbl.setObjectName("section_header")
        self._header_lbl.setContentsMargins(0, 0, 0, 4)
        self._layout.addWidget(self._header_lbl)

    def _populate_mod_list(self):
        """Build (or rebuild) card list from current config + virtual co-op entry."""
        for card in list(self._cards.values()):
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for mod in self._get_display_mods():
            self._add_card(mod)

        self._update_header()

    def _installed_insert_index(self) -> int:
        """Return the layout index where the next installed card should go.

        Cards go after the header but before the 'Add Mod' button.
        """
        idx = self._layout.indexOf(self._add_btn_widget)
        if idx >= 0:
            return idx
        # Fallback: before trending separator or stretch
        if self._trending_separator:
            return self._layout.indexOf(self._trending_separator)
        return self._layout.count() - 1

    def _get_display_mods(self) -> list[dict]:
        """Return installed mods, prepending a virtual co-op entry if not installed."""
        installed = self._config.get_game_mods(self._game_id)
        installed_ids = {m["id"] for m in installed}

        result = list(installed)

        # Prepend virtual co-op mod entry if not installed and game has one
        coop_id = f"{self._game_id}-coop"
        if coop_id not in installed_ids and self._gdef.get("nexus_mod_id"):
            result.insert(0, {
                "id": coop_id,
                "name": self._gdef.get("mod_name", "Co-op Mod"),
                "version": None,
                "path": "",
                "nexus_domain": self._gdef.get("nexus_domain", ""),
                "nexus_mod_id": self._gdef.get("nexus_mod_id", 0),
                "enabled": False,
                "_virtual": True,
            })

        return result

    def _get_mod_version_dir(self, mod_id: str) -> str:
        """App-managed directory for per-mod metadata (version file etc.)."""
        return os.path.join(self._config.get_game_mod_dir(self._game_id), mod_id)

    def _add_card(self, mod: dict):
        # For non-ME3 games, auto-correct a stale/empty path to the actual mod marker dir.
        if not self._is_me3_game and not mod.get("_virtual"):
            correct_path = os.path.join(
                self._game_info.get("install_path", ""),
                self._gdef.get("mod_marker_relative", ""),
            )
            if correct_path and mod.get("path") != correct_path and os.path.isdir(correct_path):
                mod = dict(mod)
                mod["path"] = correct_path
                self._config.add_or_update_game_mod(self._game_id, mod)

        # If config version is missing, check our version file as fallback.
        # If that's also missing, version stays None → update check will flag as "update available"
        # so the user can click Update, which writes the version file and starts tracking.
        if not mod.get("version") and not mod.get("_virtual"):
            saved_ver = read_fsmm_version(self._get_mod_version_dir(mod["id"]))
            if saved_ver:
                mod = dict(mod)
                mod["version"] = saved_ver
                self._config.add_or_update_game_mod(self._game_id, mod)

        card = _ModCard(mod, self._game_id, self._is_me3_game, self._pending)
        # Insert in the installed section (before trending separator / stretch)
        self._layout.insertWidget(self._installed_insert_index(), card)
        self._cards[mod["id"]] = card

    def _update_header(self):
        installed_count = sum(1 for c in self._cards.values() if not c.is_virtual)
        if installed_count:
            self._header_lbl.setText(f"Mods Installed  ({installed_count})")
        else:
            self._header_lbl.setText("Mods Installed")

    # ------------------------------------------------------------------
    # Update checks
    # ------------------------------------------------------------------
    def _start_update_checks(self):
        api_key = self._config.get_nexus_api_key()
        for mod_id, card in self._cards.items():
            if card.is_virtual:
                continue
            mod = card.mod
            if not mod.get("nexus_mod_id"):
                card._status_lbl.setText("No Nexus info")
                card._status_lbl.setStyleSheet("font-size:11px;color:#555577;")
                continue
            if not api_key:
                card._status_lbl.setText("Connect Nexus for update checks")
                card._status_lbl.setStyleSheet("font-size:11px;color:#555577;")
                continue
            self._spawn_update_check(mod)

    def _spawn_update_check(self, mod: dict):
        api_key = self._config.get_nexus_api_key()
        pending = self._pending
        mod_id = mod["id"]
        version_dir = self._get_mod_version_dir(mod_id)

        def _work():
            from app.core.mod_updater import version_compare
            svc = NexusService(api_key)
            domain = mod.get("nexus_domain", "")
            nid = mod.get("nexus_mod_id", 0)
            # Use the Nexus mod-page version as single source of truth
            mod_info = svc.get_mod_info(domain, nid)
            if "error" in mod_info:
                pending.put(("update_result", mod_id, {"error": mod_info["error"]}))
                return
            latest = mod_info.get("version", "")
            # Use config version; fall back to our version file if config is empty
            installed = mod.get("version") or read_fsmm_version(version_dir) or ""
            has_update = False
            if installed and latest:
                has_update = version_compare(installed, latest) < 0
            elif latest:
                has_update = True
            print(f"[UPDATE CHECK] {mod.get('name')}: installed={installed!r} latest={latest!r} has_update={has_update}", flush=True)
            pending.put(("update_result", mod_id, {"latest_version": latest, "has_update": has_update}))

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # Trending mods
    # ------------------------------------------------------------------
    def _start_trending_fetch(self):
        api_key = self._config.get_nexus_api_key()
        if not api_key or self._trending_loaded:
            return
        nexus_domain = self._gdef.get("nexus_domain", "")
        if not nexus_domain:
            return
        pending = self._pending

        def _work():
            svc = NexusService(api_key)
            mods = svc.get_trending_mods(nexus_domain)
            # Fetch game categories to identify utility/tool categories
            cats = svc.get_game_categories(nexus_domain)
            _EXCLUDE_CAT_NAMES = {"utilities", "modding tools", "tools",
                                  "cheats and god items", "save games",
                                  "cheat", "bug fixes"}
            excluded_cat_ids: set[int] = set()
            for cat in cats:
                cat_name = cat.get("name", "").lower()
                if any(exc in cat_name for exc in _EXCLUDE_CAT_NAMES):
                    excluded_cat_ids.add(cat.get("category_id", -1))
            pending.put(("trending_result", mods, excluded_cat_ids))

        threading.Thread(target=_work, daemon=True).start()

    def _on_trending_result(self, trending_mods: list[dict],
                            excluded_cats: set[int]):
        if not trending_mods or self._trending_loaded:
            return
        self._trending_loaded = True

        # Collect installed nexus_mod_ids to filter out
        installed_ids = set()
        for card in self._cards.values():
            nid = card.mod.get("nexus_mod_id")
            if nid:
                installed_ids.add(nid)

        # Build separator
        sep = QLabel("Other Popular Mods")
        sep.setObjectName("section_header")
        sep.setContentsMargins(0, 12, 0, 4)
        self._layout.insertWidget(self._layout.count() - 1, sep)
        self._trending_separator = sep

        # Keywords for non-content mods that ME3 can't load or the app
        # already handles — checked against name AND summary.
        _SKIP_KEYWORDS = (
            "mod engine", "modengine", "cheat engine", "cheat table",
            "save editor", "save manager", "mod loader", "mod manager",
            "mod organizer", "debug tool", "practice tool", "trainer",
            "anti-cheat", "anticheat",
        )

        count = 0
        for tm in trending_mods:
            nid = tm.get("mod_id", 0)
            if nid in installed_ids:
                continue
            # Skip mods in excluded categories (utilities, tools, cheats, etc.)
            if tm.get("category_id", 0) in excluded_cats:
                continue
            text_lower = (tm.get("name", "") + " " + tm.get("summary", "")).lower()
            if any(kw in text_lower for kw in _SKIP_KEYWORDS):
                continue

            mod_id = f"trending-{nid}"
            virtual_mod = {
                "id": mod_id,
                "name": tm.get("name", "Unknown"),
                "version": None,
                "path": "",
                "nexus_domain": tm.get("domain_name", self._gdef.get("nexus_domain", "")),
                "nexus_mod_id": nid,
                "enabled": False,
                "_virtual": True,
            }
            card = _ModCard(virtual_mod, self._game_id, self._is_me3_game, self._pending)

            # Show summary + download count
            parts = []
            summary = tm.get("summary", "")
            if summary:
                parts.append(summary[:80] + "…" if len(summary) > 80 else summary)
            downloads = tm.get("mod_downloads", 0)
            if downloads:
                parts.append(f"{downloads:,} downloads")
            if parts:
                card._status_lbl.setText("  |  ".join(parts))
                card._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")

            self._layout.insertWidget(self._layout.count() - 1, card)
            self._trending_cards[mod_id] = card
            count += 1
            if count >= 10:
                break

        # Remove separator if nothing was added
        if not self._trending_cards and self._trending_separator:
            self._layout.removeWidget(self._trending_separator)
            self._trending_separator.deleteLater()
            self._trending_separator = None

    # ------------------------------------------------------------------
    # Action routing
    # ------------------------------------------------------------------
    def _get_mod_ini_path(self, mod_id: str) -> str | None:
        """
        Return the INI path for a mod, checking the card's stored path first and
        falling back to the game definition's canonical config path for non-ME3 games.
        """
        card = self._cards.get(mod_id)
        if not card:
            return None
        ini = card.get_ini_path()
        if ini:
            return ini
        # Fallback: non-ME3 games may have a stale path; check the known INI location
        if not self._is_me3_game:
            config_rel = self._gdef.get("config_relative", "")
            game_path = self._game_info.get("install_path", "")
            if config_rel and game_path:
                candidate = os.path.join(game_path, config_rel)
                if os.path.isfile(candidate):
                    return candidate
        return None

    def _ensure_me3_available(self) -> bool:
        """Check ME3 CLI is available for ME3-compatible games. Returns True if OK."""
        if not self._is_me3_game:
            return True
        me3_path = find_me3_executable(self._config.get_me3_path())
        if me3_path:
            return True
        self.log_message.emit(
            "ME3 CLI not found — install Mod Engine 3 or set its path in App Settings", "error")
        return False

    def _route_action(self, mod_id: str):
        card = self._cards.get(mod_id) or self._trending_cards.get(mod_id)
        if not card:
            return
        if card.is_virtual:
            if not self._ensure_me3_available():
                return
            self._do_install(mod_id)
        elif card._has_update:
            if not self._ensure_me3_available():
                return
            self._do_update(mod_id)
        elif self._get_mod_ini_path(mod_id):
            self._do_manage(mod_id)
        else:
            self._do_uninstall(mod_id)

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------
    def _do_install(self, mod_id: str):
        card = self._cards.get(mod_id) or self._trending_cards.get(mod_id)
        if not card:
            return
        mod = card.mod
        api_key = self._config.get_nexus_api_key()

        if mod.get("nexus_mod_id") and api_key:
            # Download from Nexus
            self._run_nexus_install(mod_id, mod)
        elif mod.get("nexus_mod_id") and not api_key:
            # Mod has Nexus info but no API key — open SSO dialog
            from app.ui.nexus_widget import NexusApiKeyDialog
            dlg = NexusApiKeyDialog(parent=self)
            if dlg.exec() == QDialog.Accepted and dlg.api_key:
                self._config.set_nexus_api_key(dlg.api_key)
                self._validate_and_save_nexus_key(dlg.api_key)
                self._run_nexus_install(mod_id, mod)
        else:
            # No Nexus info — fall back to zip browser
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            path, _ = QFileDialog.getOpenFileName(
                self, f"Select archive for {mod.get('name', mod_id)}", downloads,
                "Archives (*.zip *.7z *.rar);;All files (*)"
            )
            if path:
                self._run_zip_install(mod_id, mod, path)

    def _run_nexus_install(self, mod_id: str, mod: dict):
        gdef = self._gdef
        game_id = self._game_id
        game_info = self._game_info
        config = self._config
        pending = self._pending
        temp_dir = os.path.join(config.get_mods_dir(), "_tmp")
        is_me3 = game_id in ME3_GAME_MAP
        # ME3 games: install into a dedicated per-mod subdirectory
        # Non-ME3 games (AC6): extract into the game dir; path points to the mod marker folder
        me3_mod_dir = os.path.join(config.get_game_mod_dir(game_id), mod_id)
        if is_me3:
            os.makedirs(me3_mod_dir, exist_ok=True)
        mod_path = me3_mod_dir if is_me3 else os.path.join(
            game_info.get("install_path", ""), gdef.get("mod_marker_relative", ""))

        fake_gdef = dict(gdef)
        fake_gdef["nexus_domain"] = mod.get("nexus_domain", "")
        fake_gdef["nexus_mod_id"] = mod.get("nexus_mod_id", 0)

        def _work():
            svc = NexusService(config.get_nexus_api_key())

            def _cb(pct, msg):
                pending.put(("install_progress", mod_id, pct, msg))

            dl = svc.download_latest_mod(game_id, fake_gdef, temp_dir, progress_callback=_cb)
            if not dl.get("success"):
                fail = {"success": False, "message": dl.get("error", "Download failed")}
                if dl.get("requires_premium"):
                    fail["requires_premium"] = True
                pending.put(("install_done", mod_id, fail, {}))
                return
            zip_path = dl["zip_path"]
            # Prefer Nexus API version > file metadata > zip-extracted
            version_hint = dl.get("api_version") or dl.get("version", "")
            result = install_mod_from_zip(
                zip_path,
                game_info.get("install_path", ""),
                gdef,
                target_dir=me3_mod_dir if is_me3 else None,
            )
            version = version_hint or result.get("version") or ""
            mod_dict = {
                "id": mod_id,
                "name": mod.get("name", mod_id),
                "version": version,
                "path": mod_path,
                "nexus_domain": mod.get("nexus_domain", ""),
                "nexus_mod_id": mod.get("nexus_mod_id", 0),
                "enabled": True,
            }
            pending.put(("install_done", mod_id, result, mod_dict))

        threading.Thread(target=_work, daemon=True).start()

    def _run_zip_install(self, mod_id: str, mod: dict, zip_path: str):
        gdef = self._gdef
        game_id = self._game_id
        game_info = self._game_info
        config = self._config
        pending = self._pending
        is_me3 = game_id in ME3_GAME_MAP
        me3_mod_dir = os.path.join(config.get_game_mod_dir(game_id), mod_id)
        if is_me3:
            os.makedirs(me3_mod_dir, exist_ok=True)
        mod_path = me3_mod_dir if is_me3 else os.path.join(
            game_info.get("install_path", ""), gdef.get("mod_marker_relative", ""))

        def _work():
            result = install_mod_from_zip(
                zip_path,
                game_info.get("install_path", ""),
                gdef,
                target_dir=me3_mod_dir if is_me3 else None,
            )
            version = result.get("version") or ""
            mod_dict = {
                "id": mod_id,
                "name": mod.get("name", mod_id),
                "version": version,
                "path": mod_path,
                "nexus_domain": mod.get("nexus_domain", ""),
                "nexus_mod_id": mod.get("nexus_mod_id", 0),
                "enabled": True,
            }
            pending.put(("install_done", mod_id, result, mod_dict))

        threading.Thread(target=_work, daemon=True).start()

    def _validate_and_save_nexus_key(self, api_key: str):
        """Validate a newly-obtained API key and save user info in background."""
        pending = self._pending

        def _work():
            svc = NexusService(api_key)
            result = svc.validate_user()
            if "error" not in result:
                pending.put(("nexus_validated", result))

        threading.Thread(target=_work, daemon=True).start()

    def _on_install_done(self, mod_id: str, result: dict, mod_dict: dict):
        version = mod_dict.get("version", "")
        if result.get("success"):
            is_trending = mod_id in self._trending_cards
            if is_trending:
                installed_id = slugify(mod_dict.get("name", str(mod_dict.get("nexus_mod_id", mod_id))))
                mod_dict["id"] = installed_id
            else:
                installed_id = mod_id

            self._config.add_or_update_game_mod(self._game_id, mod_dict)
            if version:
                write_fsmm_version(self._get_mod_version_dir(installed_id), version)
            self._rewrite_profile()

            # Rebuild installed cards to reflect new state
            self._populate_mod_list()
            self._scroll.verticalScrollBar().setValue(0)

            if is_trending:
                # Remove from trending section
                tc = self._trending_cards.pop(mod_id, None)
                if tc:
                    self._layout.removeWidget(tc)
                    tc.deleteLater()
                if not self._trending_cards and self._trending_separator:
                    self._layout.removeWidget(self._trending_separator)
                    self._trending_separator.deleteLater()
                    self._trending_separator = None

            self.log_message.emit(f"Installed {mod_dict.get('name', mod_id)}", "success")
            self.mod_installed.emit()
            if mod_dict.get("nexus_mod_id") and self._config.get_nexus_api_key():
                self._spawn_update_check(mod_dict)
        else:
            if result.get("requires_premium"):
                self._handle_premium_fallback(mod_id)
                return
            # Update the card to show the error
            card = self._cards.get(mod_id) or self._trending_cards.get(mod_id)
            if card:
                card.on_install_done(result, version)
            self.log_message.emit(result.get("message", "Install failed"), "error")

    # ------------------------------------------------------------------
    # Premium fallback — open browser + prompt for zip
    # ------------------------------------------------------------------
    def _handle_premium_fallback(self, mod_id: str):
        """Open browser to Nexus and prompt user to select a downloaded file."""
        import webbrowser
        card = self._cards.get(mod_id) or self._trending_cards.get(mod_id)
        if card:
            card.set_installing(False)
        mod = card.mod if card else {}
        domain = mod.get("nexus_domain", "")
        nid = mod.get("nexus_mod_id", 0)
        nexus_url = f"https://www.nexusmods.com/{domain}/mods/{nid}?tab=files" if domain and nid else ""
        if nexus_url:
            webbrowser.open(nexus_url)
        self.log_message.emit(
            "Free Nexus account — opening mod page in your browser.",
            "warning"
        )
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Download Mod Manually")
        msg.setText(
            f"<b>Download \"{mod.get('name', mod_id)}\" from Nexus Mods</b>"
        )
        msg.setInformativeText(
            "The mod page has been opened in your browser.\n\n"
            "1. Click the FILES tab on the Nexus page\n"
            "2. Click \"Manual Download\" on the file you want\n"
            "3. Wait for the download to finish\n"
            "4. Click OK below, then browse to the downloaded\n"
            "   .zip / .7z / .rar file (usually in your Downloads folder)\n\n"
            "Tip: Nexus Premium members get one-click installs\n"
            "directly from the app."
        )
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if msg.exec() != QMessageBox.Ok:
            return
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select downloaded archive for {mod.get('name', mod_id)}", downloads,
            "Archives (*.zip *.7z *.rar);;All files (*)"
        )
        if path:
            self._run_zip_install(mod_id, mod, path)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def _do_update(self, mod_id: str):
        card = self._cards.get(mod_id)
        if not card:
            return
        mod = card.mod
        api_key = self._config.get_nexus_api_key()
        if not api_key:
            self.log_message.emit("No Nexus API key — cannot auto-update", "error")
            return

        gdef = self._gdef
        game_id = self._game_id
        game_info = self._game_info
        config = self._config
        pending = self._pending
        is_me3 = game_id in ME3_GAME_MAP

        old_path = mod.get("path", "")
        me3_mod_dir = os.path.join(config.get_game_mod_dir(game_id), mod_id)

        # Detect if mod is currently in the game directory and needs migrating
        # to the app-managed ME3 mod directory.  Use normcase for
        # case-insensitive comparison on Windows.
        needs_migration = False
        if is_me3 and old_path:
            install_path = game_info.get("install_path", "")
            if install_path and os.path.normcase(os.path.normpath(old_path)).startswith(
                    os.path.normcase(os.path.normpath(install_path))):
                needs_migration = True

        mod_target = me3_mod_dir if is_me3 else old_path

        fake_gdef = dict(gdef)
        fake_gdef["nexus_domain"] = mod.get("nexus_domain", "")
        fake_gdef["nexus_mod_id"] = mod.get("nexus_mod_id", 0)

        def _work():
            from app.core.mod_installer import _merge_ini_settings

            svc = NexusService(api_key)
            temp_dir = os.path.join(config.get_mods_dir(), "_tmp")

            def _cb(pct, msg):
                pending.put(("update_progress", mod_id, pct, msg))

            dl = svc.download_latest_mod(game_id, fake_gdef, temp_dir, progress_callback=_cb)
            if not dl.get("success"):
                fail = {"success": False, "message": dl.get("error", "Download failed")}
                if dl.get("requires_premium"):
                    fail["requires_premium"] = True
                pending.put(("update_done", mod_id, fail, ""))
                return

            # If migrating, read old INI settings before extraction overwrites them
            old_ini_data: dict[str, bytes] = {}
            if needs_migration and os.path.isdir(old_path):
                for root, _dirs, files in os.walk(old_path):
                    for fname in files:
                        if fname.endswith(".ini"):
                            try:
                                with open(os.path.join(root, fname), "rb") as fh:
                                    old_ini_data[fname] = fh.read()
                            except Exception:
                                pass

            zip_path = dl["zip_path"]
            # Prefer Nexus API version > file metadata > zip-extracted
            version_hint = dl.get("api_version") or dl.get("version", "")

            if is_me3:
                os.makedirs(me3_mod_dir, exist_ok=True)

            result = install_mod_from_zip(
                zip_path,
                game_info.get("install_path", ""),
                gdef,
                target_dir=mod_target if is_me3 else None,
            )

            if needs_migration and result.get("success"):
                # Merge old settings into the newly extracted INIs
                if old_ini_data:
                    for root, _dirs, files in os.walk(me3_mod_dir):
                        for fname in files:
                            if fname.endswith(".ini") and fname in old_ini_data:
                                _merge_ini_settings(
                                    os.path.join(root, fname),
                                    old_ini_data[fname],
                                )

                # Tag result so _on_update_done updates the path
                # (old files in game dir are left untouched)
                result["_new_path"] = me3_mod_dir

            pending.put(("update_done", mod_id, result, version_hint))

        threading.Thread(target=_work, daemon=True).start()

    def _on_update_done(self, mod_id: str, result: dict, version: str):
        if not result.get("success") and result.get("requires_premium"):
            self._handle_premium_fallback(mod_id)
            return
        # version already has API-first priority from _do_update; fall back to zip-extracted
        effective_version = version or result.get("version") or ""
        card = self._cards.get(mod_id)
        if card:
            card.on_install_done(result, effective_version)
        if result.get("success"):
            mods = self._config.get_game_mods(self._game_id)
            for m in mods:
                if m["id"] == mod_id:
                    if effective_version:
                        m["version"] = effective_version
                    # Update path: migration sets _new_path, otherwise fix stale paths
                    if result.get("_new_path"):
                        m["path"] = result["_new_path"]
                    elif not self._is_me3_game:
                        correct_path = os.path.join(
                            self._game_info.get("install_path", ""),
                            self._gdef.get("mod_marker_relative", ""),
                        )
                        if correct_path:
                            m["path"] = correct_path
                    self._config.add_or_update_game_mod(self._game_id, m)
                    break
            if effective_version:
                write_fsmm_version(self._get_mod_version_dir(mod_id), effective_version)
            self._rewrite_profile()
            name = card.mod.get("name", mod_id) if card else mod_id
            self.log_message.emit(f"Updated {name}", "success")
            self.mod_installed.emit()
        else:
            self.log_message.emit(result.get("message", "Update failed"), "error")

    # ------------------------------------------------------------------
    # Manage (open settings dialog)
    # ------------------------------------------------------------------
    def _do_manage(self, mod_id: str):
        card = self._cards.get(mod_id)
        if not card:
            return
        ini_path = self._get_mod_ini_path(mod_id) or ""
        mod = card.mod
        defaults = self._gdef.get("defaults", {})
        from app.ui.dialogs.mod_settings_dialog import ModSettingsDialog
        dlg = ModSettingsDialog(ini_path, defaults, mod.get("name", mod_id), parent=self)
        dlg.uninstall_requested.connect(lambda: self._do_uninstall(mod_id))
        dlg.exec()

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------
    def _do_uninstall(self, mod_id: str):
        card = self._cards.get(mod_id)
        mod_name = card.mod.get("name", mod_id) if card else mod_id
        dlg = ConfirmDialog(
            "Remove Mod",
            f"Remove '{mod_name}' and delete all its files?\nThis cannot be undone.",
            confirm_text="Remove",
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        if card:
            mod_path = card.mod.get("path", "")
            if mod_path and os.path.isdir(mod_path):
                try:
                    shutil.rmtree(mod_path)
                except Exception as e:
                    self.log_message.emit(f"Could not delete mod files: {e}", "warning")

        self._config.remove_game_mod(self._game_id, mod_id)
        self._rewrite_profile()

        if card:
            self._layout.removeWidget(card)
            card.deleteLater()
            del self._cards[mod_id]

        self._update_header()
        # Show virtual co-op entry again if it was the coop mod
        coop_id = f"{self._game_id}-coop"
        if mod_id == coop_id and self._gdef.get("nexus_mod_id"):
            virtual = {
                "id": coop_id,
                "name": self._gdef.get("mod_name", "Co-op Mod"),
                "version": None,
                "path": "",
                "nexus_domain": self._gdef.get("nexus_domain", ""),
                "nexus_mod_id": self._gdef.get("nexus_mod_id", 0),
                "enabled": False,
                "_virtual": True,
            }
            self._add_card(virtual)

        self.log_message.emit(f"Removed {mod_name}", "info")

    # ------------------------------------------------------------------
    # Add mod
    # ------------------------------------------------------------------
    def _on_add_mod(self):
        from app.ui.dialogs.add_mod_dialog import AddModDialog
        dlg = AddModDialog(
            self._game_id, self._game_info, self._config, self._gdef,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted or not dlg.result:
            return

        # Dialog handled the full download+install — save to config and refresh
        mod_dict = dlg.result
        mod_id = mod_dict["id"]

        # Avoid slug collision
        if mod_id in self._cards:
            import time
            mod_id = f"{mod_id}-{int(time.time()) % 10000}"
            mod_dict["id"] = mod_id

        self._config.add_or_update_game_mod(self._game_id, mod_dict)
        if mod_dict.get("version"):
            write_fsmm_version(self._get_mod_version_dir(mod_id), mod_dict["version"])
        self._rewrite_profile()
        self._populate_mod_list()
        self._update_header()
        self._scroll.verticalScrollBar().setValue(0)
        self.log_message.emit(f"Installed {mod_dict.get('name', mod_id)}", "success")
        self.mod_installed.emit()

        # Warn if the mod has no content ME3 can load
        if self._is_me3_game and mod_dict.get("path") and os.path.isdir(mod_dict["path"]):
            dlls = _find_native_dlls(mod_dict["path"])
            assets = _has_asset_content(mod_dict["path"])
            if not dlls and not assets:
                self.log_message.emit(
                    f"Note: {mod_dict.get('name', mod_id)} has no DLLs or game assets — "
                    f"it won't appear in the ME3 profile. It may be a standalone tool.",
                    "warning"
                )

        # Check for updates on the newly installed mod
        if mod_dict.get("nexus_mod_id") and self._config.get_nexus_api_key():
            self._spawn_update_check(mod_dict)

    # ------------------------------------------------------------------
    # Link to Nexus
    # ------------------------------------------------------------------
    def _on_link_nexus(self, mod_id: str, domain: str, nexus_mod_id: int):
        mod = None
        for m in self._config.get_game_mods(self._game_id):
            if m["id"] == mod_id:
                mod = dict(m)
                break
        if not mod:
            return
        mod["nexus_domain"] = domain
        mod["nexus_mod_id"] = nexus_mod_id
        self._config.add_or_update_game_mod(self._game_id, mod)
        self.log_message.emit(f"Linked {mod.get('name', mod_id)} to Nexus", "info")
        # Trigger update check for the newly linked mod
        card = self._cards.get(mod_id)
        if card:
            card._status_lbl.setText("Checking for updates…")
            card._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
            self._spawn_update_check(mod)

    # ------------------------------------------------------------------
    # ME3 profile rewrite
    # ------------------------------------------------------------------
    def _rewrite_profile(self):
        if not self._is_me3_game:
            return
        me3_path = find_me3_executable(self._config.get_me3_path())
        if not me3_path:
            return
        mods = self._config.get_game_mods(self._game_id)
        pkg_paths = []
        native_paths = []
        for m in mods:
            if not m.get("enabled") or not m.get("path"):
                continue
            p = m["path"]
            if p.lower().endswith(".dll"):
                native_paths.append(p)
            elif os.path.isdir(p):
                # Scan directory for DLLs to load as natives
                dlls = _find_native_dlls(p)
                if dlls:
                    native_paths.extend(dlls)
                # Only add as package if it has asset override content
                if _has_asset_content(p):
                    pkg_paths.append(p)
        write_me3_profile(self._game_id, pkg_paths, me3_path, native_dlls=native_paths)

    # ------------------------------------------------------------------
    # Refresh (called after scan / settings saved)
    # ------------------------------------------------------------------
    def refresh(self, game_info: dict):
        self._game_info = game_info
        # Clear trending section
        for tc in self._trending_cards.values():
            self._layout.removeWidget(tc)
            tc.deleteLater()
        self._trending_cards.clear()
        if self._trending_separator:
            self._layout.removeWidget(self._trending_separator)
            self._trending_separator.deleteLater()
            self._trending_separator = None
        self._trending_loaded = False

        self._populate_mod_list()

        # Ensure ME3 profile exists if this game has enabled mods
        if self._is_me3_game:
            mods = self._config.get_game_mods(self._game_id)
            if any(m.get("enabled") and m.get("path") for m in mods):
                self._rewrite_profile()

        QTimer.singleShot(200, self._start_update_checks)
        QTimer.singleShot(400, self._start_trending_fetch)
