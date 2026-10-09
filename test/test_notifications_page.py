from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
