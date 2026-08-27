from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.pages.comment_configuration_page import CommentConfigurationPage
from IGBot.ui.pages.dm_configuration_page import DMConfigurationPage
from IGBot.ui.pages.follow_configuration_page import FollowConfigurationPage
from IGBot.ui.pages.like_configuration_page import LikeConfigurationPage
from IGBot.ui.pages.story_configuration_page import StoryConfigurationPage
from IGBot.ui.pages.unfollow_configuration_page import UnfollowConfigurationPage


class TemplateEditorDialog(QDialog):
    """Reuses account module pages while excluding account-specific controls."""

    save_requested = Signal(dict)

    def __init__(
        self, name: str, configuration: dict, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle(f"Edit Template — {name}")
        self.resize(940, 720)
        heading = QLabel(name, self)
        heading.setObjectName("dialogTitle")
        subtitle = QLabel(
            "Reusable behaviour only. Account identity, schedules, targets, and messages are excluded.",
            self,
        )
        subtitle.setObjectName("dialogSubtitle")
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("accountTabs")
        self.follow = FollowConfigurationPage(self.tabs, include_sources=False)
        self.unfollow = UnfollowConfigurationPage(self.tabs, include_file_targets=False)
        self.like = LikeConfigurationPage(
            self.tabs, include_file_targets=False, include_sources=False
        )
        self.story = StoryConfigurationPage(self.tabs, include_sources=False)
        self.dm = DMConfigurationPage(
            self.tabs, include_messages=False, include_sources=False
        )
        self.comment = CommentConfigurationPage(
            self.tabs, include_comments=False, include_sources=False
        )
        for label, page in (
            ("Follow", self.follow),
            ("Unfollow", self.unfollow),
            ("Like", self.like),
            ("Story", self.story),
            ("DM", self.dm),
            ("Comment", self.comment),
        ):
            page.set_configuration(configuration)
            self.tabs.addTab(page, label)

        self.error = QLabel(self)
        self.error.setObjectName("dialogError")
        self.error.hide()
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("Save Changes", self)
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._request_save)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.error)
        layout.addLayout(actions)
        self.save_shortcut = QShortcut(QKeySequence.Save, self)
        self.save_shortcut.activated.connect(self._request_save)

    def values(self) -> dict:
        values = self.follow.values()
        values.update(self.unfollow.values())
        values.update(self.like.values())
        values.update(self.story.values())
        values.update(self.dm.values())
        values.update(self.comment.values())
        return values

    def _request_save(self) -> None:
        try:
            values = self.values()
        except ValueError as error:
            self.error.setText(str(error))
            self.error.show()
            return
        self.error.hide()
        self.save_button.setEnabled(False)
        self.save_requested.emit(values)

    def save_succeeded(self) -> None:
        self.accept()

    def save_failed(self, message: str) -> None:
        self.save_button.setEnabled(True)
        self.error.setText(message)
        self.error.show()
