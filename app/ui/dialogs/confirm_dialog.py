"""Generic confirmation dialog."""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton)
from PySide6.QtCore import Qt


class ConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, confirm_text="Confirm",
                 cancel_text="Cancel", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(380)
        self._build(title, message, confirm_text, cancel_text)

    def _build(self, title, message, confirm_text, cancel_text):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size:14px;font-weight:700;color:#e0e0ec;")
        layout.addWidget(lbl_title)

        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color:#8888aa;font-size:12px;line-height:1.5;")
        layout.addWidget(lbl_msg)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton(cancel_text)
        btn_cancel.setObjectName("sidebar_mgmt_btn")
        btn_cancel.setFixedWidth(90)
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton(confirm_text)
        btn_confirm.setObjectName("btn_accent")
        btn_confirm.setFixedWidth(110)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)
        layout.addLayout(btn_row)
