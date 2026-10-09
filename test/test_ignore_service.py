from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from IGBot.runtime.ignore import IgnoreService
from IGBot.services.specific_lists_service import SpecificListsService
from IGBot.ui.widgets.ignore_list_dialog import IgnoreListDialog


def test_ignore_service_normalizes_and_deduplicates_on_save_and_load(tmp_path):
    saved = IgnoreService.save(
        tmp_path, [" Example_User ", "example_user", "SECOND.User", ""]
    )

    assert saved == ("example_user", "second.user")
    assert (tmp_path / "Lists" / "ignore.txt").read_text(encoding="utf-8") == (
        "example_user\nsecond.user\n"
    )
    loaded = IgnoreService.load(tmp_path)
    assert loaded.usernames == frozenset(("example_user", "second.user"))
    assert loaded.is_ignored("EXAMPLE_USER")


def test_running_ignore_service_is_an_immutable_session_snapshot(tmp_path):
    IgnoreService.save(tmp_path, ["first"])
    running = IgnoreService.load(tmp_path)

    IgnoreService.save(tmp_path, ["second"])

    assert running.is_ignored("first")
    assert not running.is_ignored("second")
    restarted = IgnoreService.load(tmp_path)
    assert restarted.is_ignored("second")
    assert not restarted.is_ignored("first")


def test_account_list_initialization_creates_ignore_file(tmp_path):
    lists = SpecificListsService(tmp_path)

    lists.initialize()

    assert (tmp_path / "Lists" / "ignore.txt").is_file()


def test_ignore_dialog_normalizes_entries_and_displays_count():
    QApplication.instance() or QApplication([])
    dialog = IgnoreListDialog(["First", "first", "SECOND"])

    assert dialog.entries() == ["first", "second"]
    assert dialog.count.text() == "2 accounts"
    assert dialog.windowTitle() == "Ignored Accounts List — 2 accounts"
    assert [button.text() for button in dialog.findChildren(QPushButton)] == [
        "Cancel",
        "Save",
    ]
    assert "One username per line." in dialog.guidance.text()
    assert (
        "normalized to lowercase, trimmed, and deduplicated" in dialog.guidance.text()
    )


def test_ignore_dialog_plain_text_save_normalizes_pasted_entries():
    QApplication.instance() or QApplication([])
    dialog = IgnoreListDialog()
    dialog.editor.setPlainText("  MIXED.User  \nmixed.user\nSecond\n\n")

    dialog._save()

    assert dialog.result() == QDialog.Accepted
    assert dialog.editor.toPlainText() == "mixed.user\nsecond"
