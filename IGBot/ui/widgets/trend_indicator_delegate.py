from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)


class TrendIndicatorDelegate(QStyledItemDelegate):
    """Paint analytics values while coloring only their trend arrow."""

    INCREASE_COLOR = QColor("#22C55E")
    DECREASE_COLOR = QColor("#EF4444")

    @staticmethod
    def segments(value: object) -> tuple[str, str, str] | None:
        text = str(value or "")
        positions = tuple(
            (text.find(arrow), arrow) for arrow in ("▲", "▼") if arrow in text
        )
        if not positions:
            return None
        position, arrow = min(positions)
        return text[:position], arrow, text[position + 1 :]

    def paint(self, painter, option, index) -> None:
        parts = self.segments(index.data(Qt.DisplayRole))
        if parts is None:
            super().paint(painter, option, index)
            return

        display = QStyleOptionViewItem(option)
        self.initStyleOption(display, index)
        display.text = ""
        style = display.widget.style() if display.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, display, painter, display.widget)

        text_rect = style.subElementRect(
            QStyle.SE_ItemViewItemText, display, display.widget
        )
        prefix, arrow, suffix = parts
        metrics = display.fontMetrics
        widths = tuple(metrics.horizontalAdvance(part) for part in parts)
        total_width = sum(widths)
        if display.displayAlignment & Qt.AlignRight:
            x = text_rect.right() - total_width + 1
        elif display.displayAlignment & Qt.AlignHCenter:
            x = text_rect.x() + (text_rect.width() - total_width) // 2
        else:
            x = text_rect.x()

        selected = bool(display.state & QStyle.State_Selected)
        text_color = display.palette.color(
            QPalette.HighlightedText if selected else QPalette.Text
        )
        painter.save()
        painter.setFont(display.font)
        for part, width in zip((prefix, arrow, suffix), widths, strict=True):
            painter.setPen(
                self.INCREASE_COLOR
                if part == "▲"
                else self.DECREASE_COLOR
                if part == "▼"
                else text_color
            )
            painter.drawText(
                x,
                text_rect.y(),
                width,
                text_rect.height(),
                Qt.AlignLeft | Qt.AlignVCenter,
                part,
            )
            x += width
        painter.restore()
