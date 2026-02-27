"""
Launch tab — launch game via ME3 or direct, desktop shortcut, player count.
"""

import os
import subprocess
import threading
import queue as _queue
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QFont
from app.config.config_manager import ConfigManager
from app.config.game_definitions import GAME_DEFINITIONS
from app.core.me3_service import (launch_game_with_me3, launch_game_direct,
                                  find_me3_executable, create_desktop_shortcut,
                                  ME3_GAME_MAP)
from app.services.steam_service import get_player_count, download_cover_art


class LaunchTab(QWidget):
    log_message = Signal(str, str)  # message, level

    def __init__(self, game_id: str, game_info: dict, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._gdef = GAME_DEFINITIONS.get(game_id, {})
        self._process = None
        self._fetching_count = False

        # Thread-safe queue: daemon threads POST results here, never touch self
        self._pending: _queue.SimpleQueue = _queue.SimpleQueue()

        # Drain the queue on the main thread every 100 ms
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_updates)
        self._poll_timer.start(100)

        self._build()

        # Delay thread start until the event loop is running
        QTimer.singleShot(0, self._load_cover_async)
        QTimer.singleShot(0, self._fetch_player_count)

        # Recurring player count refresh every 5 seconds
        self._player_timer = QTimer(self)
        self._player_timer.timeout.connect(self._fetch_player_count)
        self._player_timer.start(60000)

    # ------------------------------------------------------------------
    # Main-thread queue drain (safe — QTimer stops when widget deleted)
    # ------------------------------------------------------------------
    def _poll_updates(self):
        try:
            while True:
                tag, data = self._pending.get_nowait()
                if tag == "cover":
                    self._apply_cover(data)
                elif tag == "count":
                    self._apply_player_count(data)
                elif tag == "count_done":
                    self._fetching_count = False
        except _queue.Empty:
            pass

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)

        # ── Center card ───────────────────────────────────────
        center = QWidget()
        center.setObjectName("card")
        center.setMaximumWidth(520)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(30, 30, 30, 30)
        center_layout.setSpacing(16)
        center_layout.setAlignment(Qt.AlignHCenter)

        # Cover art
        self._cover = QLabel()
        self._cover.setFixedSize(160, 240)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setStyleSheet(
            "background:#181830;border:1px solid #2a2a4a;border-radius:8px;"
            "font-size:40px;color:#3a3a5a;"
        )
        self._cover.setFont(QFont("Segoe MDL2 Assets", 32))
        self._cover.setText("\uE7FC")
        center_layout.addWidget(self._cover, alignment=Qt.AlignHCenter)

        # Game name
        name_lbl = QLabel(self._game_info.get("name", ""))
        name_lbl.setStyleSheet("font-size:20px;font-weight:700;color:#ffffff;")
        name_lbl.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(name_lbl)

        # Mod name
        mod_lbl = QLabel(self._gdef.get("mod_name", ""))
        mod_lbl.setStyleSheet("font-size:12px;color:#8888aa;")
        mod_lbl.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(mod_lbl)

        # Player count
        self._players_lbl = QLabel("👥 Loading player count…")
        self._players_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        self._players_lbl.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self._players_lbl)

        # Mod status
        mod_installed = self._game_info.get("mod_installed", False)
        launcher_exists = self._game_info.get("launcher_exists", False)
        status_color = "#4ecca3" if (mod_installed and launcher_exists) else "#e74c3c"
        status_text = "✓ Mod installed" if (mod_installed and launcher_exists) else "⚠ Mod not installed"
        self._status_lbl = QLabel(status_text)
        self._status_lbl.setStyleSheet(f"font-size:12px;color:{status_color};font-weight:600;")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self._status_lbl)

        # Launch button
        self._launch_btn = QPushButton("▶  Launch Co-op")
        self._launch_btn.setObjectName("btn_launch")
        self._launch_btn.setFixedHeight(48)
        self._launch_btn.setFixedWidth(220)
        self._launch_btn.setEnabled(launcher_exists or bool(ME3_GAME_MAP.get(self._game_id)))
        self._launch_btn.clicked.connect(self._on_launch)
        center_layout.addWidget(self._launch_btn, alignment=Qt.AlignHCenter)

        # Launch mode label
        self._mode_lbl = QLabel()
        self._mode_lbl.setStyleSheet("font-size:10px;color:#555577;")
        self._mode_lbl.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self._mode_lbl)
        self._update_mode_label()

        # Shortcut button
        self._shortcut_btn = QPushButton("📌  Create Desktop Shortcut")
        self._shortcut_btn.setObjectName("sidebar_mgmt_btn")
        self._shortcut_btn.setFixedWidth(200)
        self._shortcut_btn.setEnabled(launcher_exists)
        self._shortcut_btn.clicked.connect(self._on_shortcut)
        center_layout.addWidget(self._shortcut_btn, alignment=Qt.AlignHCenter)

        layout.addWidget(center, alignment=Qt.AlignHCenter)
        layout.addStretch()

    def _update_mode_label(self):
        use_me3 = self._config.get_use_me3()
        me3_path = find_me3_executable(self._config.get_me3_path())
        has_me3_support = bool(ME3_GAME_MAP.get(self._game_id))

        if use_me3 and me3_path and has_me3_support:
            self._mode_lbl.setText("via Mod Engine 3")
        elif self._game_info.get("launcher_exists"):
            self._mode_lbl.setText("via Direct Launcher")
        else:
            self._mode_lbl.setText("Launcher not found — install the mod first")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_launch(self):
        # Check cooppassword before launch
        if not self._check_coop_password():
            return

        self._launch_btn.setEnabled(False)
        self._launch_btn.setText("Launching…")

        use_me3 = self._config.get_use_me3()
        me3_path = find_me3_executable(self._config.get_me3_path())
        has_me3_support = bool(ME3_GAME_MAP.get(self._game_id))

        def _cb(msg):
            self.log_message.emit(msg, "info")

        if use_me3 and me3_path and has_me3_support:
            proc = launch_game_with_me3(self._game_id, me3_path, terminal_callback=_cb)
        else:
            launcher = self._game_info.get("launcher_path", "")
            proc = launch_game_direct(launcher, terminal_callback=_cb)

        if proc:
            self.log_message.emit(f"Launched {self._game_info['name']}", "success")
        else:
            self.log_message.emit(f"Failed to launch {self._game_info['name']}", "error")

        QTimer.singleShot(3000, lambda: (
            self._launch_btn.setEnabled(True),
            self._launch_btn.setText("▶  Launch Co-op")
        ))

    def _find_coop_ini(self) -> str | None:
        """Locate the co-op settings INI, checking the mod's stored path
        first (ME3 mod dir), then falling back to the game directory."""
        coop_id = f"{self._game_id}-coop"
        for m in self._config.get_game_mods(self._game_id):
            if m["id"] == coop_id and m.get("path") and os.path.isdir(m["path"]):
                for root, _dirs, files in os.walk(m["path"]):
                    for f in files:
                        if f.endswith(".ini"):
                            return os.path.join(root, f)
                break
        config_rel = self._gdef.get("config_relative", "")
        install_path = self._game_info.get("install_path", "")
        if config_rel and install_path:
            candidate = os.path.join(install_path, config_rel)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _check_coop_password(self) -> bool:
        """Check if the co-op INI has an empty cooppassword. Prompt if so."""
        if "cooppassword" not in self._gdef.get("defaults", {}):
            return True

        ini_path = self._find_coop_ini()
        if not ini_path:
            return True

        from app.core.ini_parser import read_ini_value, save_ini_settings
        password = read_ini_value(ini_path, "cooppassword")
        if password:
            return True

        from PySide6.QtWidgets import QDialog
        from app.ui.dialogs.coop_password_dialog import CoopPasswordDialog
        dlg = CoopPasswordDialog(self._game_info.get("name", self._game_id), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return False

        save_ini_settings(ini_path, {"cooppassword": dlg.password})
        self.log_message.emit(f"Co-op password saved", "info")
        return True

    def _on_shortcut(self):
        launcher = self._game_info.get("launcher_path", "")
        result = create_desktop_shortcut(self._game_info["name"], launcher)
        level = "success" if result["success"] else "error"
        self.log_message.emit(result["message"], level)

    # ------------------------------------------------------------------
    # Background loaders — capture only the queue, never self
    # ------------------------------------------------------------------
    def _load_cover_async(self):
        app_id = self._game_info.get("steam_app_id")
        if not app_id:
            return

        cache_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "resources", "covers")
        os.makedirs(cache_dir, exist_ok=True)
        cover_path = os.path.join(cache_dir, f"{app_id}.jpg")
        pending = self._pending  # capture queue object, NOT self

        def _load():
            if not os.path.isfile(cover_path):
                download_cover_art(app_id, cover_path)
            if os.path.isfile(cover_path):
                pending.put(("cover", cover_path))

        threading.Thread(target=_load, daemon=True).start()

    def _fetch_player_count(self):
        app_id = self._game_info.get("steam_app_id")
        if not app_id:
            self._players_lbl.setText("")
            return
        if self._fetching_count:
            return
        self._fetching_count = True
        pending = self._pending  # capture queue object, NOT self

        def _work():
            try:
                count = get_player_count(app_id)
                text = (
                    f"👥 {count:,} players online now" if count is not None
                    else "👥 Player count unavailable"
                )
                pending.put(("count", text))
            finally:
                pending.put(("count_done", None))

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # UI update slots (always called on main thread via _poll_updates)
    # ------------------------------------------------------------------
    def _apply_cover(self, cover_path: str):
        if cover_path and os.path.isfile(cover_path):
            pix = QPixmap(cover_path).scaled(
                160, 240, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            x = max(0, (pix.width() - 160) // 2)
            y = max(0, (pix.height() - 240) // 2)
            pix = pix.copy(x, y, 160, 240)
            self._cover.setPixmap(pix)
            self._cover.setText("")
            self._cover.setStyleSheet("border:1px solid #2a2a4a;border-radius:8px;")

    def _apply_player_count(self, text: str):
        self._players_lbl.setText(text)

    def refresh(self, game_info: dict):
        self._game_info = game_info
        self._update_mode_label()
