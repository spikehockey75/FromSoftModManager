"""Embedded terminal / log output panel."""

from datetime import datetime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QPlainTextEdit, QSizePolicy)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QFont


class TerminalWidget(QWidget):
    MAX_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(28)
        header.setStyleSheet("background:#13132a;border-top:1px solid #2a2a4a;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 0, 10, 0)

        self._toggle_btn = QPushButton("▲  Output Log")
        self._toggle_btn.setObjectName("sidebar_mgmt_btn")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.clicked.connect(self._toggle)
        h_layout.addWidget(self._toggle_btn)
        h_layout.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("sidebar_mgmt_btn")
        clear_btn.setFixedHeight(22)
        clear_btn.setFixedWidth(50)
        clear_btn.clicked.connect(self._clear)
        h_layout.addWidget(clear_btn)

        layout.addWidget(header)

        # Text area
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(self.MAX_LINES)
        self._text.setFixedHeight(130)
        font = QFont("Consolas", 10)
        self._text.setFont(font)
        layout.addWidget(self._text)

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._text.setVisible(not self._collapsed)
        arrow = "▲" if not self._collapsed else "▼"
        self._toggle_btn.setText(f"{arrow}  Output Log")

    def _clear(self):
        self._text.clear()

    def log(self, message: str, level: str = "info"):
        """Append a timestamped message. level: 'info'|'success'|'warn'|'error'"""
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {
            "info": "#8888aa",
            "success": "#4ecca3",
            "warn": "#f0c040",
            "error": "#e94560",
        }
        color = colors.get(level, "#8888aa")
        html = f'<span style="color:#555577">[{ts}]</span> <span style="color:{color}">{message}</span>'
        self._text.appendHtml(html)
        self._text.moveCursor(QTextCursor.End)

    def log_success(self, msg: str): self.log(msg, "success")
    def log_error(self, msg: str): self.log(msg, "error")
    def log_warn(self, msg: str): self.log(msg, "warn")
