from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.device import AssignedAccount
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS
from IGBot.ui.icons import eye_icon
from IGBot.ui.pages.follow_configuration_page import FollowConfigurationPage
from IGBot.ui.pages.timer_configuration_page import TimerConfigurationPage
from IGBot.ui.widgets.page_header import PageHeader


class AccountPage(QWidget):
    """Shared account-detail screen for active and archived Instagram accounts."""

    back_requested = Signal()
    dirty_changed = Signal(bool)
    package_detection_requested = Signal()

    TABS = (
        "Overview",
        "Timer",
        "Follow",
        "Unfollow",
        "Like",
        "Comment",
        "Story",
        "DM",
        "Post",
        "Reels",
        "Share",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("accountPage")
        self.account: AssignedAccount | None = None
        self.is_dirty = False
        self._loading = False

        self.page_header = PageHeader(
            "Account", "Instagram account configuration.", self
        )
        back = QPushButton("Back", self)
        back.setObjectName("secondaryButton")
        back.clicked.connect(self.back_requested)
        self.page_header.add_action_widget(back)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("accountTabs")
        self.tabs.addTab(self._build_overview(), "Overview")
        self.timer_page = TimerConfigurationPage(self.tabs)
        self.timer_page.changed.connect(self._mark_dirty)
        self.tabs.addTab(self.timer_page, "Timer")
        self.follow_page = FollowConfigurationPage(self.tabs)
        self.follow_page.changed.connect(self._mark_dirty)
        self.follow_page.changed.connect(self.update_follow_tab_indicator)
        self.tabs.addTab(self.follow_page, "Follow")
        for name in self.TABS[3:]:
            self.tabs.addTab(QWidget(self.tabs), name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(self.page_header)
        layout.addWidget(self.tabs, 1)

    def _build_overview(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        overview = QWidget(scroll)
        layout = QVBoxLayout(overview)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(14)

        credentials, credential_layout = self._section("Login Credentials", overview)
        credential_form = QFormLayout()
        credential_form.setHorizontalSpacing(18)
        credential_form.setVerticalSpacing(10)
        self.username = QLineEdit(credentials)
        self.username.setObjectName("dialogInput")
        self.password = QLineEdit(credentials)
        self.password.setObjectName("dialogInput")
        self.password.setEchoMode(QLineEdit.Password)
        self.password_toggle = self.password.addAction(
            eye_icon(), QLineEdit.TrailingPosition
        )
        self.password_toggle.setCheckable(True)
        self.password_toggle.setToolTip("Show password")
        self.password_toggle.toggled.connect(self._toggle_password_visibility)
        credential_form.addRow("Username", self.username)
        credential_form.addRow("Password", self.password)
        credential_layout.addLayout(credential_form)
        session_actions = QHBoxLayout()
        self.login_button = QPushButton("Login", credentials)
        self.logout_button = QPushButton("Logout", credentials)
        for button in (self.login_button, self.logout_button):
            button.setObjectName("secondaryButton")
            button.setEnabled(False)
            session_actions.addWidget(button)
        session_actions.addStretch()
        credential_layout.addLayout(session_actions)
        layout.addWidget(credentials)

        app_cloner, app_layout = self._section("App Cloner", overview)
        app_form = QFormLayout()
        app_form.setHorizontalSpacing(18)
        self.application_id = QLineEdit(app_cloner)
        self.application_id.setObjectName("dialogInput")
        app_form.addRow("Application ID", self.application_id)
        app_layout.addLayout(app_form)
        app_actions = QHBoxLayout()
        self.detect_app_id_button = QPushButton("Detect App ID", app_cloner)
        self.detect_app_id_button.setObjectName("secondaryButton")
        self.detect_app_id_button.clicked.connect(self.package_detection_requested)
        app_actions.addWidget(self.detect_app_id_button)
        app_actions.addStretch()
        app_layout.addLayout(app_actions)
        layout.addWidget(app_cloner)

        reserved = QGridLayout()
        reserved.setHorizontalSpacing(12)
        reserved.setVerticalSpacing(12)
        for index, title in enumerate(("Participation", "Tags", "Limits", "Filters")):
            section, _ = self._section(title, overview)
            reserved.addWidget(section, index // 2, index % 2)
        layout.addLayout(reserved)
        layout.addStretch()

        self.device = QLabel(overview)
        self.device.hide()
        for editor in (self.username, self.password, self.application_id):
            editor.textChanged.connect(self._mark_dirty)
        scroll.setWidget(overview)
        return scroll

    @staticmethod
    def _section(title: str, parent: QWidget) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame(parent)
        section.setObjectName("contentCard")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        heading = QLabel(title, section)
        heading.setObjectName("deviceContextTitle")
        layout.addWidget(heading)
        return section, layout

    def _toggle_password_visibility(self, visible: bool) -> None:
        self.password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.password_toggle.setToolTip("Hide password" if visible else "Show password")

    def set_configuration(self, configuration: dict) -> None:
        self._loading = True
        self.username.setText(str(configuration.get("username") or ""))
        self.password.setText(str(configuration.get("password") or ""))
        self.application_id.setText(
            str(configuration.get("app-id") or configuration.get("app_id") or "")
        )
        self.follow_page.set_configuration(configuration)
        self.timer_page.set_configuration(configuration)
        self.update_follow_tab_indicator()
        self._loading = False
        self.mark_clean()

    def configuration_values(self) -> dict:
        values = self.follow_page.values()
        values.update(self.timer_page.values())
        return values

    def set_application_id(self, package: str) -> None:
        self.application_id.setText(package)

    def _mark_dirty(self, *_args) -> None:
        if self._loading or self.is_dirty:
            return
        self.is_dirty = True
        self.dirty_changed.emit(True)

    def mark_clean(self) -> None:
        if self.is_dirty:
            self.is_dirty = False
            self.dirty_changed.emit(False)

    def update_follow_tab_indicator(self) -> None:
        enabled = self.follow_page.enabled.isChecked()
        self.tabs.setTabText(2, f"{'●' if enabled else '○'} Follow")
        self.tabs.tabBar().setTabTextColor(
            2, QColor("#43c86b" if enabled else "#788697")
        )

    def set_account(self, account: AssignedAccount, phone_name: str = "") -> None:
        self.account = account
        self._loading = True
        self.page_header.title.setText(account.username)
        self.page_header.subtitle.setText("Instagram account settings and activity.")
        self.username.setText(account.username)
        self.password.clear()
        self.password_toggle.setChecked(False)
        self.device.setText(
            "Archived"
            if account.device_id == ARCHIVED_ACCOUNTS
            else phone_name or account.device_id
        )
        self.application_id.setText(account.app_id)
        self._loading = False
        self.mark_clean()
        self.tabs.setCurrentIndex(0)
