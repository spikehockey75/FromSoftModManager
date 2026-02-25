"""
FromSoft Mod Manager — PySide6 Desktop Application
Entry point.
"""

import faulthandler
faulthandler.enable()  # print Python stack on segfault

import os
import sys
import logging

# Ensure the app directory is on the path when running from PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

# SSL certs for PyInstaller
if getattr(sys, 'frozen', False):
    try:
        import certifi
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    except ImportError:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QCoreApplication
    from PySide6.QtGui import QFont

    QCoreApplication.setApplicationName("FromSoft Mod Manager")
    QCoreApplication.setOrganizationName("FromSoftModManager")
    QCoreApplication.setApplicationVersion("2.0.0")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # base style; overridden by QSS

    # Load dark theme
    qss_path = os.path.join(BASE_DIR, "resources", "dark_theme.qss")
    if os.path.isfile(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    # Font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Config
    from app.config.config_manager import ConfigManager
    config = ConfigManager()

    # ME3 is mandatory — prompt to install if missing
    from app.core.me3_service import find_me3_executable
    from app.ui.dialogs.me3_setup_dialog import ME3SetupDialog
    from PySide6.QtWidgets import QDialog
    if not find_me3_executable(config.get_me3_path()):
        dlg = ME3SetupDialog(config)
        if dlg.exec() != QDialog.Accepted:
            sys.exit(0)

    # One-time ME2 migration check
    if not config.get("me2_migrated"):
        from app.core.me2_migrator import (find_me2_installations,
                                           scan_me2_installation,
                                           scan_game_folders,
                                           merge_scan_results)
        me2_results = []
        for d in find_me2_installations():
            me2_results.extend(scan_me2_installation(d))
        game_results = scan_game_folders(config)
        merged = merge_scan_results(me2_results, game_results)
        if merged:
            from app.ui.dialogs.me2_migration_dialog import ME2MigrationDialog
            me3_path = find_me3_executable(config.get_me3_path())
            ME2MigrationDialog(merged, me3_path, config).exec()
        config.set("me2_migrated", True)

    # Main window
    from app.ui.main_window import MainWindow
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
