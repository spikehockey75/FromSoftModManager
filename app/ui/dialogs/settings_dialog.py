"""App-level settings dialog — Nexus API key, ME3 path, preferences."""

import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QLineEdit, QCheckBox, QFileDialog,
                                QGroupBox, QFormLayout, QDialogButtonBox)
from PySide6.QtCore import Qt, Signal
from app.config.config_manager import ConfigManager, _DEFAULT_MODS_DIR


class SettingsDialog(QDialog):
    settings_saved = Signal()
    _update_checked = Signal(object)  # internal: update check result from bg thread

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Settings")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(500)
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Settings")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#e0e0ec;")
        layout.addWidget(title)

        # ── Nexus Mods ────────────────────────────────────────
        nexus_group = QGroupBox("Nexus Mods")
        nexus_layout = QFormLayout(nexus_group)
        nexus_layout.setSpacing(10)

        self._nexus_key = QLineEdit()
        self._nexus_key.setPlaceholderText("Paste your Nexus API key here")
        self._nexus_key.setEchoMode(QLineEdit.Password)
        show_btn = QPushButton("Show")
        show_btn.setFixedWidth(60)
        show_btn.setCheckable(True)
        show_btn.toggled.connect(lambda on: self._nexus_key.setEchoMode(
            QLineEdit.Normal if on else QLineEdit.Password
        ))
        key_row = QHBoxLayout()
        key_row.addWidget(self._nexus_key)
        key_row.addWidget(show_btn)
        nexus_layout.addRow("API Key:", key_row)

        nexus_help = QLabel('<a href="https://www.nexusmods.com/users/myaccount?tab=api+access" '
                           'style="color:#e94560;">Get your API key from Nexus</a>')
        nexus_help.setOpenExternalLinks(True)
        nexus_help.setStyleSheet("font-size:11px;")
        nexus_layout.addRow("", nexus_help)

        self._signout_btn = QPushButton("Sign Out")
        self._signout_btn.setFixedWidth(80)
        self._signout_btn.setStyleSheet(
            "QPushButton{color:#e74c3c;font-size:11px;border:1px solid #e74c3c;"
            "background:transparent;border-radius:4px;padding:4px 12px;}"
            "QPushButton:hover{color:#fff;background:#e74c3c;}"
        )
        self._signout_btn.clicked.connect(self._sign_out)
        nexus_layout.addRow("", self._signout_btn)

        layout.addWidget(nexus_group)

        # ── ME3 ───────────────────────────────────────────────
        me3_group = QGroupBox("Mod Engine 3 (ME3)")
        me3_layout = QFormLayout(me3_group)
        me3_layout.setSpacing(10)

        self._use_me3 = QCheckBox("Use ME3 for launching games (recommended)")
        me3_layout.addRow("", self._use_me3)

        me3_path_row = QHBoxLayout()
        self._me3_path = QLineEdit()
        self._me3_path.setPlaceholderText("Auto-detect or browse…")
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_me3)
        me3_path_row.addWidget(self._me3_path)
        me3_path_row.addWidget(browse_btn)
        me3_layout.addRow("ME3 Path:", me3_path_row)

        me2_import_btn = QPushButton("Import from Mod Engine 2...")
        me2_import_btn.setObjectName("btn_blue")
        me2_import_btn.clicked.connect(self._import_me2)
        me3_layout.addRow("", me2_import_btn)

        me3_import_btn = QPushButton("Import from ME3 Profiles...")
        me3_import_btn.setObjectName("btn_blue")
        me3_import_btn.clicked.connect(self._import_me3_profiles)
        me3_layout.addRow("", me3_import_btn)

        layout.addWidget(me3_group)

        # ── Mod Storage ───────────────────────────────────────
        mods_group = QGroupBox("Mod Storage")
        mods_layout = QFormLayout(mods_group)
        mods_layout.setSpacing(10)

        mods_dir_row = QHBoxLayout()
        self._mods_dir = QLineEdit()
        self._mods_dir.setPlaceholderText("Default: <app folder>/mods")
        browse_mods_btn = QPushButton("Browse")
        browse_mods_btn.setFixedWidth(70)
        browse_mods_btn.clicked.connect(self._browse_mods_dir)
        reset_mods_btn = QPushButton("Reset")
        reset_mods_btn.setFixedWidth(60)
        reset_mods_btn.clicked.connect(self._reset_mods_dir)
        mods_dir_row.addWidget(self._mods_dir)
        mods_dir_row.addWidget(browse_mods_btn)
        mods_dir_row.addWidget(reset_mods_btn)
        mods_layout.addRow("Directory:", mods_dir_row)

        mods_help = QLabel("Extracted mod files for ME3-managed games are stored here.")
        mods_help.setStyleSheet("font-size:11px;color:#8888aa;")
        mods_layout.addRow("", mods_help)
        layout.addWidget(mods_group)

        # ── App Updates ────────────────────────────────────────
        update_group = QGroupBox("App Updates")
        update_layout = QFormLayout(update_group)
        update_layout.setSpacing(10)

        from app.services.update_service import get_current_version
        version_lbl = QLabel(f"v{get_current_version()}")
        version_lbl.setStyleSheet("font-size:12px;color:#e0e0ec;font-weight:600;")
        update_layout.addRow("Current version:", version_lbl)

        check_row = QHBoxLayout()
        self._check_update_btn = QPushButton("Check for Updates")
        self._check_update_btn.setObjectName("btn_blue")
        self._check_update_btn.setFixedWidth(160)
        self._check_update_btn.clicked.connect(self._check_for_updates)
        check_row.addWidget(self._check_update_btn)
        self._update_status_lbl = QLabel("")
        self._update_status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        check_row.addWidget(self._update_status_lbl)
        check_row.addStretch()
        update_layout.addRow("", check_row)

        layout.addWidget(update_group)

        # ── Buttons ───────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load(self):
        key = self._config.get_nexus_api_key()
        self._nexus_key.setText(key)
        self._signout_btn.setVisible(bool(key))
        self._me3_path.setText(self._config.get_me3_path())
        self._use_me3.setChecked(self._config.get_use_me3())
        self._mods_dir.setText(self._config.get_mods_dir())

    def _browse_me3(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select me3.exe", "", "Executables (*.exe)"
        )
        if path:
            self._me3_path.setText(path)

    def _import_me2(self):
        home = os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(
            self, "Select Mod Engine 2 Directory", home
        )
        if not path:
            return
        from app.core.me2_migrator import (scan_me2_installation,
                                           scan_game_folders,
                                           merge_scan_results)
        me2_results = scan_me2_installation(path)
        game_results = scan_game_folders(self._config)
        merged = merge_scan_results(me2_results, game_results)
        if not merged:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "No Mods Found",
                "No importable mods were found.\n"
                "Make sure you selected a Mod Engine 2 folder with config_*.toml files."
            )
            return
        from app.core.me3_service import find_me3_executable
        from app.ui.dialogs.me2_migration_dialog import ME2MigrationDialog
        me3_path = find_me3_executable(self._config.get_me3_path())
        dlg = ME2MigrationDialog(merged, me3_path, self._config, parent=self)
        dlg.exec()

    def _import_me3_profiles(self):
        from app.core.me3_service import find_me3_executable
        me3_path = find_me3_executable(self._config.get_me3_path())
        if not me3_path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "ME3 Not Found",
                "Mod Engine 3 was not found. Please set the ME3 path first."
            )
            return
        from app.core.me2_migrator import (scan_me3_profiles,
                                           scan_game_folders,
                                           merge_scan_results)
        me3_results = scan_me3_profiles(me3_path)
        game_results = scan_game_folders(self._config)
        merged = merge_scan_results(me3_results, game_results)
        if not merged:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "No Mods Found",
                "No importable mods were found in existing ME3 profiles."
            )
            return
        from app.ui.dialogs.me2_migration_dialog import ME2MigrationDialog
        dlg = ME2MigrationDialog(merged, me3_path, self._config, parent=self)
        dlg.exec()

    def _check_for_updates(self):
        self._check_update_btn.setEnabled(False)
        self._update_status_lbl.setText("Checking…")
        self._update_status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        self._update_checked.connect(self._on_update_check_done)

        import threading

        def _work():
            from app.services.update_service import check_for_update
            result = check_for_update()
            self._update_checked.emit(result)

        threading.Thread(target=_work, daemon=True).start()

    def _on_update_check_done(self, result):
        self._check_update_btn.setEnabled(True)
        self._update_checked.disconnect(self._on_update_check_done)
        if result.get("error"):
            self._update_status_lbl.setText(f"Error: {result['error']}")
            self._update_status_lbl.setStyleSheet("font-size:11px;color:#e74c3c;")
        elif result.get("has_update"):
            latest = result.get("latest", "?")
            self._update_status_lbl.setText(f"Update available: v{latest}")
            self._update_status_lbl.setStyleSheet("font-size:11px;color:#b0d880;font-weight:600;")
        else:
            self._update_status_lbl.setText("Up to date")
            self._update_status_lbl.setStyleSheet("font-size:11px;color:#4a6a2a;font-weight:600;")

    def _browse_mods_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Mod Storage Directory", self._mods_dir.text() or ""
        )
        if path:
            self._mods_dir.setText(path)

    def _reset_mods_dir(self):
        self._mods_dir.setText(_DEFAULT_MODS_DIR)

    def _sign_out(self):
        self._config.clear_nexus_auth()
        self._nexus_key.clear()
        self._signout_btn.setVisible(False)
        self.settings_saved.emit()

    def _save(self):
        key = self._nexus_key.text().strip()
        if key:
            self._config.set_nexus_api_key(key)
        self._config.set_me3_path(self._me3_path.text().strip())
        self._config.set_use_me3(self._use_me3.isChecked())
        mods_dir = self._mods_dir.text().strip()
        if mods_dir:
            self._config.set_mods_dir(mods_dir)
        self.settings_saved.emit()
        self.accept()
