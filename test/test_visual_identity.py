from IGBot.ui.app import _load_stylesheet


def test_visual_identity_uses_the_approved_dark_palette():
    stylesheet = _load_stylesheet()
    for color in (
        "#18181B",
        "#27272A",
        "#3F3F46",
        "#F9FAFB",
        "#A1A1AA",
        "#52525B",
        "#3B82F6",
        "#22C55E",
        "#F59E0B",
        "#EF4444",
    ):
        assert color in stylesheet
    assert "#ffffff" not in stylesheet.lower()
    assert "#000000" not in stylesheet.lower()


def test_visual_identity_covers_shared_interactive_controls():
    stylesheet = _load_stylesheet()
    for selector in (
        "QTabWidget#accountTabs QTabBar::tab:selected",
        "QPushButton#primaryButton:hover",
        "QLineEdit:focus",
        "QCheckBox#configurationSwitch::indicator:checked",
        "QTableView#deviceTable::item:selected",
        "QDialog#inputDialog",
        "QToolButton#configurationSectionHeader:hover",
    ):
        assert selector in stylesheet


def test_popup_backed_labels_are_blue_without_underlines():
    stylesheet = _load_stylesheet()

    assert "QPushButton#linkButton:hover { color: #93C5FD; }" in stylesheet
    assert "QPushButton#checkboxLinkButton:hover { color: #93C5FD; }" in stylesheet
    assert "text-decoration: underline" not in stylesheet
