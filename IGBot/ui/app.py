import sys
from PySide6.QtWidgets import QApplication
from IGBot.ui.main_window import MainWindow

def run_app():
    app=QApplication(sys.argv)
    win=MainWindow()
    win.show()
    sys.exit(app.exec())
