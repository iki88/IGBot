from PySide6.QtCore import Signal
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
from IGBot.ui.widgets.page_header import PageHeader


class AccountPage(QWidget):
    """Shared account-detail screen for active and archived Instagram accounts."""

    back_requested = Signal()

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
        for name in self.TABS[1:]:
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
        self.password_toggle = QPushButton("Show", credentials)
        self.password_toggle.setObjectName("secondaryButton")
        self.password_toggle.setCheckable(True)
        self.password_toggle.toggled.connect(self._toggle_password_visibility)
        password_row = QWidget(credentials)
        password_layout = QHBoxLayout(password_row)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(8)
        password_layout.addWidget(self.password, 1)
        password_layout.addWidget(self.password_toggle)
        credential_form.addRow("Username", self.username)
        credential_form.addRow("Password", password_row)
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
        self.load_app_ids_button = QPushButton("Load App IDs", app_cloner)
        for button in (self.detect_app_id_button, self.load_app_ids_button):
            button.setObjectName("secondaryButton")
            button.setEnabled(False)
            app_actions.addWidget(button)
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
        self.password_toggle.setText("Hide" if visible else "Show")

    def set_configuration(self, configuration: dict) -> None:
        self.username.setText(str(configuration.get("username") or ""))
        self.password.setText(str(configuration.get("password") or ""))
        self.application_id.setText(
            str(configuration.get("app-id") or configuration.get("app_id") or "")
        )

    def set_account(self, account: AssignedAccount, phone_name: str = "") -> None:
        self.account = account
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
        self.tabs.setCurrentIndex(0)
