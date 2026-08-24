from PySide6.QtWidgets import QMainWindow,QSplitter,QListWidget,QTextEdit,QStatusBar,QToolBar,QWidget,QVBoxLayout,QLabel
from PySide6.QtCore import Qt
from IGBot.core.phone_manager import PhoneManager

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IGBot v0.1.0")
        self.resize(1400,850)

        tb=QToolBar("Main")
        tb.addAction("Refresh", self.refresh_devices)
        self.addToolBar(tb)

        splitter=QSplitter(Qt.Horizontal)
        self.sidebar=QListWidget()
        self.sidebar.addItems(["📱 Devices","👤 Accounts","▶ Sessions","📊 Analytics","⚙ Settings"])
        splitter.addWidget(self.sidebar)

        center=QWidget()
        layout=QVBoxLayout(center)
        layout.addWidget(QLabel("Connected Devices"))
        self.devices=QListWidget()
        layout.addWidget(self.devices)
        layout.addWidget(QLabel("Live Log"))
        self.log=QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        splitter.addWidget(center)
        splitter.setStretchFactor(1,1)
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self.refresh_devices()

    def refresh_devices(self):
        self.devices.clear()
        devs=PhoneManager.get_connected_devices()
        for d in devs:
            self.devices.addItem("🟢 "+d)
        self.log.append(f"Detected {len(devs)} device(s).")
        self.statusBar().showMessage(f"{len(devs)} device(s) connected")
