"""Checkbox editors for operator-facing alphabet and language filters."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

ALPHABETS = tuple(
    (name, name.lower())
    for name in (
        "Latin",
        "Cyrillic",
        "Greek",
        "Arabic",
        "Hebrew",
        "Japanese",
        "Chinese",
        "Korean",
        "Thai",
        "Hindi",
    )
)
LANGUAGES = (
    ("English", "en"),
    ("German", "de"),
    ("French", "fr"),
    ("Spanish", "es"),
    ("Italian", "it"),
    ("Portuguese", "pt"),
    ("Dutch", "nl"),
    ("Turkish", "tr"),
    ("Polish", "pl"),
    ("Czech", "cs"),
    ("Slovak", "sk"),
    ("Hungarian", "hu"),
    ("Romanian", "ro"),
    ("Russian", "ru"),
    ("Ukrainian", "uk"),
    ("Japanese", "ja"),
    ("Chinese", "zh"),
    ("Korean", "ko"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
)


class FilterSelectionDialog(QDialog):
    """Select canonical values without requiring operator text entry."""

    def __init__(self, title, choices, entries=(), parent=None):
        super().__init__(parent)
        self.setObjectName("inputDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(11)
        heading = QLabel(title, self)
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)
        layout.addWidget(
            QLabel("No selection: filter disabled. Everything allowed.", self)
        )
        aliases = {name.casefold(): value for name, value in choices}
        aliases.update({value: value for _, value in choices})
        if choices == ALPHABETS:
            aliases.update({"devanagari": "hindi", "han": "chinese"})
        selected = {
            aliases.get(str(entry).strip().casefold(), str(entry).strip())
            for entry in entries
        }
        self._unknown = selected - {value for _, value in choices}
        self.checkboxes = {}
        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        for index, (name, value) in enumerate(choices):
            checkbox = QCheckBox(name, self)
            checkbox.setChecked(value in selected)
            self.checkboxes[value] = checkbox
            grid.addWidget(checkbox, index // 2, index % 2)
        layout.addLayout(grid)
        actions = QHBoxLayout()
        self.select_all = QPushButton("Select All", self)
        self.select_none = QPushButton("Select None", self)
        self.select_all.clicked.connect(lambda: self._select(True))
        self.select_none.clicked.connect(lambda: self._select(False))
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save", self)
        save.setObjectName("primaryButton")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        for button in (self.select_all, self.select_none, cancel):
            button.setObjectName("secondaryButton")
        actions.addWidget(self.select_all)
        actions.addWidget(self.select_none)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _select(self, selected):
        self._unknown.clear()
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(selected)

    def entries(self):
        # Preserve unsupported legacy values until the operator explicitly clears
        # the selection, rather than silently weakening a saved filter.
        return [
            value for value, checkbox in self.checkboxes.items() if checkbox.isChecked()
        ] + sorted(self._unknown)
