from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from IGBot.ui.app import _load_stylesheet
from IGBot.ui.widgets.configuration_widgets import (
    DecimalSettings,
    NumericSettings,
    RangePairSettings,
    WheelSafeDoubleSpinBox,
    WheelSafeSpinBox,
)
from IGBot.ui.widgets.navigation_sidebar import NavigationSidebar


def test_all_shared_numeric_editors_ignore_mouse_wheel_input():
    QApplication.instance() or QApplication([])
    numeric = NumericSettings({"integer": "Integer"})
    decimal = DecimalSettings({"decimal": "Decimal"})
    pair = RangePairSettings("Minimum", "Maximum")
    widgets = (
        numeric.controls["integer"],
        decimal.controls["decimal"],
        pair.minimum,
    )

    for widget in widgets:
        widget.setValue(10)
        event = Mock()
        widget.wheelEvent(event)
        assert widget.value() == 10
        event.ignore.assert_called_once_with()

    assert isinstance(widgets[0], WheelSafeSpinBox)
    assert isinstance(widgets[1], WheelSafeDoubleSpinBox)


def test_sidebar_scrollbars_are_content_aware():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(_load_stylesheet())
    sidebar = NavigationSidebar()
    sidebar.show()
    application.processEvents()

    assert sidebar.navigation.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert sidebar.settings_navigation.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert sidebar.navigation.verticalScrollBar().maximum() == 0
    assert sidebar.settings_navigation.verticalScrollBar().maximum() == 0

    sidebar.close()
