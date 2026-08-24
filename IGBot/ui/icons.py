from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def phone_icon() -> QIcon:
    """Return a compact phone glyph suitable for primary navigation."""
    icon = QIcon()
    icon.addPixmap(_phone_pixmap("#9caaba"), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_phone_pixmap("#f3f7fb"), QIcon.Selected, QIcon.Off)
    icon.addPixmap(_phone_pixmap("#f3f7fb"), QIcon.Active, QIcon.Off)
    return icon


def copy_icon(color: str = "#9caaba") -> QIcon:
    """Return a small copy glyph without relying on a platform icon theme."""
    pixmap = _canvas()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(color), 1.5))
    painter.drawRoundedRect(QRectF(5.5, 3.5, 9, 10), 1.5, 1.5)
    painter.drawRoundedRect(QRectF(3.5, 6.5, 9, 10), 1.5, 1.5)
    painter.end()
    return QIcon(pixmap)


def _phone_pixmap(color: str) -> QPixmap:
    pixmap = _canvas()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(color), 1.6))
    painter.drawRoundedRect(QRectF(5, 2, 10, 16), 2, 2)
    painter.drawLine(8, 5, 12, 5)
    painter.drawLine(9, 15, 11, 15)
    painter.end()
    return pixmap


def _canvas() -> QPixmap:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    return pixmap
