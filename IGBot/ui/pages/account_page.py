from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
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
from IGBot.ui.icons import eye_icon, status_dot_icon
from IGBot.ui.pages.comment_configuration_page import CommentConfigurationPage
from IGBot.ui.pages.dm_configuration_page import DMConfigurationPage
from IGBot.ui.pages.follow_configuration_page import FollowConfigurationPage
from IGBot.ui.pages.like_configuration_page import LikeConfigurationPage
from IGBot.ui.pages.story_configuration_page import StoryConfigurationPage
from IGBot.ui.pages.timer_configuration_page import TimerConfigurationPage
from IGBot.ui.pages.unfollow_configuration_page import UnfollowConfigurationPage
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
        self._syncing_sources = False

        self.page_header = PageHeader(
            "Account", "Instagram account configuration.", self
        )
        back = QPushButton("Back", self)
        back.setObjectName("secondaryButton")
        back.clicked.connect(self.back_requested)
        self.page_header.add_action_widget(back)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("accountTabs")
        self.tabs.setIconSize(QSize(12, 12))
        self.tabs.addTab(self._build_overview(), "Overview")
        self.timer_page = TimerConfigurationPage(self.tabs)
        self.timer_page.changed.connect(self._mark_dirty)
        self.tabs.addTab(self.timer_page, "Timer")
        self.follow_page = FollowConfigurationPage(self.tabs)
        self.follow_page.changed.connect(self._mark_dirty)
        self.follow_page.changed.connect(self.update_follow_tab_indicator)
        self.tabs.addTab(self.follow_page, "Follow")
        self.unfollow_page = UnfollowConfigurationPage(self.tabs)
        self.unfollow_page.changed.connect(self._mark_dirty)
        self.unfollow_page.changed.connect(self.update_unfollow_tab_indicator)
        self.tabs.addTab(self.unfollow_page, "Unfollow")
        self.like_page = LikeConfigurationPage(self.tabs)
        self.like_page.changed.connect(self._mark_dirty)
        self.like_page.changed.connect(self.update_like_tab_indicator)
        self.tabs.addTab(self.like_page, "Like")
        self.comment_page = CommentConfigurationPage(self.tabs)
        self.comment_page.changed.connect(self._mark_dirty)
        self.comment_page.changed.connect(self.update_comment_tab_indicator)
        self.tabs.addTab(self.comment_page, "Comment")
        self.story_page = StoryConfigurationPage(self.tabs)
        self.story_page.changed.connect(self._mark_dirty)
        self.story_page.changed.connect(self.update_story_tab_indicator)
        self.tabs.addTab(self.story_page, "Story")
        self.dm_page = DMConfigurationPage(self.tabs)
        self.dm_page.changed.connect(self._mark_dirty)
        self.dm_page.changed.connect(self.update_dm_tab_indicator)
        self.tabs.addTab(self.dm_page, "DM")
        for name in self.TABS[8:]:
            self.tabs.addTab(QWidget(self.tabs), name)
        for page in self._source_pages():
            page.sources.changed.connect(
                lambda page=page: self._sync_sources_from(page.sources)
            )

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

        information, information_layout = self._section("Account Information", overview)
        information_layout.setContentsMargins(16, 12, 16, 12)
        information_layout.setSpacing(8)
        credential_form = QFormLayout()
        credential_form.setHorizontalSpacing(18)
        credential_form.setVerticalSpacing(8)
        self.username = QLineEdit(information)
        self.username.setObjectName("dialogInput")
        self.password = QLineEdit(information)
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
        self.application_id = QLineEdit(information)
        self.application_id.setObjectName("dialogInput")
        self.tag = QLineEdit(information)
        self.tag.setObjectName("dialogInput")
        self.tag.setPlaceholderText("Warmup, APK1, VIP, Client A, Germany")
        for editor in (self.username, self.password, self.application_id, self.tag):
            editor.setMaximumWidth(460)
        self.application_row = QWidget(information)
        self.application_layout = QHBoxLayout(self.application_row)
        self.application_layout.setContentsMargins(0, 0, 0, 0)
        self.application_layout.setSpacing(8)
        self.application_layout.addWidget(self.application_id, 1)
        self.detect_app_id_button = QPushButton("Detect", self.application_row)
        self.detect_app_id_button.setObjectName("secondaryButton")
        self.detect_app_id_button.setToolTip("Detect App ID")
        self.detect_app_id_button.clicked.connect(self.package_detection_requested)
        self.application_layout.addWidget(self.detect_app_id_button)
        self.application_row.setMaximumWidth(560)
        credential_form.addRow("Instagram App", self.application_row)
        credential_form.addRow("Tag", self.tag)
        information_layout.addLayout(credential_form)
        layout.addWidget(information)
        layout.addStretch()

        self.device = QLabel(overview)
        self.device.hide()
        for editor in (self.username, self.password, self.application_id, self.tag):
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
        heading.setObjectName("accountInformationTitle")
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
        self.tag.setText(str(configuration.get("tag") or ""))
        self.follow_page.set_configuration(configuration)
        self.timer_page.set_configuration(configuration)
        self.unfollow_page.set_configuration(configuration)
        self.like_page.set_configuration(configuration)
        self.comment_page.set_configuration(configuration)
        self.story_page.set_configuration(configuration)
        self.dm_page.set_configuration(configuration)
        self.update_follow_tab_indicator()
        self.update_unfollow_tab_indicator()
        self.update_like_tab_indicator()
        self.update_comment_tab_indicator()
        self.update_story_tab_indicator()
        self.update_dm_tab_indicator()
        self._loading = False
        self.mark_clean()

    def configuration_values(self) -> dict:
        values = self.follow_page.values()
        values.update(self.timer_page.values())
        values.update(self.unfollow_page.values())
        values.update(self.like_page.values())
        values.update(self.comment_page.values())
        values.update(self.story_page.values())
        values.update(self.dm_page.values())
        values.update(self.follow_page.sources.values())
        return values

    def _source_pages(self):
        return (
            self.follow_page,
            self.like_page,
            self.story_page,
            self.dm_page,
            self.comment_page,
        )

    def _sync_sources_from(self, source) -> None:
        if self._loading or self._syncing_sources:
            return
        self._syncing_sources = True
        try:
            values = source.state_values()
            for page in self._source_pages():
                if page.sources is not source:
                    page.sources.set_configuration(values)
        finally:
            self._syncing_sources = False

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
        self._set_module_tab_indicator(
            2, "Follow", self.follow_page.enabled.isChecked()
        )

    def update_unfollow_tab_indicator(self) -> None:
        enabled = self.unfollow_page.status.text() == "● Enabled"
        self._set_module_tab_indicator(3, "Unfollow", enabled)

    def update_like_tab_indicator(self) -> None:
        enabled = self.like_page.status.text() == "● Enabled"
        self._set_module_tab_indicator(4, "Like", enabled)

    def update_comment_tab_indicator(self) -> None:
        enabled = self.comment_page.spintax_method.isChecked()
        self._set_module_tab_indicator(5, "Comment", enabled)

    def update_story_tab_indicator(self) -> None:
        enabled = self.story_page.enabled.isChecked()
        self._set_module_tab_indicator(6, "Story", enabled)

    def update_dm_tab_indicator(self) -> None:
        enabled = self.dm_page.enabled.isChecked()
        self._set_module_tab_indicator(7, "DM", enabled)

    def _set_module_tab_indicator(self, index: int, name: str, enabled: bool) -> None:
        """Apply one consistent module-state marker to every account tab."""
        self.tabs.setTabText(index, name)
        self.tabs.setTabIcon(index, status_dot_icon(enabled))

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
