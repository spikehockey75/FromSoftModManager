"""
Settings tab — INI editor with smart type-inference.
"""

import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame, QComboBox,
                                QSpinBox, QLineEdit, QSizePolicy, QDialog,
                                QTableWidget, QTableWidgetItem, QHeaderView,
                                QTextEdit)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from app.config.config_manager import ConfigManager
from app.config.game_definitions import GAME_DEFINITIONS
from app.core.ini_parser import parse_ini_file, save_ini_settings
from app.core.me3_service import ME3_GAME_MAP, get_me3_profile_path, find_me3_executable


class SettingsTab(QWidget):
    log_message = Signal(str, str)

    def __init__(self, game_id: str, game_info: dict, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._gdef = GAME_DEFINITIONS.get(game_id, {})
        self._widgets = {}   # key -> widget
        self._original = {}  # key -> original value
        self._dirty = set()
        self._sections = []
        self._active_ini: str | None = None
        self._build()

    def _find_configurable_mods(self) -> list[dict]:
        """Return list of {mod, ini_path} for mods that have at least one .ini."""
        result = []
        for mod in self._config.get_game_mods(self._game_id):
            path = mod.get("path", "")
            if not path or not os.path.isdir(path):
                continue
            for root, _dirs, files in os.walk(path):
                for f in files:
                    if f.endswith(".ini"):
                        result.append({"mod": mod, "ini_path": os.path.join(root, f)})
                        break
                else:
                    continue
                break
        return result

    def _build_toml_viewer(self) -> QFrame:
        """Build a read-only viewer for the ME3 profile TOML."""
        frame = QFrame()
        frame.setObjectName("card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        # Header row with title + refresh button
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(10, 6, 10, 6)
        hdr = QLabel("ME3 Profile (read-only)")
        hdr.setObjectName("section_header")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedHeight(24)
        refresh_btn.setStyleSheet(
            "QPushButton{font-size:11px;padding:2px 8px;border:1px solid #2a2a4a;"
            "border-radius:3px;background:transparent;color:#8888aa;}"
            "QPushButton:hover{background:#1e1e3a;color:#e0e0ec;}"
        )
        refresh_btn.clicked.connect(self._refresh_toml)
        hdr_row.addWidget(refresh_btn)
        fl.addLayout(hdr_row)

        self._toml_edit = QTextEdit()
        self._toml_edit.setReadOnly(True)
        self._toml_edit.setFont(QFont("Consolas", 10))
        self._toml_edit.setStyleSheet(
            "QTextEdit{background:#0e0e1a;color:#c0c0d8;border:none;"
            "padding:8px;font-size:12px;}"
        )
        self._toml_edit.setFixedHeight(160)
        fl.addWidget(self._toml_edit)

        self._refresh_toml()
        return frame

    def _refresh_toml(self):
        """Load the ME3 TOML profile content into the viewer."""
        if not self._toml_edit:
            return
        me3_path = find_me3_executable(self._config.get_me3_path())
        if not me3_path:
            self._toml_edit.setPlainText("ME3 CLI not found — install Mod Engine 3 or set its path in App Settings")
            return
        toml_path = get_me3_profile_path(self._game_id, me3_path)
        if not toml_path:
            self._toml_edit.setPlainText("No ME3 profile found — install a mod first")
            return
        try:
            with open(toml_path, "r", encoding="utf-8") as f:
                self._toml_edit.setPlainText(f.read())
        except Exception as e:
            self._toml_edit.setPlainText(f"Error reading profile: {e}")

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ME3 TOML profile viewer (read-only, ME3-compatible games only)
        self._toml_edit = None
        if self._game_id in ME3_GAME_MAP:
            layout.addWidget(self._build_toml_viewer())

        # Find mods with settings
        configurable = self._find_configurable_mods()

        if not configurable:
            placeholder = QLabel("⚙  No configurable mods installed.\nInstall a mod from the Mods tab first.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color:#8888aa;font-size:13px;padding:40px;")
            placeholder.setWordWrap(True)
            layout.addWidget(placeholder)
            return

        # Mod selector (only shown when >1 mod has settings)
        if len(configurable) > 1:
            selector_bar = QWidget()
            selector_bar.setStyleSheet("background:#13132a;border-bottom:1px solid #2a2a4a;")
            sb = QHBoxLayout(selector_bar)
            sb.setContentsMargins(16, 8, 16, 8)
            sb.addWidget(QLabel("Mod:"))
            self._mod_selector = QComboBox()
            self._mod_selector.setFixedWidth(260)
            for entry in configurable:
                self._mod_selector.addItem(entry["mod"].get("name", entry["mod"]["id"]), entry)
            self._mod_selector.currentIndexChanged.connect(self._on_mod_selected)
            sb.addWidget(self._mod_selector)
            sb.addStretch()
            layout.addWidget(selector_bar)
        else:
            self._mod_selector = None

        # Config path hint
        self._path_lbl = QLabel("")
        self._path_lbl.setObjectName("muted")
        self._path_lbl.setContentsMargins(16, 8, 16, 4)
        layout.addWidget(self._path_lbl)

        # Scrollable settings area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 8, 16, 8)
        self._content_layout.setSpacing(12)
        scroll.setWidget(self._content)
        layout.addWidget(scroll)

        # Save bar (sticky bottom)
        save_bar = QWidget()
        save_bar.setStyleSheet("background:#13132a;border-top:1px solid #2a2a4a;")
        save_bar.setFixedHeight(50)
        sb_layout = QHBoxLayout(save_bar)
        sb_layout.setContentsMargins(16, 0, 16, 0)

        self._dirty_lbl = QLabel("")
        self._dirty_lbl.setStyleSheet("color:#f0c040;font-size:11px;font-weight:600;")
        sb_layout.addWidget(self._dirty_lbl)
        sb_layout.addStretch()

        self._undo_btn = QPushButton("Undo All")
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._on_undo)
        sb_layout.addWidget(self._undo_btn)

        self._reset_btn = QPushButton("Defaults")
        self._reset_btn.setObjectName("btn_warn")
        self._reset_btn.clicked.connect(self._on_reset)
        sb_layout.addWidget(self._reset_btn)

        self._save_btn = QPushButton("Save Changes")
        self._save_btn.setObjectName("btn_success")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        sb_layout.addWidget(self._save_btn)

        layout.addWidget(save_bar)

        # Load first mod's settings
        first = configurable[0]
        self._active_ini = first["ini_path"]
        self._path_lbl.setText(f"Config: {self._active_ini}")
        self._load_settings()

    def _on_mod_selected(self, index: int):
        if not self._mod_selector:
            return
        entry = self._mod_selector.itemData(index)
        if entry:
            self._active_ini = entry["ini_path"]
            self._path_lbl.setText(f"Config: {self._active_ini}")
            self._load_settings()

    def _load_settings(self):
        # Clear existing
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()
        self._original.clear()
        self._dirty.clear()

        config_path = self._active_ini
        if not config_path or not os.path.isfile(config_path):
            no_file = QLabel("Settings file not found.")
            no_file.setStyleSheet("color:#8888aa;font-size:12px;padding:20px;")
            self._content_layout.addWidget(no_file)
            return

        defaults = self._gdef.get("defaults", {})
        try:
            self._sections = parse_ini_file(config_path, defaults)
        except Exception as e:
            self.log_message.emit(f"Failed to parse settings: {e}", "error")
            return

        for section in self._sections:
            # Section header
            header_frame = QFrame()
            header_frame.setObjectName("card")
            header_layout = QVBoxLayout(header_frame)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(0)

            hdr = QLabel(section["name"])
            hdr.setObjectName("section_header")
            hdr.setContentsMargins(10, 6, 10, 6)
            header_layout.addWidget(hdr)

            for setting in section.get("settings", []):
                row = self._build_setting_row(setting)
                header_layout.addWidget(row)

            self._content_layout.addWidget(header_frame)

        self._content_layout.addStretch()

    def _build_setting_row(self, setting: dict) -> QWidget:
        key = setting["key"]
        value = setting["value"]
        description = setting.get("description", "")
        field_type = setting.get("type", "text")
        options = setting.get("options", [])

        self._original[key] = value

        row = QWidget()
        row.setStyleSheet("background:transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(12)
        row.setProperty("key", key)

        # Left side: name + description
        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(key)
        name_lbl.setStyleSheet("font-weight:600;font-size:12px;color:#e0e0ec;")
        info.addWidget(name_lbl)
        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
            desc_lbl.setWordWrap(True)
            info.addWidget(desc_lbl)
        row_layout.addLayout(info, stretch=1)

        # Right side: control
        if field_type == "select" and options:
            widget = QComboBox()
            widget.setFixedWidth(180)
            for opt in options:
                widget.addItem(opt["label"], opt["value"])
            idx = next((i for i, o in enumerate(options) if o["value"] == value), 0)
            widget.setCurrentIndex(idx)
            widget.currentIndexChanged.connect(lambda _: self._on_changed(key, widget))
        elif field_type == "number":
            widget = QSpinBox()
            widget.setFixedWidth(100)
            widget.setMinimum(setting.get("min", -9999))
            widget.setMaximum(setting.get("max", 99999))
            try:
                widget.setValue(int(value))
            except ValueError:
                widget.setValue(0)
            widget.valueChanged.connect(lambda _: self._on_changed(key, widget))
        else:
            widget = QLineEdit(value)
            widget.setFixedWidth(180)
            widget.textChanged.connect(lambda _: self._on_changed(key, widget))

        self._widgets[key] = widget
        row_layout.addWidget(widget, alignment=Qt.AlignRight | Qt.AlignVCenter)
        return row

    def _get_widget_value(self, key: str) -> str:
        widget = self._widgets.get(key)
        if widget is None:
            return ""
        if isinstance(widget, QComboBox):
            return widget.currentData() or ""
        elif isinstance(widget, QSpinBox):
            return str(widget.value())
        elif isinstance(widget, QLineEdit):
            return widget.text()
        return ""

    def _on_changed(self, key: str, widget):
        current = self._get_widget_value(key)
        original = self._original.get(key, "")
        if current != original:
            self._dirty.add(key)
            widget.setStyleSheet("border-left:3px solid #f0c040;border-radius:4px;")
        else:
            self._dirty.discard(key)
            widget.setStyleSheet("")
        self._update_save_bar()

    def _update_save_bar(self):
        n = len(self._dirty)
        self._save_btn.setEnabled(n > 0)
        self._undo_btn.setEnabled(n > 0)
        if n > 0:
            self._dirty_lbl.setText(f"● {n} unsaved change{'s' if n != 1 else ''}")
        else:
            self._dirty_lbl.setText("")

    def _on_save(self):
        if not self._dirty:
            return
        # Show confirmation with table of changes
        changes = {k: self._get_widget_value(k) for k in self._dirty}
        dlg = _SaveConfirmDialog(changes, self._original, self)
        if dlg.exec() != QDialog.Accepted:
            return

        config_path = self._active_ini
        try:
            save_ini_settings(config_path, changes)
            for key in list(self._dirty):
                self._original[key] = changes[key]
                w = self._widgets.get(key)
                if w:
                    w.setStyleSheet("")
            self._dirty.clear()
            self._update_save_bar()
            self.log_message.emit(f"Settings saved", "success")
        except Exception as e:
            self.log_message.emit(f"Save failed: {e}", "error")

    def _on_undo(self):
        for key in list(self._dirty):
            orig = self._original.get(key, "")
            widget = self._widgets.get(key)
            if widget is None:
                continue
            if isinstance(widget, QComboBox):
                setting = next((s for sec in self._sections
                               for s in sec["settings"] if s["key"] == key), None)
                if setting:
                    options = setting.get("options", [])
                    idx = next((i for i, o in enumerate(options) if o["value"] == orig), 0)
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(orig))
                except ValueError:
                    pass
            elif isinstance(widget, QLineEdit):
                widget.setText(orig)
            widget.setStyleSheet("")
        self._dirty.clear()
        self._update_save_bar()

    def _on_reset(self):
        defaults = self._gdef.get("defaults", {})
        if not defaults:
            return
        for key, default_val in defaults.items():
            widget = self._widgets.get(key)
            if widget is None:
                continue
            if isinstance(widget, QComboBox):
                setting = next((s for sec in self._sections
                               for s in sec["settings"] if s["key"] == key), None)
                if setting:
                    options = setting.get("options", [])
                    idx = next((i for i, o in enumerate(options) if o["value"] == str(default_val)), 0)
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(default_val))
                except ValueError:
                    pass
            elif isinstance(widget, QLineEdit):
                widget.setText(str(default_val))

    def refresh(self, game_info: dict):
        self._game_info = game_info
        # Rebuild entire tab to pick up new mods
        layout = self.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._widgets.clear()
        self._original.clear()
        self._dirty.clear()
        self._active_ini = None
        self._mod_selector = None
        self._build()


class _SaveConfirmDialog(QDialog):
    def __init__(self, changes: dict, original: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Changes")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(QLabel(f"Save {len(changes)} setting change(s)?"))

        table = QTableWidget(len(changes), 3)
        table.setHorizontalHeaderLabels(["Setting", "From", "To"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setMaximumHeight(200)

        for row, (key, new_val) in enumerate(changes.items()):
            table.setItem(row, 0, QTableWidgetItem(key))
            old_item = QTableWidgetItem(original.get(key, ""))
            old_item.setForeground(Qt.red)
            table.setItem(row, 1, old_item)
            new_item = QTableWidgetItem(new_val)
            new_item.setForeground(Qt.green)
            table.setItem(row, 2, new_item)

        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        confirm = QPushButton("Save")
        confirm.setObjectName("btn_success")
        confirm.clicked.connect(self.accept)
        btn_row.addWidget(confirm)
        layout.addLayout(btn_row)
