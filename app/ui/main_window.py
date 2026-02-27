"""
Main application window — horizontal splitter: sidebar | content, terminal at bottom.
"""

import os
import threading
import queue as _queue
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                QSplitter, QLabel, QPushButton, QFrame,
                                QStackedWidget, QProgressDialog, QDialog,
                                QApplication, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer, QSize
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence

from PySide6.QtGui import QFont as _QFont, QIcon as _QIcon, QPixmap as _QPixmap, QPainter as _QPainter, QColor as _QColor
from app.config.config_manager import ConfigManager

# Windows 11 native icon font — used for all UI icons
_MDL2 = "Segoe MDL2 Assets"


def _mdl2_icon(char: str, size: int = 16, color: str = "#c0c0d8") -> _QIcon:
    """Render a Segoe MDL2 Assets glyph to a QIcon."""
    px = _QPixmap(size, size)
    px.fill(_QColor("transparent"))
    p = _QPainter(px)
    p.setFont(_QFont(_MDL2, int(size * 0.75)))
    p.setPen(_QColor(color))
    p.drawText(px.rect(), Qt.AlignCenter, char)
    p.end()
    return _QIcon(px)
from app.core.game_scanner import scan_for_games
from app.ui.sidebar import Sidebar
from app.ui.game_page import GamePage
from app.ui.terminal_widget import TerminalWidget
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.dialogs.confirm_dialog import ConfirmDialog


