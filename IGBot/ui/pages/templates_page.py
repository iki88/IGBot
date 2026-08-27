from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from IGBot.core.account_template import AccountTemplate
from IGBot.ui.widgets.page_header import PageHeader


class TemplatesPage(QWidget):
    """Account-template management workspace."""

    create_requested = Signal()
    edit_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("templatesPage")
        header = PageHeader(
            "Templates",
            "Reusable behaviour profiles applied once when creating an account.",
            self,
        )
        create = QPushButton("Create Template", self)
        create.setObjectName("primaryButton")
        create.clicked.connect(self.create_requested)
        header.add_action_widget(create)
        self.list = QListWidget(self)
        self.list.setObjectName("configurationList")
        self.empty = QLabel("No account templates created.", self)
        self.empty.setObjectName("emptyStateTitle")
        self.edit = QPushButton("Edit", self)
        self.rename = QPushButton("Rename", self)
        self.delete = QPushButton("Delete", self)
        self.delete.setObjectName("dangerButton")
        for button in (self.edit, self.rename):
            button.setObjectName("secondaryButton")
        self.edit.clicked.connect(lambda: self._emit_selected(self.edit_requested))
        self.rename.clicked.connect(lambda: self._emit_selected(self.rename_requested))
        self.delete.clicked.connect(lambda: self._emit_selected(self.delete_requested))
        self.list.itemDoubleClicked.connect(
            lambda item: self.edit_requested.emit(item.text())
        )
        self.list.itemActivated.connect(
            lambda item: self.edit_requested.emit(item.text())
        )
        self.list.currentItemChanged.connect(lambda *_: self._update_actions())
        actions = QHBoxLayout()
        actions.addWidget(self.edit)
        actions.addWidget(self.rename)
        actions.addWidget(self.delete)
        actions.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        layout.addLayout(actions)
        self.set_templates(())

    def set_templates(self, templates: tuple[AccountTemplate, ...]) -> None:
        current = self.selected_name()
        self.list.clear()
        self.list.addItems([template.name for template in templates])
        matches = self.list.findItems(current, Qt.MatchExactly) if current else []
        if matches:
            self.list.setCurrentItem(matches[0])
        self.empty.setVisible(not templates)
        self.list.setVisible(bool(templates))
        self._update_actions()

    def selected_name(self) -> str:
        item = self.list.currentItem()
        return item.text() if item else ""

    def _emit_selected(self, signal) -> None:
        name = self.selected_name()
        if name:
            signal.emit(name)

    def _update_actions(self) -> None:
        selected = bool(self.selected_name())
        for button in (self.edit, self.rename, self.delete):
            button.setEnabled(selected)
