import pytest
from PySide6.QtWidgets import QApplication

from IGBot.ui.pages.follow_configuration_page import FollowConfigurationPage
from IGBot.ui.widgets.filter_selection_dialog import (
    ALPHABETS,
    LANGUAGES,
    FilterSelectionDialog,
)


@pytest.fixture(autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("choices", (ALPHABETS, LANGUAGES))
def test_selection_defaults_empty_and_all_none(choices):
    dialog = FilterSelectionDialog("Filter", choices)
    assert dialog.entries() == []
    dialog.select_all.click()
    assert dialog.entries() == [value for _, value in choices]
    dialog.select_none.click()
    assert dialog.entries() == []


@pytest.mark.parametrize(
    "choices, old, expected",
    (
        (ALPHABETS, ["LATIN", "Cyrillic"], ["latin", "cyrillic"]),
        (LANGUAGES, ["German", "EN", "Japanese"], ["en", "de", "ja"]),
    ),
)
def test_legacy_values_become_checked_canonical_values(choices, old, expected):
    dialog = FilterSelectionDialog("Filter", choices, old)
    assert dialog.entries() == expected


@pytest.mark.parametrize(
    "key, choices",
    (
        ("specific_alphabet", ALPHABETS),
        ("biography_language", LANGUAGES),
    ),
)
def test_follow_selection_save_and_empty_disable(mocker, key, choices):
    page = FollowConfigurationPage()
    page.set_configuration({key: [choices[0][0]]})
    selected = [choices[0][1], choices[1][1]]
    mocker.patch.object(
        FilterSelectionDialog, "exec", return_value=FilterSelectionDialog.Accepted
    )
    mocker.patch.object(FilterSelectionDialog, "entries", return_value=selected)
    page._edit_list_filter(key)
    assert page.values()[key] == selected
    mocker.patch.object(FilterSelectionDialog, "entries", return_value=[])
    page._edit_list_filter(key)
    assert not page.list_filters[key].enabled.isChecked()
    assert page.values()[key] is None
