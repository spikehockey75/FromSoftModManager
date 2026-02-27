"""
ME3 setup dialog — shown on startup when ME3 is not installed.
Blocks the main window until the user installs ME3 or cancels (which exits the app).
"""

import threading
import queue as _queue
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QProgressBar, QFrame)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from app.core.me3_service import download_and_install_me3
from app.config.config_manager import ConfigManager


class ME3SetupDialog(QDialog):
    """Blocking dialog requiring ME3 installation before the app can proceed."""

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._pending: _queue.SimpleQueue = _queue.SimpleQueue()

        self.setWindowTitle("Mod Engine 3 Required")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)  # force explicit choice
        self.setMinimumWidth(480)
        self.setMinimumHeight(280)
        self._build()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(100)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Icon + title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel("\uE713")
        icon_lbl.setFont(QFont("Segoe MDL2 Assets", 24))
        icon_lbl.setStyleSheet("color:#e0e0ec;")
        title_row.addWidget(icon_lbl)

        title = QLabel("Mod Engine 3 Required")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#e0e0ec;")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Description
        desc = QLabel(
            "FromSoft Mod Manager requires Mod Engine 3 (ME3) to load and manage mods.\n\n"
            "ME3 is a free, open-source mod loader for FromSoftware games. "
            "Click Install ME3 to download and install it automatically."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px;color:#a0a0c0;line-height:1.5;")
        layout.addWidget(desc)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#2a2a4a;")
        layout.addWidget(sep)

        # Status label
        self._status_lbl = QLabel("Ready to install")
        self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        layout.addWidget(self._status_lbl)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("sidebar_mgmt_btn")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._install_btn = QPushButton("  Install ME3")
        self._install_btn.setObjectName("btn_accent")
        self._install_btn.setFixedHeight(36)
        self._install_btn.setFixedWidth(160)
        self._install_btn.clicked.connect(self._on_install)
        btn_row.addWidget(self._install_btn)

        layout.addLayout(btn_row)

    def _on_install(self):
        self._install_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status_lbl.setText("Starting download…")

        pending = self._pending

        def _work():
            def _cb(msg, pct):
                pending.put(("progress", pct, msg))
            result = download_and_install_me3(progress_callback=_cb)
            pending.put(("done", result))

        threading.Thread(target=_work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                item = self._pending.get_nowait()
                tag = item[0]
                if tag == "progress":
                    _, pct, msg = item
                    self._progress.setValue(pct)
                    self._status_lbl.setText(msg)
                elif tag == "done":
                    _, result = item
                    self._on_install_done(result)
        except _queue.Empty:
            pass

    def _on_install_done(self, result: dict):
        self._poll_timer.stop()
        if result.get("success"):
            self._progress.setValue(100)
            self._status_lbl.setText("ME3 installed successfully!")
            self._status_lbl.setStyleSheet("font-size:11px;color:#4ecca3;font-weight:600;")
            if result.get("path"):
                self._config.set_me3_path(result["path"])
            self._config.set_use_me3(True)
            # Brief pause so user sees success, then accept
            QTimer.singleShot(800, self.accept)
        else:
            self._progress.setVisible(False)
            self._status_lbl.setText(f"Installation failed: {result.get('message', 'Unknown error')}")
            self._status_lbl.setStyleSheet("font-size:11px;color:#e74c3c;")
            self._install_btn.setEnabled(True)
            self._cancel_btn.setEnabled(True)
            self._install_btn.setText("  Retry")
