"""Dialog for editing a mod's INI settings."""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame, QComboBox,
                                QSpinBox, QLineEdit, QDialogButtonBox, QWidget,
                                QMessageBox)
from PySide6.QtCore import Qt, Signal
from app.core.ini_parser import parse_ini_file, save_ini_settings


class ModSettingsDialog(QDialog):
    uninstall_requested = Signal()  # emitted when user confirms uninstall

    def __init__(self, ini_path: str, defaults: dict, mod_name: str, parent=None):
        super().__init__(parent)
        self._ini_path = ini_path
        self._defaults = defaults
        self._mod_name = mod_name
        self._widgets: dict = {}
        self._original: dict = {}
        self._rows: dict = {}     # key -> QFrame (for highlight updates)
        self._sections: list = []
        self.setWindowTitle(f"{mod_name} — Settings")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(740, 580)
        self.resize(780, 640)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"{self._mod_name} Settings")
        title.setStyleSheet("font-size:14px;font-weight:700;color:#e0e0ec;")
        layout.addWidget(title)

        import os
        if not os.path.isfile(self._ini_path):
            placeholder = QLabel("No settings file found for this mod.")
            placeholder.setStyleSheet("color:#8888aa;font-size:13px;padding:20px;")
            placeholder.setAlignment(Qt.AlignCenter)
            layout.addWidget(placeholder)
            btn_box = QDialogButtonBox(QDialogButtonBox.Close)
            btn_box.rejected.connect(self.reject)
            layout.addWidget(btn_box)
            return

        # Parse INI
        try:
            self._sections = parse_ini_file(self._ini_path, self._defaults)
        except Exception as e:
            err = QLabel(f"Failed to parse settings: {e}")
            err.setStyleSheet("color:#e74c3c;font-size:12px;padding:20px;")
            layout.addWidget(err)
            btn_box = QDialogButtonBox(QDialogButtonBox.Close)
            btn_box.rejected.connect(self.reject)
            layout.addWidget(btn_box)
            return

        # Scrollable settings area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 4, 0)
        cl.setSpacing(10)

        for section in self._sections:
            sec_frame = QFrame()
            sec_frame.setObjectName("card")
            sf_layout = QVBoxLayout(sec_frame)
            sf_layout.setContentsMargins(0, 0, 0, 0)
            sf_layout.setSpacing(0)

            hdr = QLabel(section["name"])
            hdr.setObjectName("section_header")
            hdr.setContentsMargins(10, 6, 10, 6)
            sf_layout.addWidget(hdr)

            for setting in section.get("settings", []):
                sf_layout.addWidget(self._build_row(setting))

            cl.addWidget(sec_frame)

        cl.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Button row: [Uninstall]  ---stretch---  [Cancel] [Save]
        btn_row = QHBoxLayout()

        uninstall_btn = QPushButton("🗑  Uninstall Mod")
        uninstall_btn.setStyleSheet(
            "QPushButton{color:#e74c3c;border:1px solid #e74c3c;border-radius:4px;"
            "padding:4px 10px;background:transparent;}"
            "QPushButton:hover{background:#e74c3c;color:#fff;}"
        )
        uninstall_btn.clicked.connect(self._on_uninstall)
        btn_row.addWidget(uninstall_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("btn_success")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _build_row(self, setting: dict) -> QFrame:
        key = setting["key"]
        value = setting["value"]
        field_type = setting.get("type", "text")
        options = setting.get("options", [])
        description = setting.get("description", "")

        self._original[key] = value

        _base_style = (
            "QFrame#settings_row{background:transparent;"
            "border-left:3px solid transparent;border-radius:2px;}"
        )
        _changed_style = (
            "QFrame#settings_row{background:#201c0e;"
            "border-left:3px solid #f39c12;border-radius:2px;}"
        )

        row = QFrame()
        row.setObjectName("settings_row")
        row.setStyleSheet(_base_style)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 8, 10, 8)
        rl.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(QLabel(key))
        if description:
            dl = QLabel(description)
            dl.setStyleSheet("font-size:11px;color:#8888aa;")
            dl.setWordWrap(True)
            info.addWidget(dl)
        rl.addLayout(info, stretch=1)

        if field_type == "select" and options:
            widget = QComboBox()
            widget.setFixedWidth(200)
            for opt in options:
                widget.addItem(opt["label"], opt["value"])
            idx = next((i for i, o in enumerate(options) if o["value"] == value), 0)
            widget.setCurrentIndex(idx)
        elif field_type == "number":
            widget = QSpinBox()
            widget.setFixedWidth(120)
            widget.setMinimum(setting.get("min", -9999))
            widget.setMaximum(setting.get("max", 99999))
            try:
                widget.setValue(int(value))
            except ValueError:
                widget.setValue(0)
        else:
            widget = QLineEdit(value)
            widget.setFixedWidth(200)

        self._widgets[key] = widget
        self._rows[key] = row
        rl.addWidget(widget, alignment=Qt.AlignRight | Qt.AlignVCenter)

        # Highlight row when value differs from original
        def _on_change(_=None, _key=key, _row=row, _base=_base_style, _changed=_changed_style):
            current = self._get_value(_key)
            if current != self._original.get(_key, ""):
                _row.setStyleSheet(_changed)
            else:
                _row.setStyleSheet(_base)

        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(_on_change)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(_on_change)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(_on_change)

        return row

    def _get_value(self, key: str) -> str:
        w = self._widgets.get(key)
        if isinstance(w, QComboBox):
            return w.currentData() or ""
        elif isinstance(w, QSpinBox):
            return str(w.value())
        elif isinstance(w, QLineEdit):
            return w.text()
        return ""

    def _on_save(self):
        changes = {
            key: self._get_value(key)
            for key in self._widgets
            if self._get_value(key) != self._original.get(key, "")
        }
        if not changes:
            self.accept()
            return

        # Build a readable before → after summary
        lines = ["The following settings will be changed:\n"]
        max_key_len = max(len(k) for k in changes)
        for key, new_val in changes.items():
            old_val = self._original.get(key, "")
            lines.append(f"  {key.ljust(max_key_len)}  :  {old_val!r}  →  {new_val!r}")
        lines.append("\nSave these changes?")

        reply = QMessageBox.question(
            self,
            "Confirm Changes",
            "\n".join(lines),
            QMessageBox.Save | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if reply != QMessageBox.Save:
            return

        try:
            save_ini_settings(self._ini_path, changes)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _on_uninstall(self):
        reply = QMessageBox.question(
            self,
            "Uninstall Mod",
            f"Remove '{self._mod_name}' and delete all its files?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.uninstall_requested.emit()
            self.accept()
