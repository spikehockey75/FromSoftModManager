"""Dialog for adding a mod from a local zip file."""

import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QLineEdit, QFileDialog,
                                QDialogButtonBox)
from PySide6.QtCore import Qt


class AddModDialog(QDialog):
    """
    Browse for a zip file, give the mod a name, optionally paste a Nexus URL.
    On accept, `.result` contains:
      {zip_path, name, slug, nexus_domain, nexus_mod_id}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Mod from Zip")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(460)
        self.result: dict | None = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Add Mod from Zip")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#e0e0ec;")
        layout.addWidget(title)

        # Zip file row
        zip_row = QHBoxLayout()
        self._zip_edit = QLineEdit()
        self._zip_edit.setPlaceholderText("Select a .zip file…")
        self._zip_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse)
        zip_row.addWidget(QLabel("Zip file:"))
        zip_row.addWidget(self._zip_edit, stretch=1)
        zip_row.addWidget(browse_btn)
        layout.addLayout(zip_row)

        # Mod name row
        name_row = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Seamless Co-op")
        name_row.addWidget(QLabel("Mod name:"))
        name_row.addWidget(self._name_edit, stretch=1)
        layout.addLayout(name_row)

        # Nexus URL row
        nexus_row = QHBoxLayout()
        self._nexus_edit = QLineEdit()
        self._nexus_edit.setPlaceholderText("https://www.nexusmods.com/…  (optional)")
        nexus_row.addWidget(QLabel("Nexus URL:"))
        nexus_row.addWidget(self._nexus_edit, stretch=1)
        layout.addLayout(nexus_row)

        hint = QLabel("Providing a Nexus URL enables automatic update checks.")
        hint.setStyleSheet("font-size:11px;color:#8888aa;")
        layout.addWidget(hint)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btn_box.button(QDialogButtonBox.Ok).setText("Install")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _browse(self):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select mod zip", downloads, "Zip files (*.zip)"
        )
        if path:
            self._zip_edit.setText(path)
            if not self._name_edit.text().strip():
                base = os.path.splitext(os.path.basename(path))[0]
                self._name_edit.setText(base)

    def _on_accept(self):
        zip_path = self._zip_edit.text().strip()
        name = self._name_edit.text().strip()
        if not zip_path or not os.path.isfile(zip_path):
            self._zip_edit.setStyleSheet("border:1px solid #e94560;")
            return
        if not name:
            self._name_edit.setStyleSheet("border:1px solid #e94560;")
            return

        from app.core.me3_service import slugify
        slug = slugify(name)
        if not slug:
            slug = "mod"

        nexus_domain = ""
        nexus_mod_id = 0
        nexus_url = self._nexus_edit.text().strip()
        if nexus_url:
            from app.services.nexus_service import parse_nexus_url
            parsed = parse_nexus_url(nexus_url)
            if parsed:
                nexus_domain, nexus_mod_id = parsed

        self.result = {
            "zip_path": zip_path,
            "name": name,
            "slug": slug,
            "nexus_domain": nexus_domain,
            "nexus_mod_id": nexus_mod_id,
        }
        self.accept()
