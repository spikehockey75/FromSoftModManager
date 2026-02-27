"""Nexus Mods authentication widget — shows login button or user info."""

import threading
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QDialog, QLineEdit, QDialogButtonBox,
                                QFrame)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QObject
from PySide6.QtGui import QPixmap, QCursor, QFont, QIcon, QPainter, QColor
from app.config.config_manager import ConfigManager
from app.services.nexus_service import NexusService
from app.services.nexus_sso import NexusSSOClient


class _ValidateWorker(QObject):
    finished = Signal(dict)

    def __init__(self, api_key: str):
        super().__init__()
        self._key = api_key

    def run(self):
        svc = NexusService(self._key)
        result = svc.validate_user()
        self.finished.emit(result)


class NexusApiKeyDialog(QDialog):
    """Dialog for Nexus SSO authorization with manual API key fallback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Nexus Account")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(440)
        self.api_key = ""
        self._sso_client = None
        self._poll_timer = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("<b>Connect your Nexus Mods account</b>"))

        desc = QLabel(
            "Authorize with Nexus Mods to enable mod downloads\n"
            "and automatic update checking."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#8888aa;font-size:11px;")
        layout.addWidget(desc)

        # ── SSO authorize button ──────────────────────────
        self._sso_btn = QPushButton("  Authorize with Nexus Mods")
        self._sso_btn.setObjectName("btn_accent")
        self._sso_btn.setFixedHeight(36)
        self._sso_btn.setCursor(Qt.PointingHandCursor)
        self._sso_btn.clicked.connect(self._on_sso_start)
        layout.addWidget(self._sso_btn)

        # SSO status label (hidden initially)
        self._sso_status = QLabel("")
        self._sso_status.setStyleSheet("color:#8888aa;font-size:11px;")
        self._sso_status.setWordWrap(True)
        self._sso_status.setVisible(False)
        layout.addWidget(self._sso_status)

        # ── Separator ────────────────────────────────────
        sep_row = QHBoxLayout()
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color:#2a2a4a;")
        sep_lbl = QLabel("or")
        sep_lbl.setStyleSheet("color:#555577;font-size:10px;padding:0 8px;")
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color:#2a2a4a;")
        sep_row.addWidget(line1)
        sep_row.addWidget(sep_lbl)
        sep_row.addWidget(line2)
        layout.addLayout(sep_row)

        # ── Manual API key fallback (collapsed) ──────────
        self._manual_toggle = QPushButton("Paste API key manually")
        self._manual_toggle.setFlat(True)
        self._manual_toggle.setCursor(Qt.PointingHandCursor)
        self._manual_toggle.setStyleSheet(
            "QPushButton{color:#8888aa;font-size:11px;text-align:left;"
            "padding:0;border:none;background:transparent;}"
            "QPushButton:hover{color:#e0e0ec;}"
        )
        self._manual_toggle.clicked.connect(self._toggle_manual)
        layout.addWidget(self._manual_toggle)

        self._manual_widget = QWidget()
        ml = QVBoxLayout(self._manual_widget)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(8)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("Paste your API key from nexusmods.com/users/myaccount")
        ml.addWidget(self._key_edit)

        open_btn = QPushButton("Open Nexus API key page")
        open_btn.setFlat(True)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(
            "QPushButton{color:#7b8cde;font-size:10px;text-align:left;"
            "padding:0;border:none;background:transparent;}"
            "QPushButton:hover{color:#e0e0ec;text-decoration:underline;}"
        )
        open_btn.clicked.connect(self._open_nexus)
        ml.addWidget(open_btn)

        self._manual_widget.setVisible(False)
        layout.addWidget(self._manual_widget)

        # ── Buttons ──────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self._on_cancel)
        layout.addWidget(btns)

    # ── SSO flow ──────────────────────────────────────────

    def _on_sso_start(self):
        """Start the WebSocket SSO flow."""
        self._sso_btn.setText("  Waiting for authorization...")
        self._sso_btn.setEnabled(False)
        self._sso_status.setText("Approve the request in your browser to continue.")
        self._sso_status.setStyleSheet("color:#8888aa;font-size:11px;")
        self._sso_status.setVisible(True)

        self._sso_client = NexusSSOClient()
        self._sso_client.start()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_sso)
        self._poll_timer.start(500)

    def _poll_sso(self):
        """Check if SSO has returned a key or error."""
        if not self._sso_client:
            return

        key, err = self._sso_client.poll()

        if key:
            self._stop_sso()
            self.api_key = key
            self.accept()
        elif err:
            self._stop_sso()
            self._sso_status.setText(f"Authorization failed: {err}")
            self._sso_status.setStyleSheet("color:#e74c3c;font-size:11px;")
            self._sso_btn.setText("  Authorize with Nexus Mods")
            self._sso_btn.setEnabled(True)

    def _stop_sso(self):
        """Clean up SSO client and timer."""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._sso_client:
            self._sso_client.stop()
            self._sso_client = None

    # ── Manual fallback ──────────────────────────────────

    def _toggle_manual(self):
        visible = not self._manual_widget.isVisible()
        self._manual_widget.setVisible(visible)
        self._manual_toggle.setText(
            "Hide manual entry" if visible else "Paste API key manually"
        )

    def _open_nexus(self):
        import webbrowser
        webbrowser.open("https://www.nexusmods.com/users/myaccount?tab=api+access")

    def _on_ok(self):
        key = self._key_edit.text().strip()
        if key:
            self._stop_sso()
            self.api_key = key
            self.accept()

    def _on_cancel(self):
        self._stop_sso()
        self.reject()

    def closeEvent(self, event):
        self._stop_sso()
        super().closeEvent(event)


class NexusWidget(QWidget):
    """Top of sidebar — shows login button or logged-in user."""
    auth_changed = Signal(str)  # emits api_key on change
    _avatar_ready = Signal(bytes)  # internal: avatar image data from bg thread

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._build()
        self._refresh()
        # Re-validate cached key in background to catch expired/revoked keys
        if self._config.get_nexus_api_key():
            QTimer.singleShot(500, self._revalidate_key)

    def _build(self):
        self._avatar_ready.connect(self._on_avatar_ready)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(6)

        # Not logged in state
        self._login_widget = QWidget()
        ll = QVBoxLayout(self._login_widget)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)

        lbl = QLabel("Nexus Mods")
        lbl.setStyleSheet("font-size:11px;font-weight:700;color:#8888aa;letter-spacing:0.06em;")
        ll.addWidget(lbl)

        self._login_btn = QPushButton("Connect Account")
        self._login_btn.setObjectName("btn_accent")
        self._login_btn.setFixedHeight(30)
        self._login_btn.clicked.connect(self._on_login)
        ll.addWidget(self._login_btn)

        self._layout.addWidget(self._login_widget)

        # Logged in state
        self._user_widget = QWidget()
        ul = QHBoxLayout(self._user_widget)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.setSpacing(8)

        self._avatar_lbl = QLabel()
        self._avatar_lbl.setFixedSize(32, 32)
        self._avatar_lbl.setAlignment(Qt.AlignCenter)
        self._avatar_lbl.setStyleSheet(
            "background:#2a2a4a;border-radius:16px;border:1px solid #3a3a5a;"
        )
        # Default person icon
        self._set_default_avatar()
        ul.addWidget(self._avatar_lbl)

        user_info = QVBoxLayout()
        user_info.setSpacing(1)
        self._name_lbl = QLabel("User")
        self._name_lbl.setStyleSheet("font-size:12px;font-weight:700;color:#e0e0ec;")
        self._status_lbl = QLabel("Premium" )
        self._status_lbl.setStyleSheet("font-size:10px;color:#4ecca3;")
        user_info.addWidget(self._name_lbl)
        user_info.addWidget(self._status_lbl)
        ul.addLayout(user_info)
        ul.addStretch()

        self._layout.addWidget(self._user_widget)

    def _set_default_avatar(self):
        """Render a person icon as the default avatar."""
        px = QPixmap(32, 32)
        px.fill(QColor("transparent"))
        p = QPainter(px)
        p.setFont(QFont("Segoe MDL2 Assets", 16))
        p.setPen(QColor("#8888aa"))
        p.drawText(px.rect(), Qt.AlignCenter, "\uE77B")  # Contact icon
        p.end()
        self._avatar_lbl.setPixmap(px)

    def _refresh(self):
        key = self._config.get_nexus_api_key()
        user = self._config.get_nexus_user_info()
        logged_in = bool(key and user)

        self._login_widget.setVisible(not logged_in)
        self._user_widget.setVisible(logged_in)

        if logged_in:
            self._name_lbl.setText(user.get("name", "User"))
            is_premium = user.get("is_premium", False) or user.get("is_supporter", False)
            self._status_lbl.setText("Premium" if is_premium else "Free")
            self._status_lbl.setStyleSheet(
                "font-size:10px;color:#4ecca3;" if is_premium else "font-size:10px;color:#8888aa;"
            )
            # Fetch profile photo in background
            profile_url = user.get("profile_url", "")
            if profile_url:
                self._fetch_avatar(profile_url)
        else:
            self._set_default_avatar()

    def _fetch_avatar(self, url: str):
        """Download the Nexus profile image in the background."""
        import urllib.request

        def _work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "FromSoftModManager/2.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    self._avatar_ready.emit(resp.read())
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _on_avatar_ready(self, data: bytes):
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            scaled = px.scaled(32, 32, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            # Crop to center 32x32 if needed
            if scaled.width() > 32 or scaled.height() > 32:
                x = (scaled.width() - 32) // 2
                y = (scaled.height() - 32) // 2
                scaled = scaled.copy(x, y, 32, 32)
            # Apply circular mask
            from PySide6.QtGui import QPainterPath, QBrush
            circle = QPixmap(32, 32)
            circle.fill(QColor("transparent"))
            p = QPainter(circle)
            p.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0, 0, 32, 32)
            p.setClipPath(path)
            p.drawPixmap(0, 0, scaled)
            p.end()
            self._avatar_lbl.setPixmap(circle)

    def _revalidate_key(self):
        """Background check that the stored API key is still valid."""
        key = self._config.get_nexus_api_key()
        if not key:
            return
        self._thread = QThread()
        self._worker = _ValidateWorker(key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_revalidated)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_revalidated(self, result: dict):
        if "error" in result:
            print(f"[NEXUS] Stored API key is invalid, clearing auth", flush=True)
            self._config.clear_nexus_auth()
            self._refresh()
            self.auth_changed.emit("")
        else:
            # Update cached user info in case it changed
            self._config.set_nexus_user_info({
                "name": result.get("name", ""),
                "is_premium": result.get("is_premium", False),
                "is_supporter": result.get("is_supporter", False),
                "profile_url": result.get("profile_url", ""),
            })
            self._refresh()

    def _on_login(self):
        dlg = NexusApiKeyDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.api_key:
            self._validate_and_save(dlg.api_key)

    def _validate_and_save(self, api_key: str):
        self._login_btn.setText("Validating...")
        self._login_btn.setEnabled(False)

        self._thread = QThread()
        self._worker = _ValidateWorker(api_key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_validated)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()
        self._pending_key = api_key

    def _on_validated(self, result: dict):
        self._login_btn.setText("Connect Account")
        self._login_btn.setEnabled(True)

        if "error" in result:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Nexus Auth", f"Failed to validate key:\n{result['error']}")
            return

        self._config.set_nexus_api_key(self._pending_key)
        self._config.set_nexus_user_info({
            "name": result.get("name", ""),
            "is_premium": result.get("is_premium", False),
            "is_supporter": result.get("is_supporter", False),
            "profile_url": result.get("profile_url", ""),
        })
        self._refresh()
        self.auth_changed.emit(self._pending_key)

    def _on_logout(self):
        self._config.clear_nexus_auth()
        self._refresh()
        self.auth_changed.emit("")
