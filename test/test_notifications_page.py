from datetime import datetime

from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from IGBot.notifications import (
    NotificationService,
    NotificationSeverity,
    NotificationType,
)
from IGBot.ui.pages.notifications_page import NotificationsPage


def test_notifications_workspace_has_static_foundation():
    QApplication.instance() or QApplication([])
    page = NotificationsPage()

    assert page.page_header.title.text() == "Notifications"
    assert page.critical_value.text() == "0"
    assert page.warning_value.text() == "0"
    assert page.total_active_value.text() == "0"
    assert [
        page.severity.itemText(index) for index in range(page.severity.count())
    ] == [
        "All",
        "Critical",
        "Warning",
    ]
    assert page.notification_type.itemText(0) == "All"
    assert page.notification_type.itemText(1) == "Human Captcha"
    assert page.notification_type.itemText(7) == "Zero Interactions"
    assert [page.status.itemText(index) for index in range(page.status.count())] == [
        "Active",
        "Resolved",
        "All",
    ]
    assert page.status.currentText() == "Active"
    assert page.total_active_card.property("selected") is True
    assert page.critical_card.property("selected") is False
    assert page.critical_card.cursor().shape() == Qt.PointingHandCursor


def test_notifications_table_and_empty_state_are_ready_for_backend():
    QApplication.instance() or QApplication([])
    page = NotificationsPage()

    assert page.model.rowCount() == 0
    assert [
        page.model.headerData(column, Qt.Horizontal)
        for column in range(page.model.columnCount())
    ] == [
        "Severity",
        "Username",
        "Tag",
        "Device",
        "Type",
        "Since",
        "Actions",
    ]
    assert page.empty_state.isVisibleTo(page)
    assert page.empty_state.title.text() == "No active notifications."
    assert page.empty_state.description.text() == (
        "Accounts requiring operator attention will appear here automatically."
    )
    assert page.actions_delegate.ACTIONS == (
        ("view", "View Phone"),
        ("manage", "Open Phone Accounts"),
    )
    assert not page.table.isHidden()
    assert page.empty_state.parent() is page.table.viewport()


def test_notification_summary_cards_apply_filters():
    application = QApplication.instance() or QApplication([])
    page = NotificationsPage()
    page.show()
    application.processEvents()

    QTest.mouseClick(page.critical_card, Qt.LeftButton)
    assert page.severity.currentText() == "Critical"
    assert page.critical_card.property("selected") is True
    assert page.total_active_card.property("selected") is False

    QTest.mouseClick(page.warning_card, Qt.LeftButton)
    assert page.severity.currentText() == "Warning"
    assert page.warning_card.property("selected") is True
    assert page.critical_card.property("selected") is False

    page.status.setCurrentText("Resolved")
    QTest.mouseClick(page.total_active_card, Qt.LeftButton)
    assert page.severity.currentText() == "All"
    assert page.status.currentText() == "Active"
    assert page.total_active_card.property("selected") is True
    assert page.warning_card.property("selected") is False


def test_notifications_page_reads_service_and_filters(tmp_path):
    application = QApplication.instance() or QApplication([])
    service = NotificationService(tmp_path)
    service.create(
        "example",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
        device="phone-1",
        tag="campaign",
    )
    page = NotificationsPage(notification_service=service)
    page.show()
    application.processEvents()

    assert page.warning_value.text() == "1"
    assert page.total_active_value.text() == "1"
    assert page.model.rowCount() == 1
    assert page.model.data(page.model.index(0, 1)) == "example"

    page.severity.setCurrentText("Critical")
    assert page.model.rowCount() == 0


def test_since_column_uses_local_date_and_full_tooltip(tmp_path):
    application = QApplication.instance() or QApplication([])
    service = NotificationService(tmp_path)
    created = service.create(
        "example",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
        device="phone-1",
    )
    page = NotificationsPage(notification_service=service)
    application.processEvents()
    index = page.model.index(0, 5)
    expected = datetime.fromisoformat(created.detected_at).astimezone()

    assert page.model.data(index) == expected.strftime("%Y-%m-%d")
    tooltip = page.model.data(index, Qt.ToolTipRole)
    assert expected.strftime("%Y-%m-%d %H:%M:%S") in tooltip
    assert expected.strftime("%z") in tooltip


def test_notification_actions_emit_only_for_icon_hit_areas(tmp_path):
    application = QApplication.instance() or QApplication([])
    service = NotificationService(tmp_path)
    service.create(
        "example",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
        device="phone-1",
    )
    page = NotificationsPage(notification_service=service)
    page.show()
    application.processEvents()
    index = page.model.index(0, 6)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 92, 36)
    viewed = []
    managed = []
    page.view_phone_requested.connect(viewed.append)
    page.open_phone_accounts_requested.connect(managed.append)

    def click(x):
        event = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(x, 18),
            QPointF(x, 18),
            QPointF(x, 18),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        return page.actions_delegate.editorEvent(event, page.model, option, index)

    assert click(20)
    assert click(52)
    assert not click(88)
    assert viewed == ["phone-1"]
    assert managed == ["phone-1"]
