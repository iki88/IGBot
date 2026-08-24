import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _LogEmitter(QObject):
    message_ready = Signal(str)


class QtLogHandler(logging.Handler):
    """Forwards Python log records to Qt's main thread."""

    def __init__(self, emitter: _LogEmitter) -> None:
        super().__init__()
        self._emitter = emitter
        self.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emitter.message_ready.emit(self.format(record))
        except Exception:
            self.handleError(record)


class LiveLogPanel(QWidget):
    """Read-only view of application log records."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("liveLogPanel")

        title = QLabel("Live Log", self)
        title.setObjectName("panelTitle")
        clear_button = QPushButton("Clear", self)
        clear_button.setObjectName("tertiaryButton")

        self.output = QPlainTextEdit(self)
        self.output.setObjectName("liveLogOutput")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2_000)
        clear_button.clicked.connect(self.output.clear)

        self._emitter = _LogEmitter(self)
        self._emitter.message_ready.connect(self._append_message)
        self._handler = QtLogHandler(self._emitter)
        self._logging_attached = True
        logging.getLogger().addHandler(self._handler)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.output)

    def closeEvent(self, event) -> None:
        self.detach_logging()
        super().closeEvent(event)

    def detach_logging(self) -> None:
        if self._logging_attached:
            logging.getLogger().removeHandler(self._handler)
            self._logging_attached = False

    def _append_message(self, message: str) -> None:
        self.output.appendPlainText(message)
        self.output.moveCursor(QTextCursor.End)
