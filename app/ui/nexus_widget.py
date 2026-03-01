"""Nexus Mods authentication widget — shows login button or user info."""

import threading
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QDialog, QDialogButtonBox)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QObject
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor
from app.config.config_manager import ConfigManager
from app.services.nexus_service import NexusService
from app.services.nexus_oauth import NexusOAuthClient, refresh_access_token


class _RefreshWorker(QObject):
    """Background worker to refresh an OAuth token."""
    finished = Signal(dict)

    def __init__(self, refresh_token: str):
        super().__init__()
        self._refresh_token = refresh_token

    def run(self):
        result = refresh_access_token(self._refresh_token)
        self.finished.emit(result)


class NexusAuthDialog(QDialog):
    """Dialog for Nexus OAuth 2.0 PKCE authorization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Nexus Account")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(440)
        self.tokens = None  # dict with access_token, refresh_token, expires_at, user
        self._oauth_client = None
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

        # ── OAuth authorize button ──────────────────────────
        self._auth_btn = QPushButton("  Authorize with Nexus Mods")
        self._auth_btn.setObjectName("btn_accent")
        self._auth_btn.setFixedHeight(36)
        self._auth_btn.setCursor(Qt.PointingHandCursor)
        self._auth_btn.clicked.connect(self._on_auth_start)
        layout.addWidget(self._auth_btn)

        # Status label (hidden initially)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#8888aa;font-size:11px;")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setVisible(False)
        layout.addWidget(self._status_lbl)

        # ── Cancel button ──────────────────────────────────
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(cancel_btn)

    # ── OAuth PKCE flow ──────────────────────────────────────

    def _on_auth_start(self):
        """Start the OAuth 2.0 PKCE flow."""
        self._auth_btn.setText("  Waiting for authorization...")
        self._auth_btn.setEnabled(False)
        self._status_lbl.setText(
            "Your browser has been opened. Approve the request to continue."
        )
        self._status_lbl.setStyleSheet("color:#8888aa;font-size:11px;")
        self._status_lbl.setVisible(True)

        self._oauth_client = NexusOAuthClient()
        self._oauth_client.start()

        # Check for error from server startup
        _, err = self._oauth_client.poll()
        if err:
            self._status_lbl.setText(f"Failed to start: {err}")
            self._status_lbl.setStyleSheet("color:#e74c3c;font-size:11px;")
            self._auth_btn.setText("  Authorize with Nexus Mods")
            self._auth_btn.setEnabled(True)
            self._oauth_client = None
            return

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_oauth)
        self._poll_timer.start(500)

    def _poll_oauth(self):
        """Check if OAuth has returned tokens or error."""
        if not self._oauth_client:
            return

        tokens, err = self._oauth_client.poll()

        if tokens:
            self._stop_oauth()
            self.tokens = tokens
            self.accept()
        elif err:
            self._stop_oauth()
            self._status_lbl.setText(f"Authorization failed: {err}")
            self._status_lbl.setStyleSheet("color:#e74c3c;font-size:11px;")
            self._auth_btn.setText("  Authorize with Nexus Mods")
            self._auth_btn.setEnabled(True)

    def _stop_oauth(self):
        """Clean up OAuth client and timer."""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._oauth_client:
            self._oauth_client.stop()
            self._oauth_client = None

    def _on_cancel(self):
        self._stop_oauth()
        self.reject()

    def closeEvent(self, event):
        self._stop_oauth()
        super().closeEvent(event)


class NexusWidget(QWidget):
    """Top of sidebar — shows login button or logged-in user."""
    auth_changed = Signal(str)  # emits access_token on change
    _avatar_ready = Signal(bytes)  # internal: avatar image data from bg thread

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._build()
        self._refresh()
        # Try to refresh token in background to catch revoked tokens
        if self._config.get_nexus_access_token():
            QTimer.singleShot(500, self._revalidate_token)

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
        self._status_lbl = QLabel("Premium")
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
        token = self._config.get_nexus_access_token()
        user = self._config.get_nexus_user_info()
        logged_in = bool(token and user)

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
            from PySide6.QtGui import QPainterPath
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

    def _revalidate_token(self):
        """Background check that the stored token is still valid."""
        tokens = self._config.get_nexus_tokens()
        refresh_token = tokens.get("refresh_token", "")
        if not refresh_token:
            return
        # If token is not expired, just validate via API
        if not self._config.is_nexus_token_expired():
            token = tokens.get("access_token", "")
            self._thread = QThread()
            self._worker = _ValidateWorker(token, self._config)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._on_revalidated)
            self._worker.finished.connect(self._thread.quit)
            self._thread.start()
        else:
            # Token expired — try refresh
            self._thread = QThread()
            self._worker = _RefreshWorker(refresh_token)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._on_token_refreshed)
            self._worker.finished.connect(self._thread.quit)
            self._thread.start()

    def _on_token_refreshed(self, result: dict):
        if "error" in result:
            print("[NEXUS] Token refresh failed, clearing auth", flush=True)
            self._config.clear_nexus_auth()
            self._refresh()
            self.auth_changed.emit("")
        else:
            self._config.set_nexus_tokens(result)
            # Update user info from JWT
            from app.services.nexus_oauth import extract_user_info
            user_info = extract_user_info(result.get("access_token", ""))
            if user_info.get("name"):
                self._config.set_nexus_user_info(user_info)
            self._refresh()

    def _on_revalidated(self, result: dict):
        if "error" in result:
            # Token might be expired — try refresh before giving up
            tokens = self._config.get_nexus_tokens()
            refresh_token = tokens.get("refresh_token", "")
            if refresh_token:
                self._thread = QThread()
                self._worker = _RefreshWorker(refresh_token)
                self._worker.moveToThread(self._thread)
                self._thread.started.connect(self._worker.run)
                self._worker.finished.connect(self._on_token_refreshed)
                self._worker.finished.connect(self._thread.quit)
                self._thread.start()
            else:
                print("[NEXUS] Stored token is invalid, clearing auth", flush=True)
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
        dlg = NexusAuthDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.tokens:
            self._save_tokens(dlg.tokens)

    def _save_tokens(self, tokens: dict):
        """Store OAuth tokens and user info, update UI."""
        self._config.set_nexus_tokens(tokens)
        user_info = tokens.get("user", {})
        if user_info:
            self._config.set_nexus_user_info(user_info)
        self._refresh()
        self.auth_changed.emit(tokens.get("access_token", ""))

    def _on_logout(self):
        self._config.clear_nexus_auth()
        self._refresh()
        self.auth_changed.emit("")


class _ValidateWorker(QObject):
    """Background worker to validate a token via the Nexus API."""
    finished = Signal(dict)

    def __init__(self, access_token: str, config=None):
        super().__init__()
        self._token = access_token
        self._config = config

    def run(self):
        svc = NexusService(self._token, config=self._config)
        result = svc.validate_user()
        self.finished.emit(result)
