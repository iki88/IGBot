import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from IGBot.ui.main_window import MainWindow


def _load_stylesheet() -> str:
    stylesheet_path = Path(__file__).with_name("styles") / "dark.qss"
    return stylesheet_path.read_text(encoding="utf-8")


def run_app():
    QCoreApplication.setApplicationName("IGBot")
    QCoreApplication.setOrganizationName("IGBot")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(_load_stylesheet())

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
