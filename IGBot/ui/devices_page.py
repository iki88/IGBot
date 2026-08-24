from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QGroupBox,QFormLayout,QLabel,QPushButton
from IGBot.core.phone_manager import PhoneManager

class DevicesPage(QWidget):
    def __init__(self):
        super().__init__()

        main=QHBoxLayout(self)

        self.device_list=QListWidget()
        self.device_list.currentTextChanged.connect(self.update_details)

        left=QVBoxLayout()
        left.addWidget(self.device_list)

        refresh=QPushButton("Refresh Devices")
        refresh.clicked.connect(self.refresh)
        left.addWidget(refresh)

        main.addLayout(left,2)

        box=QGroupBox("Device Details")
        form=QFormLayout(box)

        self.serial=QLabel("-")
        self.status=QLabel("-")
        self.instagram=QLabel("Unknown")
        self.account=QLabel("Not Assigned")

        form.addRow("Serial:",self.serial)
        form.addRow("Status:",self.status)
        form.addRow("Instagram:",self.instagram)
        form.addRow("Account:",self.account)

        main.addWidget(box,1)

        self.refresh()

    def refresh(self):
        self.device_list.clear()
        for dev in PhoneManager.get_connected_devices():
            self.device_list.addItem(dev)

    def update_details(self,text):
        if not text:
            return
        self.serial.setText(text)
        self.status.setText("Connected")
