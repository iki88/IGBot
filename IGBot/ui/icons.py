from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def phone_icon() -> QIcon:
    """Return a compact phone glyph suitable for primary navigation."""
    icon = QIcon()
    icon.addPixmap(_phone_pixmap("#A1A1AA"), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_phone_pixmap("#F9FAFB"), QIcon.Selected, QIcon.Off)
    icon.addPixmap(_phone_pixmap("#F9FAFB"), QIcon.Active, QIcon.Off)
    return icon


def copy_icon(color: str = "#A1A1AA") -> QIcon:
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


def archive_icon(color: str = "#A1A1AA") -> QIcon:
    """Return an archive glyph matching the application's phone icon weight."""
    pixmap = _canvas()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(color), 1.6))
    painter.drawRoundedRect(QRectF(3, 4, 14, 4), 1, 1)
    painter.drawRoundedRect(QRectF(4, 8, 12, 9), 1, 1)
    painter.drawLine(8, 11, 12, 11)
    painter.end()
    return QIcon(pixmap)


def eye_icon(color: str = "#A1A1AA") -> QIcon:
    """Return a compact eye glyph for the phone-view toolbar action."""
    pixmap = _canvas()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(color), 1.5))
    outline = QPainterPath()
    outline.moveTo(2.5, 10)
    outline.cubicTo(6, 4, 14, 4, 17.5, 10)
    outline.cubicTo(14, 16, 6, 16, 2.5, 10)
    painter.drawPath(outline)
    painter.drawEllipse(QRectF(7.25, 7.25, 5.5, 5.5))
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
