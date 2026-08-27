import yaml
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QKeySequence, QTextCursor
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.widgets.configuration_widgets import CollapsibleSection
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.target_source_row import TargetSourceRow
from IGBot.ui.widgets.top_toolbar import TopToolbar


def configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# retained comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'blogger-followers: ["source.one", "source_two"]\r\n'
        b'blogger-following: ["following.source"]\r\n'
        b'blogger: ["specific.user"] # retained inline\r\n'
        b'hashtag-posts-recent: ["cats", "dogs"]\r\n'
        b"screen-sleep: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_audience_sources_load_and_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    sources = page.follow_page.sources
    assert sources.rows["blogger-followers"].entries() == [
        "source.one",
        "source_two",
    ]
    assert sources.rows["blogger-followers"].enabled.isChecked()
    assert sources.rows["hashtag-posts-recent"].entries() == ["cats", "dogs"]
    assert "Audience Sources" not in [
        page.tabs.tabText(index) for index in range(page.tabs.count())
    ]
    assert not page.is_dirty
    assert TopToolbar().save_action.shortcut() == QKeySequence.Save

    sources.rows["blogger-followers"].enabled.setChecked(False)
    assert page.is_dirty


def test_audience_sources_save_only_documented_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    account_page = AccountPage()
    account_page.set_configuration(service.load_configuration(account.config_path))
    page = account_page.like_page.sources
    page.rows["blogger-followers"].set_entries(["new.source", "another.source"])
    page.rows["blogger"].enabled.setChecked(False)
    page.rows["place-posts-top"].set_entries(["Sarajevo", "Mostar"])
    page.rows["place-posts-top"].enabled.setChecked(True)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["blogger-followers"] == ["new.source", "another.source"]
    assert "blogger" not in parsed
    assert parsed["place-posts-top"] == ["Sarajevo", "Mostar"]
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)


def test_target_editor_cleans_empty_lines_and_removes_duplicates():
    QApplication.instance() or QApplication([])
    dialog = TargetEditorDialog("Targets", validator=lambda value: " " not in value)
    dialog.editor.setPlainText("first\n\nSECOND\nsecond\n")
    dialog.remove_duplicates()

    assert dialog.entries() == ["first", "SECOND"]
    dialog._validate_and_accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.editor.toPlainText() == "first\nSECOND"


def test_target_editor_supports_copy_paste_and_save_shortcut():
    application = QApplication.instance() or QApplication([])
    dialog = TargetEditorDialog("Targets", ["copy.me"])
    dialog.show()
    dialog.editor.setFocus()
    application.processEvents()
    dialog.editor.selectAll()
    dialog.editor.copy()
    assert application.clipboard().text() == "copy.me"

    dialog.editor.moveCursor(QTextCursor.End)
    pasted = QMimeData()
    pasted.setText("\npasted.target")
    dialog.editor.insertFromMimeData(pasted)
    assert dialog.entries() == ["copy.me", "pasted.target"]
    dialog.save_shortcut.activated.emit()
    assert dialog.result() == QDialog.Accepted


def test_audience_source_validation_rejects_enabled_empty_source():
    page = AccountPage().follow_page.sources
    page.set_configuration({})
    page.rows["blogger-followers"].enabled.setChecked(True)

    try:
        page.values()
    except ValueError as error:
        assert "at least one target" in str(error)
    else:
        raise AssertionError("An enabled empty source must be rejected.")


def test_module_source_label_launches_shared_target_editor_request():
    source = TargetSourceRow("Follow User's Followers")
    requested = QSignalSpy(source.edit_requested)

    source.name.click()

    assert requested.count() == 1


def test_module_sources_are_methods_without_duplicate_sources_heading():
    page = AccountPage()
    headings = [
        section.toggle.text()
        for section in page.follow_page.sources.findChildren(CollapsibleSection)
    ]
    assert headings == ["Method", "Advanced Sources"]
    assert "Sources" not in headings


def test_configuration_sections_are_permanently_expanded():
    section = CollapsibleSection("Limits")
    assert not section.toggle.isCheckable()
    assert section.body.isVisibleTo(section)
