from unittest.mock import Mock

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.app import _load_stylesheet
from IGBot.ui.widgets.configuration_widgets import (
    DecimalSettings,
    NumericSettings,
    RangePairSettings,
    WheelSafeDoubleSpinBox,
    WheelSafeSpinBox,
)
from IGBot.ui.widgets.navigation_sidebar import NavigationSidebar
from IGBot.ui.widgets.target_source_row import TargetSourceRow


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
        assert widget.buttonSymbols() == QAbstractSpinBox.NoButtons
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


def test_popup_label_uses_native_checkbox_text_geometry():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(_load_stylesheet())
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    normal = QCheckBox("Normal checkbox", container)
    popup = TargetSourceRow("Popup checkbox", container, switch_style=False)
    layout.addWidget(normal)
    layout.addWidget(popup)
    container.show()
    application.processEvents()

    option = QStyleOptionButton()
    normal.initStyleOption(option)
    contents = normal.style().subElementRect(QStyle.SE_CheckBoxContents, option, normal)
    normal_text_x = normal.mapTo(container, QPoint(contents.x(), 0)).x()
    popup_text_x = popup.name.mapTo(container, QPoint(0, 0)).x()

    assert popup.layout().spacing() == 0
    assert normal.sizeHint().height() == popup.sizeHint().height()
    assert popup_text_x == normal_text_x
    assert popup.name.cursor().shape() == Qt.PointingHandCursor

    container.close()
