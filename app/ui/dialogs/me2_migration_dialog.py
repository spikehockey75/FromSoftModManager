"""
ME2 → ME3 migration dialog — shown when a Mod Engine 2 installation is detected
with real mods that can be imported into the app's ME3 workflow.

Also handles loose mods found in game directories via scan_game_folders().
"""

import os
import threading
import queue as _queue
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QProgressBar, QFrame,
                                QScrollArea, QWidget)
from PySide6.QtCore import Qt, QTimer

from app.config.config_manager import ConfigManager
from app.config.game_definitions import GAME_DEFINITIONS
from app.core.me2_migrator import migrate_selected
from app.ui.widgets.toggle_switch import ToggleSwitch


class ME2MigrationDialog(QDialog):
    """Dialog offering to import discovered mods into ME3 profiles.

    game_configs: merged dict from merge_scan_results(), keyed by game_id.
    """

    def __init__(self, game_configs: dict[str, dict], me3_exe_path: str,
                 config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_configs = game_configs
        self._me3_exe_path = me3_exe_path
        self._config = config
        self._pending: _queue.SimpleQueue = _queue.SimpleQueue()
        self._toggles: dict[str, ToggleSwitch] = {}

        self.setWindowTitle("Import Mods")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(500)
        self.setMinimumHeight(360)
        self._build()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(100)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel(">>")
        icon_lbl.setStyleSheet("font-size:24px;font-weight:700;color:#7b8cde;")
        title_row.addWidget(icon_lbl)
        title = QLabel("Import Mods")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#e0e0ec;")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Description
        desc = QLabel(
            "Found mods from Mod Engine 2 and game folders.\n"
            "Select which games to import:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px;color:#a0a0c0;")
        layout.addWidget(desc)

        # Scrollable game list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;}")
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # Sort games by display name
        sorted_games = sorted(
            self._game_configs.items(),
            key=lambda kv: GAME_DEFINITIONS.get(kv[0], {}).get("name", kv[0])
        )

        for game_id, gc in sorted_games:
            game_name = GAME_DEFINITIONS.get(game_id, {}).get("name", game_id)
            has_mods = bool(gc["packages"]) or bool(gc["natives"])

            # Game row: toggle + name
            game_row = QHBoxLayout()
            game_row.setSpacing(10)
            toggle = ToggleSwitch(checked=has_mods)
            if not has_mods:
                toggle.setEnabled(False)
            self._toggles[game_id] = toggle
            game_row.addWidget(toggle)

            name_lbl = QLabel(game_name)
            name_lbl.setStyleSheet("font-size:13px;font-weight:600;color:#e0e0ec;")
            game_row.addWidget(name_lbl)
            game_row.addStretch()
            scroll_layout.addLayout(game_row)

            # Mod list under this game
            if has_mods:
                for pkg in gc["packages"]:
                    mod_lbl = QLabel(f"      {pkg['name']}  (asset mod)")
                    mod_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
                    scroll_layout.addWidget(mod_lbl)
                for dll in gc["natives"]:
                    dll_name = _dll_display_name(dll)
                    mod_lbl = QLabel(f"      {dll_name}  (DLL mod)")
                    mod_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
                    scroll_layout.addWidget(mod_lbl)
            else:
                no_mods = QLabel("      (no additional mods found)")
                no_mods.setStyleSheet("font-size:11px;color:#555570;")
                scroll_layout.addWidget(no_mods)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#2a2a4a;")
        layout.addWidget(sep)

        # Status
        self._status_lbl = QLabel("Ready to import")
        self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")
        layout.addWidget(self._status_lbl)

        # Progress bar (hidden until migration starts)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._skip_btn = QPushButton("Skip")
        self._skip_btn.setObjectName("sidebar_mgmt_btn")
        self._skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._skip_btn)

        self._import_btn = QPushButton("  Import Selected")
        self._import_btn.setObjectName("btn_accent")
        self._import_btn.setFixedHeight(36)
        self._import_btn.setFixedWidth(170)
        self._import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(self._import_btn)

        layout.addLayout(btn_row)

    def _get_selected_ids(self) -> set[str]:
        return {gid for gid, toggle in self._toggles.items() if toggle.isChecked()}

    def _on_import(self):
        selected = self._get_selected_ids()
        if not selected:
            self._status_lbl.setText("No games selected")
            self._status_lbl.setStyleSheet("font-size:11px;color:#e94560;")
            return

        self._import_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        for toggle in self._toggles.values():
            toggle.setEnabled(False)
        self._progress.setVisible(True)
        self._status_lbl.setText("Importing mods...")
        self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")

        game_configs = self._game_configs
        me3_path = self._me3_exe_path
        config = self._config
        pending = self._pending

        def _work():
            pending.put(("progress", 30, "Importing mods..."))
            result = migrate_selected(game_configs, selected, me3_path, config)
            pending.put(("progress", 90, "Writing ME3 profiles..."))
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
                    self._on_done(result)
        except _queue.Empty:
            pass

    def _on_done(self, result: dict):
        self._poll_timer.stop()
        self._progress.setValue(100)

        imported = result.get("mods_imported", [])
        games = result.get("games_migrated", [])

        if imported:
            count = len(imported)
            game_names = [GAME_DEFINITIONS.get(g, {}).get("name", g) for g in games]
            self._status_lbl.setText(
                f"Imported {count} mod{'s' if count != 1 else ''} "
                f"for {', '.join(game_names)}"
            )
            self._status_lbl.setStyleSheet("font-size:11px;color:#4ecca3;font-weight:600;")
        else:
            self._status_lbl.setText("No new mods to import (already registered)")
            self._status_lbl.setStyleSheet("font-size:11px;color:#8888aa;")

        self._import_btn.setVisible(False)
        self._skip_btn.setText("Done")
        self._skip_btn.setEnabled(True)
        self._skip_btn.setObjectName("btn_success")
        self._skip_btn.setStyle(self._skip_btn.style())  # force QSS re-apply


def _dll_display_name(dll_path: str) -> str:
    """Derive a friendly display name for a DLL mod."""
    parent = os.path.basename(os.path.dirname(dll_path))
    if parent:
        return parent
    return os.path.splitext(os.path.basename(dll_path))[0]
