"""Dialog for adding a mod — paste a Nexus URL or browse for a zip.

Shows a progress bar during download and install, then closes on success.
"""

import os
import threading
import webbrowser
import queue as _queue
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QLineEdit, QFileDialog,
                                QProgressBar, QWidget)
from PySide6.QtCore import Qt, QTimer


class AddModDialog(QDialog):
    """
    Prompt for a Nexus Mods URL (primary) or a local zip (fallback).
    Handles download + install internally, showing progress.
    On success, `.result` contains the installed mod dict.
    """

    def __init__(self, game_id: str, game_info: dict, config, gdef: dict,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Mod")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(480)
        self.result: dict | None = None
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._gdef = gdef
        self._queue = _queue.SimpleQueue()
        self._poll_timer = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Add Mod")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#e0e0ec;")
        layout.addWidget(title)

        desc = QLabel("Paste a Nexus Mods URL to download and install automatically.")
        desc.setStyleSheet("font-size:11px;color:#8888aa;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Nexus URL input
        self._nexus_edit = QLineEdit()
        self._nexus_edit.setPlaceholderText("https://www.nexusmods.com/eldenring/mods/510")
        layout.addWidget(self._nexus_edit)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("font-size:11px;color:#e74c3c;")
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        # Zip fallback (collapsed by default)
        self._zip_toggle = QPushButton("Or install from a zip file...")
        self._zip_toggle.setFlat(True)
        self._zip_toggle.setCursor(Qt.PointingHandCursor)
        self._zip_toggle.setStyleSheet(
            "QPushButton{color:#8888aa;font-size:11px;text-align:left;"
            "padding:0;border:none;background:transparent;}"
            "QPushButton:hover{color:#e0e0ec;}"
        )
        self._zip_toggle.clicked.connect(self._toggle_zip)
        layout.addWidget(self._zip_toggle)

        self._zip_panel = QWidget()
        zl = QVBoxLayout(self._zip_panel)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.setSpacing(6)

        zip_row = QHBoxLayout()
        self._zip_edit = QLineEdit()
        self._zip_edit.setPlaceholderText("Select a .zip / .7z / .rar file...")
        self._zip_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_zip)
        zip_row.addWidget(self._zip_edit, stretch=1)
        zip_row.addWidget(browse_btn)
        zl.addLayout(zip_row)

        self._zip_name_edit = QLineEdit()
        self._zip_name_edit.setPlaceholderText("Mod name (e.g. Seamless Co-op)")
        zl.addWidget(self._zip_name_edit)

        self._zip_panel.setVisible(False)
        layout.addWidget(self._zip_panel)

        # Progress section (hidden until install starts)
        self._progress_panel = QWidget()
        pl = QVBoxLayout(self._progress_panel)
        pl.setContentsMargins(0, 8, 0, 0)
        pl.setSpacing(6)

        self._mod_name_lbl = QLabel("")
        self._mod_name_lbl.setStyleSheet("font-size:12px;font-weight:600;color:#e0e0ec;")
        pl.addWidget(self._mod_name_lbl)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(18)
        pl.addWidget(self._progress_bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        self._status_lbl.setWordWrap(True)
        pl.addWidget(self._status_lbl)

        self._progress_panel.setVisible(False)
        layout.addWidget(self._progress_panel)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("sidebar_mgmt_btn")
        self._cancel_btn.setFixedWidth(90)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._install_btn = QPushButton("Install")
        self._install_btn.setObjectName("btn_accent")
        self._install_btn.setFixedWidth(110)
        self._install_btn.clicked.connect(self._on_install)
        btn_row.addWidget(self._install_btn)

        layout.addLayout(btn_row)

    # ── UI toggles ──────────────────────────────────────────

    def _toggle_zip(self):
        visible = not self._zip_panel.isVisible()
        self._zip_panel.setVisible(visible)
        self._zip_toggle.setText(
            "Hide zip install" if visible else "Or install from a zip file..."
        )

    def _browse_zip(self):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select mod archive", downloads,
            "Archives (*.zip *.7z *.rar);;All files (*)"
        )
        if path:
            self._zip_edit.setText(path)
            if not self._zip_name_edit.text().strip():
                base = os.path.splitext(os.path.basename(path))[0]
                self._zip_name_edit.setText(base)

    # ── Install trigger ─────────────────────────────────────

    def _on_install(self):
        self._error_lbl.setVisible(False)

        # If zip panel is visible and has a file, use zip flow
        zip_path = self._zip_edit.text().strip()
        if self._zip_panel.isVisible() and zip_path and os.path.isfile(zip_path):
            name = self._zip_name_edit.text().strip()
            if not name:
                self._zip_name_edit.setStyleSheet("border:1px solid #e94560;")
                return
            self._start_zip_install(zip_path, name)
            return

        # Primary: Nexus URL
        nexus_url = self._nexus_edit.text().strip()
        if not nexus_url:
            self._error_lbl.setText("Paste a Nexus Mods URL or select a zip file.")
            self._error_lbl.setVisible(True)
            return

        from app.services.nexus_service import parse_nexus_url
        parsed = parse_nexus_url(nexus_url)
        if not parsed:
            self._error_lbl.setText(
                "Invalid URL. Expected format: https://www.nexusmods.com/{game}/mods/{id}"
            )
            self._error_lbl.setVisible(True)
            return

        api_key = self._config.get_nexus_api_key()
        if not api_key:
            self._error_lbl.setText("Connect your Nexus account first to download mods.")
            self._error_lbl.setVisible(True)
            return

        nexus_domain, nexus_mod_id = parsed
        self._start_nexus_install(api_key, nexus_domain, nexus_mod_id)

    # ── Shared: lock UI + start poll timer ──────────────────

    def _enter_installing(self, mod_name: str):
        """Lock inputs, show progress panel, start polling."""
        self._nexus_edit.setEnabled(False)
        self._install_btn.setEnabled(False)
        self._zip_toggle.setEnabled(False)
        self._zip_panel.setEnabled(False)

        self._mod_name_lbl.setText(mod_name)
        self._progress_bar.setValue(0)
        self._status_lbl.setText("Starting...")
        self._progress_panel.setVisible(True)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(100)

    def _poll(self):
        """Drain the thread-safe queue and update UI."""
        try:
            while True:
                msg = self._queue.get_nowait()
                tag = msg[0]
                if tag == "progress":
                    _, pct, text = msg
                    self._progress_bar.setValue(pct)
                    self._status_lbl.setText(text)
                elif tag == "mod_name":
                    _, name = msg
                    self._mod_name_lbl.setText(name)
                elif tag == "done":
                    _, result_dict = msg
                    self._on_done(result_dict)
                elif tag == "premium_fallback":
                    _, mod_name, nexus_url = msg
                    self._on_premium_fallback(mod_name, nexus_url)
                elif tag == "error":
                    _, error_msg = msg
                    self._on_error(error_msg)
        except _queue.Empty:
            pass

    def _on_done(self, result_dict: dict):
        """Install succeeded — store result and close."""
        if self._poll_timer:
            self._poll_timer.stop()
        self.result = result_dict
        self.accept()

    def _on_error(self, error_msg: str):
        """Install failed — show error, re-enable inputs."""
        if self._poll_timer:
            self._poll_timer.stop()
        self._progress_panel.setVisible(False)
        self._error_lbl.setText(error_msg)
        self._error_lbl.setVisible(True)
        self._nexus_edit.setEnabled(True)
        self._install_btn.setEnabled(True)
        self._zip_toggle.setEnabled(True)
        self._zip_panel.setEnabled(True)

    def _on_premium_fallback(self, mod_name: str, nexus_url: str):
        """Premium required — open browser to Nexus and show zip fallback."""
        if self._poll_timer:
            self._poll_timer.stop()
        self._progress_panel.setVisible(False)
        webbrowser.open(nexus_url)
        self._error_lbl.setText(
            "Free Nexus account — direct downloads require Premium.\n"
            "The mod page has been opened in your browser.\n\n"
            "Steps:\n"
            "  1. Click the FILES tab on the Nexus page\n"
            "  2. Click \"Manual Download\" on the file you want\n"
            "  3. Wait for the download to finish\n"
            "  4. Use the \"Install from ZIP\" section below to\n"
            "     browse to the downloaded .zip / .7z / .rar file\n"
            "     (usually in your Downloads folder)"
        )
        self._error_lbl.setStyleSheet("font-size:11px;color:#ff9800;")
        self._error_lbl.setVisible(True)
        self._nexus_edit.setEnabled(True)
        self._install_btn.setEnabled(True)
        self._zip_toggle.setEnabled(True)
        self._zip_panel.setEnabled(True)
        # Auto-expand zip panel and pre-fill mod name
        if not self._zip_panel.isVisible():
            self._toggle_zip()
        if not self._zip_name_edit.text().strip():
            self._zip_name_edit.setText(mod_name)

    # ── Nexus install flow ──────────────────────────────────

    def _start_nexus_install(self, api_key: str, domain: str, nexus_mod_id: int):
        from app.core.me3_service import slugify, ME3_GAME_MAP
        slug = slugify(f"{domain}-{nexus_mod_id}")
        self._enter_installing(f"Fetching mod info...")

        game_id = self._game_id
        game_info = self._game_info
        config = self._config
        gdef = self._gdef
        q = self._queue
        is_me3 = game_id in ME3_GAME_MAP

        def _work():
            from app.services.nexus_service import NexusService
            from app.core.mod_installer import install_mod_from_zip

            svc = NexusService(api_key)

            # 1. Fetch mod info for the name
            q.put(("progress", 2, "Fetching mod info from Nexus..."))
            mod_info = svc.get_mod_info(domain, nexus_mod_id)
            if "error" in mod_info:
                q.put(("error", mod_info["error"]))
                return
            mod_name = mod_info.get("name", f"{domain}-{nexus_mod_id}")
            q.put(("mod_name", mod_name))

            # 2. Download
            fake_gdef = dict(gdef)
            fake_gdef["nexus_domain"] = domain
            fake_gdef["nexus_mod_id"] = nexus_mod_id

            temp_dir = os.path.join(config.get_mods_dir(), "_tmp")

            def _cb(pct, msg):
                q.put(("progress", pct, msg))

            dl = svc.download_latest_mod(game_id, fake_gdef, temp_dir,
                                         progress_callback=_cb)
            if not dl.get("success"):
                if dl.get("requires_premium"):
                    nexus_url = f"https://www.nexusmods.com/{domain}/mods/{nexus_mod_id}?tab=files"
                    q.put(("premium_fallback", mod_name, nexus_url))
                else:
                    q.put(("error", dl.get("error", "Download failed")))
                return

            # 3. Extract / install
            q.put(("progress", 96, "Installing..."))
            zip_path = dl["zip_path"]
            mod_id = slug

            me3_mod_dir = os.path.join(config.get_game_mod_dir(game_id), mod_id)
            if is_me3:
                os.makedirs(me3_mod_dir, exist_ok=True)
            mod_path = me3_mod_dir if is_me3 else os.path.join(
                game_info.get("install_path", ""),
                gdef.get("mod_marker_relative", ""))

            result = install_mod_from_zip(
                zip_path,
                game_info.get("install_path", ""),
                gdef,
                target_dir=me3_mod_dir if is_me3 else None,
            )
            if not result.get("success"):
                q.put(("error", result.get("message", "Install failed")))
                return

            version_hint = dl.get("api_version") or dl.get("version", "")
            version = version_hint or result.get("version") or ""

            mod_dict = {
                "id": mod_id,
                "name": mod_name,
                "version": version,
                "path": mod_path,
                "nexus_domain": domain,
                "nexus_mod_id": nexus_mod_id,
                "enabled": True,
            }
            q.put(("done", mod_dict))

        threading.Thread(target=_work, daemon=True).start()

    # ── Zip install flow ────────────────────────────────────

    def _start_zip_install(self, zip_path: str, name: str):
        from app.core.me3_service import slugify, ME3_GAME_MAP

        slug = slugify(name) or "mod"
        self._enter_installing(name)

        game_id = self._game_id
        game_info = self._game_info
        config = self._config
        gdef = self._gdef
        q = self._queue
        is_me3 = game_id in ME3_GAME_MAP

        def _work():
            from app.core.mod_installer import install_mod_from_zip

            q.put(("progress", 50, f"Extracting {os.path.basename(zip_path)}..."))

            me3_mod_dir = os.path.join(config.get_game_mod_dir(game_id), slug)
            if is_me3:
                os.makedirs(me3_mod_dir, exist_ok=True)
            mod_path = me3_mod_dir if is_me3 else os.path.join(
                game_info.get("install_path", ""),
                gdef.get("mod_marker_relative", ""))

            result = install_mod_from_zip(
                zip_path,
                game_info.get("install_path", ""),
                gdef,
                target_dir=me3_mod_dir if is_me3 else None,
            )
            if not result.get("success"):
                q.put(("error", result.get("message", "Install failed")))
                return

            version = result.get("version") or ""
            mod_dict = {
                "id": slug,
                "name": name,
                "version": version,
                "path": mod_path,
                "nexus_domain": "",
                "nexus_mod_id": 0,
                "enabled": True,
            }
            q.put(("done", mod_dict))

        threading.Thread(target=_work, daemon=True).start()
