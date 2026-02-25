"""
Per-game page with Launch / Settings / Saves / Mods tabs.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QTabWidget, QFrame)
from PySide6.QtCore import Qt, Signal
from app.config.config_manager import ConfigManager
from app.ui.tabs.settings_tab import SettingsTab
from app.ui.tabs.saves_tab import SavesTab
from app.ui.tabs.mods_tab import ModsTab


class GamePage(QWidget):
    log_message = Signal(str, str)
    mod_installed = Signal(str)  # game_id

    def __init__(self, game_id: str, game_info: dict, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._mods_tab = ModsTab(self._game_id, self._game_info, self._config)
        self._settings_tab = SettingsTab(self._game_id, self._game_info, self._config)
        self._saves_tab = SavesTab(self._game_id, self._game_info, self._config)

        self._tabs.addTab(self._mods_tab, "📦  Mods")
        self._tabs.addTab(self._settings_tab, "⚙  Settings")
        self._tabs.addTab(self._saves_tab, "💾  Saves")

        layout.addWidget(self._tabs)

        # Wire log signals
        for tab in [self._mods_tab, self._settings_tab, self._saves_tab]:
            tab.log_message.connect(self.log_message)

        self._mods_tab.mod_installed.connect(lambda: self.mod_installed.emit(self._game_id))

    def refresh(self, game_info: dict):
        self._game_info = game_info
        self._mods_tab.refresh(game_info)
        self._settings_tab.refresh(game_info)
        self._saves_tab.refresh(game_info)

    def show_mods_tab(self):
        self._tabs.setCurrentWidget(self._mods_tab)
