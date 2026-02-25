"""
Saves tab — save file management, backup, restore, transfer.
"""

from datetime import datetime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame, QSizePolicy,
                                QDialog)
from PySide6.QtCore import Qt, Signal
from app.config.config_manager import ConfigManager
from app.core.save_manager import (get_saves_info, transfer_save,
                                   create_backup, restore_backup, delete_backup)
from app.ui.dialogs.confirm_dialog import ConfirmDialog


class SavesTab(QWidget):
    log_message = Signal(str, str)

    def __init__(self, game_id: str, game_info: dict, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._game_info = game_info
        self._config = config
        self._build()
        self._load()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(16)

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _load(self):
        self._clear()
        saves_info = get_saves_info(self._game_info, self._game_id)

        if "error" in saves_info:
            err = QLabel(f"⚠  {saves_info['error']}")
            err.setStyleSheet("color:#8888aa;font-size:12px;padding:20px;")
            err.setWordWrap(True)
            self._layout.addWidget(err)
            self._layout.addStretch()
            return

        # ── Save directory info ────────────────────────────────
        dir_lbl = QLabel(f"Save directory: {saves_info['save_dir']}")
        dir_lbl.setObjectName("muted")
        dir_lbl.setWordWrap(True)
        self._layout.addWidget(dir_lbl)

        # ── Transfer cards ─────────────────────────────────────
        self._layout.addWidget(self._section_header("Transfer Saves"))
        transfer_row = QHBoxLayout()
        transfer_row.setSpacing(12)

        base_ext = saves_info['base_ext']
        coop_ext = saves_info['coop_ext']

        transfer_row.addWidget(self._transfer_card(
            "Base Game → Co-op",
            f"Copy your {base_ext} save to {coop_ext} so you can play co-op.",
            "base_to_coop", "btn_blue"
        ))
        transfer_row.addWidget(self._transfer_card(
            "Co-op → Base Game",
            f"Copy your {coop_ext} save back to {base_ext} for solo play.",
            "coop_to_base", "btn_warn"
        ))
        self._layout.addLayout(transfer_row)

        # ── Current save files ─────────────────────────────────
        self._layout.addWidget(self._section_header("Current Save Files"))
        files_row = QHBoxLayout()
        files_row.setSpacing(12)
        files_row.addWidget(self._file_group(
            f"Base Game ({base_ext})", saves_info['base_files']
        ))
        files_row.addWidget(self._file_group(
            f"Co-op ({coop_ext})", saves_info['coop_files']
        ))
        self._layout.addLayout(files_row)

        # ── Backup section ─────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(self._section_header("Backups"))
        hdr_row.addStretch()
        backup_now_btn = QPushButton("Backup Now")
        backup_now_btn.setObjectName("btn_success")
        backup_now_btn.setFixedHeight(28)
        backup_now_btn.clicked.connect(self._on_backup)
        hdr_row.addWidget(backup_now_btn)
        self._layout.addLayout(hdr_row)

        if saves_info['backups']:
            for backup in saves_info['backups']:
                self._layout.addWidget(self._backup_entry(backup, saves_info))
        else:
            no_back = QLabel("No backups yet.")
            no_back.setStyleSheet("color:#8888aa;font-style:italic;font-size:12px;")
            self._layout.addWidget(no_back)

        self._layout.addStretch()
        self._saves_info = saves_info

    def _section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        lbl.setContentsMargins(0, 0, 0, 0)
        lbl.setStyleSheet(
            "font-size:11px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.06em;color:#e94560;"
        )
        return lbl

    def _transfer_card(self, title: str, desc: str, direction: str, btn_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        t = QLabel(title)
        t.setStyleSheet("font-size:13px;font-weight:700;color:#e0e0ec;")
        layout.addWidget(t)

        d = QLabel(desc)
        d.setStyleSheet("font-size:11px;color:#8888aa;")
        d.setWordWrap(True)
        layout.addWidget(d)

        btn = QPushButton(f"Transfer →")
        btn.setObjectName(btn_name)
        btn.setFixedHeight(30)
        btn.clicked.connect(lambda: self._on_transfer(direction))
        layout.addWidget(btn)
        return card

    def _file_group(self, title: str, files: list) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        t = QLabel(title)
        t.setStyleSheet("font-size:11px;font-weight:700;text-transform:uppercase;"
                       "letter-spacing:0.05em;color:#8888aa;")
        layout.addWidget(t)

        if not files:
            empty = QLabel("No files found")
            empty.setStyleSheet("color:#8888aa;font-style:italic;font-size:11px;")
            layout.addWidget(empty)
        else:
            for f in files:
                fc = QFrame()
                fc.setStyleSheet("background:#0e0e18;border:1px solid #1e1e2e;border-radius:5px;")
                fl = QVBoxLayout(fc)
                fl.setContentsMargins(8, 6, 8, 6)
                fl.setSpacing(2)

                name_lbl = QLabel(f["name"])
                name_lbl.setStyleSheet("font-size:12px;font-weight:600;color:#e0e0ec;")
                fl.addWidget(name_lbl)

                size_kb = f["size"] // 1024
                mod_dt = f["modified"][:16].replace("T", " ")
                meta_lbl = QLabel(f"{size_kb} KB • {mod_dt}")
                meta_lbl.setStyleSheet("font-size:10px;color:#8888aa;")
                fl.addWidget(meta_lbl)
                layout.addWidget(fc)

        return frame

    def _backup_entry(self, backup: dict, saves_info: dict) -> QFrame:
        entry = QFrame()
        entry.setObjectName("card")
        layout = QHBoxLayout(entry)
        layout.setContentsMargins(12, 8, 12, 8)

        ts = backup["timestamp"].replace("_", " ")
        ts_lbl = QLabel(ts)
        ts_lbl.setStyleSheet("font-family:Consolas,monospace;font-size:12px;color:#e0e0ec;")
        layout.addWidget(ts_lbl)

        counts = QLabel(
            f"Base: {backup['base_count']} • Co-op: {backup['coop_count']}"
        )
        counts.setStyleSheet("font-size:11px;color:#8888aa;")
        layout.addWidget(counts)
        layout.addStretch()

        ts_raw = backup["timestamp"]
        restore_base_btn = QPushButton("→ Base")
        restore_base_btn.setObjectName("btn_blue")
        restore_base_btn.setFixedHeight(26)
        restore_base_btn.clicked.connect(lambda: self._on_restore(ts_raw, "base"))
        layout.addWidget(restore_base_btn)

        restore_coop_btn = QPushButton("→ Co-op")
        restore_coop_btn.setObjectName("btn_warn")
        restore_coop_btn.setFixedHeight(26)
        restore_coop_btn.clicked.connect(lambda: self._on_restore(ts_raw, "coop"))
        layout.addWidget(restore_coop_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("btn_danger")
        del_btn.setFixedSize(28, 26)
        del_btn.clicked.connect(lambda: self._on_delete_backup(ts_raw))
        layout.addWidget(del_btn)

        return entry

    def _on_transfer(self, direction: str):
        label = "Base → Co-op" if direction == "base_to_coop" else "Co-op → Base"
        dlg = ConfirmDialog(
            "Transfer Saves",
            f"Transfer saves: {label}?\nThe destination saves will be backed up first.",
            confirm_text="Transfer",
            parent=self
        )
        if dlg.exec() != QDialog.Accepted:
            return

        result = transfer_save(self._game_info, self._game_id, direction)
        level = "success" if result["success"] else "error"
        self.log_message.emit(result["message"], level)
        if result["success"]:
            self._load()

    def _on_backup(self):
        result = create_backup(self._game_info, self._game_id)
        level = "success" if result["success"] else "error"
        self.log_message.emit(result["message"], level)
        if result["success"]:
            self._load()

    def _on_restore(self, timestamp: str, dest_type: str):
        label = "Base Game" if dest_type == "base" else "Co-op"
        dlg = ConfirmDialog(
            "Restore Backup",
            f"Restore this backup to {label}?\nYour current {label} saves will be backed up first.",
            confirm_text="Restore",
            parent=self
        )
        if dlg.exec() != QDialog.Accepted:
            return

        result = restore_backup(self._game_info, self._game_id, timestamp, dest_type)
        level = "success" if result["success"] else "error"
        self.log_message.emit(result["message"], level)
        if result["success"]:
            self._load()

    def _on_delete_backup(self, timestamp: str):
        dlg = ConfirmDialog(
            "Delete Backup",
            f"Permanently delete backup from {timestamp.replace('_', ' ')}?",
            confirm_text="Delete",
            parent=self
        )
        if dlg.exec() != QDialog.Accepted:
            return

        result = delete_backup(self._game_info, self._game_id, timestamp)
        level = "success" if result["success"] else "error"
        self.log_message.emit(result["message"], level)
        if result["success"]:
            self._load()

    def refresh(self, game_info: dict):
        self._game_info = game_info
        self._load()
