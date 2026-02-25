"""Nexus Mods authentication widget — shows login button or user info."""

import threading
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QDialog, QLineEdit, QDialogButtonBox,
                                QVBoxLayout, QProgressBar)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QObject
from PySide6.QtGui import QPixmap, QCursor
from app.config.config_manager import ConfigManager
from app.services.nexus_service import NexusService
from app.services.nexus_sso import NexusSSOAuth
import urllib.request


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
    """Dialog to paste API key manually or open Nexus page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Nexus Account")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(440)
        self.api_key = ""
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("<b>Connect your Nexus Mods account</b>"))

        desc = QLabel(
            "Paste your personal API key from Nexus Mods.\n"
            "This enables authenticated downloads and update checks."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#8888aa;font-size:11px;")
        layout.addWidget(desc)

        open_btn = QPushButton("  Open Nexus API key page")
        open_btn.setObjectName("btn_blue")
        open_btn.clicked.connect(self._open_nexus)
        layout.addWidget(open_btn)

        lbl = QLabel("Paste your API key:")
        layout.addWidget(lbl)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("Your API key from nexusmods.com/users/myaccount")
        layout.addWidget(self._key_edit)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#4ecca3;font-size:11px;")
        layout.addWidget(self._status)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _open_nexus(self):
        import webbrowser
        webbrowser.open("https://www.nexusmods.com/users/myaccount?tab=api+access")
        self._status.setText("Opened browser — paste your key above.")

    def _on_ok(self):
        key = self._key_edit.text().strip()
        if key:
            self.api_key = key
            self.accept()


class NexusWidget(QWidget):
    """Top of sidebar — shows login button or logged-in user."""
    auth_changed = Signal(str)  # emits api_key on change

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._build()
        self._refresh()

    def _build(self):
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
        self._avatar_lbl.setStyleSheet(
            "background:#2a2a4a;border-radius:16px;border:1px solid #3a3a5a;"
        )
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

        logout_btn = QPushButton("✕")
        logout_btn.setObjectName("sidebar_mgmt_btn")
        logout_btn.setFixedSize(24, 24)
        logout_btn.setToolTip("Disconnect account")
        logout_btn.clicked.connect(self._on_logout)
        ul.addWidget(logout_btn)

        self._layout.addWidget(self._user_widget)

    def _refresh(self):
        key = self._config.get_nexus_api_key()
        user = self._config.get_nexus_user_info()
        logged_in = bool(key and user)

        self._login_widget.setVisible(not logged_in)
        self._user_widget.setVisible(logged_in)

        if logged_in:
            self._name_lbl.setText(user.get("name", "User"))
            is_premium = user.get("is_premium", False) or user.get("is_supporter", False)
            self._status_lbl.setText("Premium ✓" if is_premium else "Free")
            self._status_lbl.setStyleSheet(
                "font-size:10px;color:#4ecca3;" if is_premium else "font-size:10px;color:#8888aa;"
            )

    def _on_login(self):
        dlg = NexusApiKeyDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.api_key:
            self._validate_and_save(dlg.api_key)

    def _validate_and_save(self, api_key: str):
        self._login_btn.setText("Validating…")
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
