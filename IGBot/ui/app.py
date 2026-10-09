import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from IGBot.logging_v2 import configure_logging, shutdown_logging
from IGBot.ui.main_window import MainWindow


def _load_stylesheet() -> str:
    stylesheet_path = Path(__file__).with_name("styles") / "dark.qss"
    return stylesheet_path.read_text(encoding="utf-8")


def run_app():
    QCoreApplication.setApplicationName("IGBot")
    QCoreApplication.setOrganizationName("IGBot")

    configure_logging(Path.cwd())
    exit_code = 1
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setStyleSheet(_load_stylesheet())

        win = MainWindow()
        win.show()
        exit_code = app.exec()
    finally:
        shutdown_logging()
    sys.exit(exit_code)
