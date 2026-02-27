"""
Per-game page with Mods / ME3 Profile / Saves tabs.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QTabWidget, QFrame)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from app.config.config_manager import ConfigManager

_MDL2 = "Segoe MDL2 Assets"


def _mdl2_icon(char: str, size: int = 16, color: str = "#c0c0d8") -> QIcon:
    px = QPixmap(size, size)
    px.fill(QColor("transparent"))
    p = QPainter(px)
    p.setFont(QFont(_MDL2, int(size * 0.75)))
    p.setPen(QColor(color))
    p.drawText(px.rect(), Qt.AlignCenter, char)
    p.end()
    return QIcon(px)
from app.core.me3_service import ME3_GAME_MAP
from app.ui.tabs.settings_tab import ME3ProfileTab
from app.ui.tabs.saves_tab import SavesTab
from app.ui.tabs.mods_tab import ModsTab


class GamePage(QWidget):
    log_message = Signal(str, str)
    mod_installed = Signal(str)  # game_id
    auth_changed = Signal()

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
        self._saves_tab = SavesTab(self._game_id, self._game_info, self._config)

        self._tabs.addTab(self._mods_tab, _mdl2_icon("\uE7B8", 16), "Mods")

        # ME3 Profile tab — only for ME3-supported games
        self._profile_tab = None
        if self._game_id in ME3_GAME_MAP:
            self._profile_tab = ME3ProfileTab(self._game_id, self._game_info, self._config)
            self._tabs.addTab(self._profile_tab, _mdl2_icon("\uE713", 16), "ME3 Profile")
            self._profile_tab.log_message.connect(self.log_message)

        self._tabs.addTab(self._saves_tab, _mdl2_icon("\uE74E", 16), "Saves")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tabs)

        # Wire log signals
        self._mods_tab.log_message.connect(self.log_message)
        self._saves_tab.log_message.connect(self.log_message)

        self._mods_tab.mod_installed.connect(lambda: self.mod_installed.emit(self._game_id))
        self._mods_tab.auth_changed.connect(self.auth_changed)

    def refresh(self, game_info: dict):
        self._game_info = game_info
        self._mods_tab.refresh(game_info)
        if self._profile_tab:
            self._profile_tab.refresh(game_info)
        self._saves_tab.refresh(game_info)

    def _on_tab_changed(self, index: int):
        widget = self._tabs.widget(index)
        if widget is self._profile_tab and self._profile_tab:
            self._profile_tab._on_refresh()

    def show_mods_tab(self):
        self._tabs.setCurrentWidget(self._mods_tab)