class _ScanWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)

    def run(self):
        def _cb(msg):
            self.progress.emit(msg)
        result = scan_for_games(progress_callback=_cb)
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self._config = config
        self._game_pages: dict[str, GamePage] = {}
        self._games: dict = {}
        self._current_game_id: str | None = None

        self.setWindowTitle("FromSoft Mod Manager")
        self.setMinimumSize(1000, 640)
        self.resize(1200, 760)

        self._pending: _queue.SimpleQueue = _queue.SimpleQueue()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_updates)
        self._poll_timer.start(200)

        self._build()
        self._load_games()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title bar ──────────────────────────────────────────
        title_bar = QFrame()
        title_bar.setObjectName("header_bar")
        title_bar.setFixedHeight(44)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(14, 0, 14, 0)

        logo = QLabel()
        logo.setPixmap(_mdl2_icon("\uE7FC", 20, "#e0e0ec").pixmap(20, 20))
        tb_layout.addWidget(logo)

        app_name = QLabel("FromSoft Mod Manager")
        app_name.setStyleSheet("font-size:14px;font-weight:700;color:#e0e0ec;")
        tb_layout.addWidget(app_name)
        tb_layout.addStretch()

        self._scan_status_lbl = QLabel("")
        self._scan_status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        tb_layout.addWidget(self._scan_status_lbl)

        root.addWidget(title_bar)

        # ── Update banner (hidden until update detected) ────────
        self._update_banner = QFrame()
        self._update_banner.setVisible(False)
        self._update_banner.setFixedHeight(36)
        self._update_banner.setStyleSheet(
            "QFrame{background:#2d3a1e;border-bottom:1px solid #4a6a2a;}"
        )
        ub_layout = QHBoxLayout(self._update_banner)
        ub_layout.setContentsMargins(14, 0, 14, 0)
        self._update_lbl = QLabel("")
        self._update_lbl.setStyleSheet("font-size:12px;color:#b0d880;font-weight:600;")
        ub_layout.addWidget(self._update_lbl)
        ub_layout.addStretch()
        self._update_now_btn = QPushButton("Update Now")
        self._update_now_btn.setFixedHeight(24)
        self._update_now_btn.setStyleSheet(
            "QPushButton{font-size:11px;color:#fff;background:#4a6a2a;"
            "border:none;border-radius:4px;padding:2px 12px;font-weight:600;}"
            "QPushButton:hover{background:#5a8a3a;}"
        )
        self._update_now_btn.clicked.connect(self._on_update_now)
        ub_layout.addWidget(self._update_now_btn)
        dismiss_btn = QPushButton("\uE711")
        dismiss_btn.setFont(_QFont(_MDL2, 10))
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.setStyleSheet(
            "QPushButton{color:#8a8a6a;background:transparent;border:none;}"
            "QPushButton:hover{color:#b0d880;}"
        )
        dismiss_btn.setToolTip("Dismiss")
        dismiss_btn.clicked.connect(lambda: self._update_banner.setVisible(False))
        ub_layout.addWidget(dismiss_btn)
        root.addWidget(self._update_banner)

        self._update_download_url = ""

        # ── Main content area (splitter) ───────────────────────
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setChildrenCollapsible(False)

        # Sidebar
        self._sidebar = Sidebar(self._config)
        self._sidebar.game_selected.connect(self._on_game_selected)
        self._sidebar.scan_requested.connect(self._on_scan)
        self._sidebar.settings_requested.connect(self._on_settings)
        self._sidebar.launch_game.connect(self._on_launch_game)
        self._sidebar.nexus_widget.auth_changed.connect(self._on_nexus_auth_changed)
        self._splitter.addWidget(self._sidebar)

        # Content area
        self._content_stack = QStackedWidget()

        # Landing page
        self._landing = self._build_landing()
        self._content_stack.addWidget(self._landing)

        self._splitter.addWidget(self._content_stack)
        self._splitter.setSizes([220, 980])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        root.addWidget(self._splitter, stretch=1)

        # ── Terminal (hidden by default, Ctrl+` to toggle) ─────
        self._terminal = TerminalWidget()
        self._terminal.setVisible(False)
        root.addWidget(self._terminal)

        shortcut = QShortcut(QKeySequence("Ctrl+`"), self)
        shortcut.activated.connect(self._toggle_terminal)

    def _toggle_terminal(self):
        self._terminal.setVisible(not self._terminal.isVisible())

    def _build_landing(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("\uE7FC")
        icon.setFont(_QFont(_MDL2, 48))
        icon.setStyleSheet("color:#3a3a5a;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("FromSoft Mod Manager")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#e0e0ec;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Manage mods for your FromSoftware games.")
        subtitle.setStyleSheet("font-size:13px;color:#8888aa;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        scan_btn = QPushButton("Scan for Games")
        scan_btn.setIcon(_mdl2_icon("\uE721", 20, "#ffffff"))
        scan_btn.setObjectName("btn_accent")
        scan_btn.setFixedWidth(200)
        scan_btn.setFixedHeight(44)
        scan_btn.setStyleSheet(scan_btn.styleSheet() + "font-size:14px;")
        scan_btn.clicked.connect(self._on_scan)
        layout.addWidget(scan_btn, alignment=Qt.AlignCenter)

        last_scan = self._config.get_last_scan()
        if last_scan:
            last_lbl = QLabel(f"Last scan: {last_scan[:16].replace('T', ' ')}")
            last_lbl.setStyleSheet("font-size:11px;color:#555577;")
            last_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(last_lbl)

        return w

    # ------------------------------------------------------------------
    # Game management
    # ------------------------------------------------------------------
    def _load_games(self):
        games = self._config.get_games()
        if games:
            self._games = games
            self._sidebar.populate_games(games)
            self._ensure_me3_profiles()
            if games:
                first_id = next(iter(games))
                self._sidebar.select_game(first_id)

        last_scan = self._config.get_last_scan()
        if last_scan:
            self._scan_status_lbl.setText(f"Scanned: {last_scan[:10]}")
        else:
            # First launch — auto-scan for games
            QTimer.singleShot(300, self._on_scan)

    def _on_game_selected(self, game_id: str):
        game_info = self._games.get(game_id)
        if not game_info:
            return
        self._current_game_id = game_id

        if game_id not in self._game_pages:
            page = GamePage(game_id, game_info, self._config)
            page.log_message.connect(self._on_log)
            page.mod_installed.connect(self._on_mod_installed)
            page.auth_changed.connect(self._on_nexus_auth_from_install)
            self._game_pages[game_id] = page
            self._content_stack.addWidget(page)

        self._content_stack.setCurrentWidget(self._game_pages[game_id])

    def _on_mod_installed(self, game_id: str):
        # Update sidebar state only — the ModsTab already updated its own cards
        # and saved config.  Calling page.refresh() would destroy/recreate cards
        # and re-fire update checks, causing stale results and layout glitches.
        self._config.reload()
        self._games = self._config.get_games()
        self._sidebar.populate_games(self._games)

    def _ensure_me3_profiles(self):
        """Auto-detect co-op mods on disk and write ME3 profiles for all games.

        Handles three scenarios:
        1. Co-op mod not in config but exists on disk → register it
        2. Co-op mod in config but path is stale/invalid → repair to marker path
        3. Co-op mod in config with valid path → just write the ME3 profile
        """
        from app.core.me3_service import (find_me3_executable, write_me3_profile,
                                          ME3_GAME_MAP)
        from app.config.game_definitions import GAME_DEFINITIONS
        from app.ui.tabs.mods_tab import _find_native_dlls, _has_asset_content

        me3_path = find_me3_executable(self._config.get_me3_path())
        if not me3_path:
            return

        for game_id, game_info in self._games.items():
            if game_id not in ME3_GAME_MAP:
                continue
            gdef = GAME_DEFINITIONS.get(game_id, {})
            marker_rel = gdef.get("mod_marker_relative", "")
            install_path = game_info.get("install_path", "")
            marker_path = os.path.join(install_path, marker_rel) if marker_rel and install_path else ""

            coop_id = f"{game_id}-coop"
            mods = self._config.get_game_mods(game_id)
            coop_mod = next((m for m in mods if m["id"] == coop_id), None)

            if coop_mod:
                # Registered — repair stale path if needed
                if not coop_mod.get("path") or not os.path.isdir(coop_mod["path"]):
                    if marker_path and os.path.isdir(marker_path):
                        coop_mod["path"] = marker_path
                        self._config.add_or_update_game_mod(game_id, coop_mod)
                        mods = self._config.get_game_mods(game_id)
            else:
                # Not registered — auto-detect from disk
                if marker_path and os.path.isdir(marker_path):
                    mod_dict = {
                        "id": coop_id,
                        "name": gdef.get("mod_name", "Co-op Mod"),
                        "version": "",
                        "path": marker_path,
                        "nexus_domain": gdef.get("nexus_domain", ""),
                        "nexus_mod_id": gdef.get("nexus_mod_id", 0),
                        "enabled": True,
                    }
                    self._config.add_or_update_game_mod(game_id, mod_dict)
                    mods = self._config.get_game_mods(game_id)

            # Write ME3 profile from current mod state
            pkg_paths = []
            native_paths = []
            for m in mods:
                if not m.get("enabled") or not m.get("path"):
                    continue
                p = m["path"]
                if p.lower().endswith(".dll"):
                    native_paths.append(p)
                elif os.path.isdir(p):
                    dlls = _find_native_dlls(p)
                    if dlls:
                        native_paths.extend(dlls)
                    if _has_asset_content(p):
                        pkg_paths.append(p)
            write_me3_profile(game_id, pkg_paths, me3_path, native_dlls=native_paths)

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def _on_scan(self):
        if getattr(self, '_scan_in_progress', False):
            return
        self._scan_in_progress = True
        print("[SCAN] _on_scan started", flush=True)
        self._scan_status_lbl.setText("Scanning…")
        self._terminal.log("Scanning for games…")

        self._scan_thread = QThread()
        self._scan_worker = _ScanWorker()
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        # Proper cleanup: schedule deletion after thread/worker have stopped
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        print("[SCAN] starting thread", flush=True)
        self._scan_thread.start()

    def _on_scan_progress(self, msg: str):
        print(f"[SCAN] progress: {msg}", flush=True)
        self._terminal.log(msg)

    def _on_scan_done(self, games: dict):
        print(f"[SCAN] _on_scan_done, found {len(games)} games", flush=True)
        self._scan_in_progress = False
        self._config.set_games(games)
        self._games = games

        print("[SCAN] removing old pages", flush=True)
        # Remove old game pages safely — deleteLater lets Qt clean up threads
        for page in list(self._game_pages.values()):
            self._content_stack.removeWidget(page)
            page.deleteLater()
        self._game_pages.clear()

        print("[SCAN] switching to landing", flush=True)
        # Landing was never removed; just switch back to it
        self._content_stack.setCurrentWidget(self._landing)

        print("[SCAN] populating sidebar", flush=True)
        self._sidebar.populate_games(games)

        count = len(games)
        self._scan_status_lbl.setText(f"Found {count} game{'s' if count != 1 else ''}")
        self._terminal.log_success(f"Scan complete — found {count} game(s)")

        if games:
            # Restore the previously selected game, or fall back to the first
            restore_id = self._current_game_id if self._current_game_id in games else next(iter(games))
            print(f"[SCAN] selecting game: {restore_id}", flush=True)
            self._on_game_selected(restore_id)
        self._ensure_me3_profiles()
        print("[SCAN] _on_scan_done complete", flush=True)
        self._check_all_mod_updates()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _on_settings(self):
        dlg = SettingsDialog(self._config, parent=self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_nexus_auth_changed(self, api_key: str):
        """Refresh game pages when Nexus auth changes (login/logout via sidebar)."""
        for page in self._game_pages.values():
            game_info = self._games.get(page._game_id, {})
            page.refresh(game_info)
        if api_key:
            self._check_all_mod_updates()

    def _on_nexus_auth_from_install(self):
        """User authenticated via SSO during a mod install — refresh sidebar."""
        self._sidebar.nexus_widget._refresh()

    def _on_settings_saved(self):
        self._terminal.log("Settings saved", "success")
        # Refresh Nexus widget (picks up sign-out / key changes)
        self._sidebar.nexus_widget._refresh()
        # Refresh game pages to pick up ME3 changes
        for page in self._game_pages.values():
            game_info = self._games.get(page._game_id, {})
            page.refresh(game_info)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    def _on_launch_game(self, game_id: str):
        import threading
        from app.core.me3_service import (find_me3_executable, launch_game_with_me3,
                                          launch_game_direct, ME3_GAME_MAP)
        game_info = self._games.get(game_id, {})
        name = game_info.get("name", game_id)

        # Check cooppassword before launch
        if not self._check_coop_password(game_id, game_info):
            return

        use_me3 = self._config.get_use_me3()
        me3_path = find_me3_executable(self._config.get_me3_path())
        launcher_path = game_info.get("launcher_path", "")
        me3_supported = ME3_GAME_MAP.get(game_id) is not None
        pending = self._pending

        self._terminal.log(f"Launching {name}…", "info")

        def _terminal_cb(msg):
            pending.put(("log", msg, "info"))

        def _launch():
            proc = None
            method = ""
            # Use ME3 for all ME3-supported games when enabled.
            # Fall back to direct co-op launcher if ME3 fails.
            if use_me3 and me3_path and me3_supported:
                proc = launch_game_with_me3(game_id, me3_path, terminal_callback=_terminal_cb)
                if proc:
                    method = "ME3"
                else:
                    # ME3 failed — it may have started the game process already,
                    # so don't try to launch again via direct launcher.
                    pending.put(("launch_result", name, False, "ME3 attach failed — close the game and try again"))
                    return
            if not proc and launcher_path:
                proc = launch_game_direct(launcher_path, terminal_callback=_terminal_cb)
                if not method:
                    method = "direct"
            pending.put(("launch_result", name, proc is not None, method))

        threading.Thread(target=_launch, daemon=True).start()

    def _find_coop_ini(self, game_id: str, game_info: dict, gdef: dict) -> str | None:
        """Locate the co-op settings INI, checking the mod's stored path
        first (ME3 mod dir), then falling back to the game directory."""
        # Check ME3 mod directory first (where Manage dialog edits)
        coop_id = f"{game_id}-coop"
        for m in self._config.get_game_mods(game_id):
            if m["id"] == coop_id and m.get("path") and os.path.isdir(m["path"]):
                for root, _dirs, files in os.walk(m["path"]):
                    for f in files:
                        if f.endswith(".ini"):
                            return os.path.join(root, f)
                break
        # Fall back to game directory
        config_rel = gdef.get("config_relative", "")
        install_path = game_info.get("install_path", "")
        if config_rel and install_path:
            candidate = os.path.join(install_path, config_rel)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _check_coop_password(self, game_id: str, game_info: dict) -> bool:
        """Check if the co-op INI has an empty cooppassword. Prompt if so.

        Returns True to proceed with launch, False to abort.
        """
        from app.config.game_definitions import GAME_DEFINITIONS
        gdef = GAME_DEFINITIONS.get(game_id, {})
        if "cooppassword" not in gdef.get("defaults", {}):
            return True

        ini_path = self._find_coop_ini(game_id, game_info, gdef)
        if not ini_path:
            return True

        from app.core.ini_parser import read_ini_value
        password = read_ini_value(ini_path, "cooppassword")
        if password:
            return True

        # Password is empty — prompt the user
        from app.ui.dialogs.coop_password_dialog import CoopPasswordDialog
        dlg = CoopPasswordDialog(game_info.get("name", game_id), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return False

        from app.core.ini_parser import save_ini_settings
        save_ini_settings(ini_path, {"cooppassword": dlg.password})
        self._terminal.log(f"Co-op password saved for {game_info.get('name', game_id)}", "info")
        return True

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _on_log(self, message: str, level: str):
        self._terminal.log(message, level)

    # ------------------------------------------------------------------
    # Background update checks
    # ------------------------------------------------------------------
    def _poll_updates(self):
        try:
            while True:
                item = self._pending.get_nowait()
                tag = item[0]
                if tag == "log":
                    _, msg, level = item
                    self._terminal.log(msg, level)
                elif tag == "update_check":
                    _, game_id, game_name, result = item
                    self._on_update_checked(game_id, game_name, result)
                elif tag == "app_update":
                    _, result = item
                    latest = result.get("latest", "")
                    self._update_download_url = result.get("download_url", "")
                    self._update_lbl.setText(f"Update available: v{latest}")
                    self._update_banner.setVisible(True)
                    self._terminal.log(f"App update available: v{latest}", "warn")
                elif tag == "app_update_done":
                    _, result = item
                    if result.get("success"):
                        self._terminal.log("Installer launched — closing app…", "success")
                        QApplication.quit()
                    else:
                        self._terminal.log(f"Update failed: {result.get('message', 'unknown error')}", "error")
                        self._update_now_btn.setEnabled(True)
                        self._update_now_btn.setText("Update Now")
                elif tag == "launch_result":
                    _, name, success, method = item
                    if success:
                        msg = f"Launched {name}"
                        if method:
                            msg += f" ({method})"
                        self._terminal.log(msg, "success")
                    elif method and "ME3 failed" in method:
                        self._terminal.log(f"{name}: {method}", "warning")
                    else:
                        self._terminal.log(f"Failed to launch {name}", "error")
        except _queue.Empty:
            pass

    def _on_update_checked(self, game_id: str, game_name: str, result: dict):
        if "error" in result:
            return
        if result.get("has_update"):
            latest = result.get("latest_version", "?")
            self._terminal.log(f"{game_name}: update available → v{latest}", "warning")
            self._sidebar.set_update_badge(game_id, True)

    # ------------------------------------------------------------------
    # App self-update
    # ------------------------------------------------------------------
    def _on_update_now(self):
        """Download the latest installer and launch it."""
        url = self._update_download_url
        if not url:
            self._terminal.log("No download URL available", "error")
            return

        self._update_now_btn.setEnabled(False)
        self._update_now_btn.setText("Downloading…")
        self._terminal.setVisible(True)
        self._terminal.log("Downloading app update…", "info")
        pending = self._pending

        def _download():
            from app.services.update_service import download_and_run_installer

            def _progress(msg, pct):
                pending.put(("log", msg, "info"))

            result = download_and_run_installer(url, progress_callback=_progress)
            pending.put(("app_update_done", result))

        threading.Thread(target=_download, daemon=True).start()

    def _check_all_mod_updates(self):
        """Fire background update checks for all installed mods across all games."""
        api_key = self._config.get_nexus_api_key()
        if not api_key:
            return
        pending = self._pending

        for game_id, game_info in self._games.items():
            mods = self._config.get_game_mods(game_id)
            if not mods:
                continue
            gname = game_info.get("name", game_id)

            for mod in mods:
                if not mod.get("nexus_mod_id"):
                    continue

                def _work(game_id=game_id, game_name=gname, mod=dict(mod)):
                    from app.services.nexus_service import NexusService
                    from app.core.mod_updater import version_compare
                    svc = NexusService(api_key)
                    domain = mod.get("nexus_domain", "")
                    nid = mod.get("nexus_mod_id", 0)
                    if not domain or not nid:
                        return
                    # Use Nexus mod-page version as single source of truth
                    mod_info = svc.get_mod_info(domain, nid)
                    if "error" in mod_info:
                        return
                    latest = mod_info.get("version", "")
                    installed = mod.get("version") or ""
                    has_update = False
                    if installed and latest:
                        has_update = version_compare(installed, latest) < 0
                    elif latest:
                        has_update = True
                    print(f"[UPDATE CHECK] {game_name} {mod.get('name','')}: installed={installed!r} latest={latest!r} has_update={has_update}", flush=True)
                    result = {"has_update": has_update, "latest_version": latest}
                    pending.put(("update_check", game_id, game_name, result))

                threading.Thread(target=_work, daemon=True).start()
