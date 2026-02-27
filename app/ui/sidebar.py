"""
Left sidebar — Nexus widget, game list, management buttons.
"""

import os
import threading
import queue as _queue
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QFrame, QScrollArea, QSizePolicy,
                                QSpacerItem)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QIcon, QFont, QPainter, QColor

from app.config.config_manager import ConfigManager

# Windows 11 native icon font
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
from app.ui.nexus_widget import NexusWidget


class GameButton(QPushButton):
    """Sidebar game button with logo + player count + play button + optional update badge."""

    launch_requested = Signal(str)  # game_id

    def __init__(self, game_id: str, game_info: dict, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self.setObjectName("sidebar_btn")
        self.setCheckable(True)
        self.setFixedHeight(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)

        # Left column: logo + player count
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(2)

        self._logo_lbl = QLabel()
        self._logo_lbl.setFixedHeight(32)
        self._logo_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._logo_lbl.setStyleSheet("background:transparent;")
        left_col.addWidget(self._logo_lbl)

        self._players_lbl = QLabel()
        self._players_lbl.setStyleSheet("font-size:9px;color:#555577;background:transparent;")
        self._players_lbl.setVisible(False)
        left_col.addWidget(self._players_lbl)

        layout.addLayout(left_col)
        layout.addStretch()

        # Update dot
        self._update_dot = QLabel("●")
        self._update_dot.setFixedSize(10, 10)
        self._update_dot.setStyleSheet("color:#ff9800;font-size:7px;background:transparent;")
        self._update_dot.setVisible(False)
        layout.addWidget(self._update_dot)

        # Play button — child QPushButton captures its own click,
        # so clicking it does NOT trigger the parent GameButton's clicked signal
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setFixedSize(56, 26)
        self._play_btn.setFlat(True)
        self._play_btn.setToolTip("Launch game")
        self._play_btn.setCursor(Qt.PointingHandCursor)
        self._play_btn.setStyleSheet(
            "QPushButton{color:#4ecca3;font-size:10px;font-weight:700;"
            "border:1px solid #4ecca3;background:transparent;border-radius:4px;"
            "padding:0 6px;}"
            "QPushButton:hover{color:#fff;background:#4ecca3;}"
            "QPushButton:pressed{background:#3dbb92;border-color:#3dbb92;}"
        )
        self._play_btn.clicked.connect(lambda: self.launch_requested.emit(self._game_id))
        layout.addWidget(self._play_btn)

    def set_player_count(self, count: int | None):
        if count is not None:
            self._players_lbl.setText(f"{count:,} playing")
            self._players_lbl.setVisible(True)
        else:
            self._players_lbl.setVisible(False)

    def set_update_available(self, available: bool):
        self._update_dot.setVisible(available)

    def load_icon(self, icon_path: str):
        if os.path.isfile(icon_path):
            pix = QPixmap(icon_path)
            # Scale to fit: max 120px wide, 32px tall
            pix = pix.scaled(120, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._logo_lbl.setPixmap(pix)

    @property
    def game_id(self):
        return self._game_id


class Sidebar(QWidget):
    game_selected = Signal(str)   # game_id
    scan_requested = Signal()
    settings_requested = Signal()
    launch_game = Signal(str)     # game_id

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._game_buttons: dict[str, GameButton] = {}
        self._current_game: str | None = None
        self._games: dict = {}
        self._fetching_counts = False
        self._pending: _queue.SimpleQueue = _queue.SimpleQueue()
        self.setObjectName("sidebar_frame")
        self.setFixedWidth(220)
        self._build()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_updates)
        self._poll_timer.start(200)
        self._player_count_timer = QTimer(self)
        self._player_count_timer.timeout.connect(self._refresh_player_counts)
        self._player_count_timer.start(60000)
        self._start_me3_version_check()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Nexus widget ───────────────────────────────────────
        self._nexus = NexusWidget(self._config)
        layout.addWidget(self._nexus)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#2a2a4a;")
        layout.addWidget(sep)

        # ── Games label ────────────────────────────────────────
        games_lbl = QLabel("GAMES")
        games_lbl.setStyleSheet(
            "font-size:10px;font-weight:700;color:#555577;"
            "letter-spacing:0.1em;padding:8px 12px 4px 12px;"
        )
        layout.addWidget(games_lbl)

        # ── Game buttons container ─────────────────────────────
        self._games_container = QWidget()
        self._games_layout = QVBoxLayout(self._games_container)
        self._games_layout.setContentsMargins(6, 0, 6, 0)
        self._games_layout.setSpacing(2)
        layout.addWidget(self._games_container)

        # No games placeholder
        self._no_games_lbl = QLabel("No games found.\nClick Scan to detect.")
        self._no_games_lbl.setStyleSheet(
            "color:#555577;font-size:11px;padding:12px 14px;"
        )
        self._no_games_lbl.setWordWrap(True)
        layout.addWidget(self._no_games_lbl)

        layout.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#2a2a4a;")
        layout.addWidget(sep2)

        # ── Management buttons ─────────────────────────────────
        mgmt = QWidget()
        mgmt_layout = QVBoxLayout(mgmt)
        mgmt_layout.setContentsMargins(6, 6, 6, 6)
        mgmt_layout.setSpacing(2)

        scan_btn = QPushButton("Scan Games")
        scan_btn.setIcon(_mdl2_icon("\uE721", 18))
        scan_btn.setObjectName("sidebar_mgmt_btn")
        scan_btn.setFixedHeight(36)
        scan_btn.clicked.connect(self.scan_requested)
        mgmt_layout.addWidget(scan_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setIcon(_mdl2_icon("\uE713", 18))
        settings_btn.setObjectName("sidebar_mgmt_btn")
        settings_btn.setFixedHeight(36)
        settings_btn.clicked.connect(self.settings_requested)
        mgmt_layout.addWidget(settings_btn)

        layout.addWidget(mgmt)

        # ── Version footer ─────────────────────────────────────
        try:
            version_file = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "VERSION")
            version = open(version_file).read().strip() if os.path.isfile(version_file) else "2.0.0"
        except Exception:
            version = "2.0.0"

        self._version_lbl = QLabel(f"v{version}")
        self._version_lbl.setStyleSheet(
            "font-size:10px;color:#3a3a5a;padding:6px 14px 2px 14px;"
        )
        layout.addWidget(self._version_lbl)

        self._me3_lbl = QLabel("ME3: checking…")
        self._me3_lbl.setStyleSheet(
            "font-size:10px;color:#3a3a5a;padding:0px 14px 6px 14px;"
        )
        layout.addWidget(self._me3_lbl)

    def populate_games(self, games: dict):
        """Rebuild the game button list."""
        # Clear existing buttons
        while self._games_layout.count():
            item = self._games_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._game_buttons.clear()

        self._no_games_lbl.setVisible(not games)

        for game_id, game_info in games.items():
            btn = GameButton(game_id, game_info)
            btn.clicked.connect(lambda checked, gid=game_id: self._on_game_clicked(gid))
            btn.launch_requested.connect(lambda gid=game_id: self.launch_game.emit(gid))

            # Load logo icon from cache
            app_id = game_info.get("steam_app_id")
            if app_id:
                resources_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "resources", "logos"
                )
                logo_path = os.path.join(resources_dir, f"{app_id}.png")
                if os.path.isfile(logo_path):
                    btn.load_icon(logo_path)

            self._games_layout.addWidget(btn)
            self._game_buttons[game_id] = btn

        # Re-select current game if still present
        if self._current_game and self._current_game in self._game_buttons:
            self._game_buttons[self._current_game].setChecked(True)

        # Store games for recurring player count refresh
        self._games = games

        # Fetch player counts in background
        self._fetch_player_counts(games)

    def _on_game_clicked(self, game_id: str):
        for gid, btn in self._game_buttons.items():
            btn.setChecked(gid == game_id)
        self._current_game = game_id
        self.game_selected.emit(game_id)

    def select_game(self, game_id: str):
        self._on_game_clicked(game_id)

    def set_update_badge(self, game_id: str, available: bool):
        if game_id in self._game_buttons:
            self._game_buttons[game_id].set_update_available(available)

    def _refresh_player_counts(self):
        """Called by recurring timer — re-fetch counts if games are loaded."""
        if self._games and not self._fetching_counts:
            self._fetch_player_counts(self._games, logos=False)

    def _fetch_player_counts(self, games: dict, logos: bool = True):
        """Fetch Steam player counts (and optionally missing logos) in background."""
        if self._fetching_counts:
            return
        self._fetching_counts = True
        pending = self._pending
        resources_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "resources", "logos"
        )

        def _work():
            try:
                from app.services.steam_service import get_player_count, download_logo
                for game_id, game_info in games.items():
                    app_id = game_info.get("steam_app_id")
                    if app_id:
                        # Download logo if missing (only on first call)
                        if logos:
                            logo_path = os.path.join(resources_dir, f"{app_id}.png")
                            if not os.path.isfile(logo_path):
                                if download_logo(app_id, logo_path):
                                    pending.put(("logo_ready", game_id, logo_path))
                        # Fetch player count
                        count = get_player_count(app_id)
                        pending.put(("player_count", game_id, count))
            finally:
                pending.put(("fetch_counts_done",))

        threading.Thread(target=_work, daemon=True).start()

    def _start_me3_version_check(self):
        config = self._config
        pending = self._pending

        def _work():
            from app.core.me3_service import get_me3_version
            ver = get_me3_version(config.get_me3_path())
            pending.put(("me3_ver", ver))

        threading.Thread(target=_work, daemon=True).start()

    def _poll_updates(self):
        try:
            while True:
                item = self._pending.get_nowait()
                if item[0] == "me3_ver":
                    ver = item[1]
                    if ver:
                        self._me3_lbl.setText(f"ME3: {ver}")
                        self._me3_lbl.setStyleSheet(
                            "font-size:10px;color:#3a3a5a;padding:0px 14px 6px 14px;"
                        )
                    else:
                        self._me3_lbl.setText("ME3: not found")
                        self._me3_lbl.setStyleSheet(
                            "font-size:10px;color:#e74c3c;padding:0px 14px 6px 14px;"
                        )
                elif item[0] == "logo_ready":
                    game_id, path = item[1], item[2]
                    if game_id in self._game_buttons:
                        self._game_buttons[game_id].load_icon(path)
                elif item[0] == "player_count":
                    game_id, count = item[1], item[2]
                    if game_id in self._game_buttons:
                        self._game_buttons[game_id].set_player_count(count)
                elif item[0] == "fetch_counts_done":
                    self._fetching_counts = False
        except _queue.Empty:
            pass

    @property
    def nexus_widget(self):
        return self._nexus
