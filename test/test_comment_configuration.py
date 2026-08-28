import pytest
import yaml
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.comment_configuration_page import CommentConfigurationPage
from IGBot.ui.widgets.top_toolbar import TopToolbar


def configuration(tmp_path, comments="Hello {friend|there}!\nWonderful photo 😊\n"):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_bytes(
        b"# retained config comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'comment-percentage: "20-30"\r\n'
        b'total-comments-limit: "10" # retained inline\r\n'
        b'max-comments-pro-user: "1"\r\n'
        b"end-if-comments-limit-reached: false\r\n"
        b"screen-sleep: true\r\n"
    )
    (directory / "filters.yml").write_bytes(
        b"# retained filter comment\r\n"
        b"comment_photos: true\r\n"
        b"comment_videos: true\r\n"
        b"comment_carousels: false\r\n"
        b"comment_feed: false\r\n"
    )
    if comments is not None:
        (directory / "comments_list.txt").write_text(comments, encoding="utf-8")
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", config_path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_comment_load_status_dirty_state_and_shared_shortcut(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.comment_page.delivery.controls["comment-percentage"].text() == ("20-30")
    assert "Wonderful photo 😊" in page.comment_page.comments.text()
    assert page.comment_page.content_filters.controls["comment_photos"].isChecked()
    assert page.comment_page.spintax_method.isChecked()
    assert not page.comment_page.ai_method.isEnabled()
    assert page.tabs.tabText(5) == "Comment"
    assert not page.is_dirty
    assert TopToolbar().save_action.shortcut() == QKeySequence.Save

    page.comment_page.comments.editor.appendPlainText("Another comment")
    assert page.is_dirty


def test_comment_save_routes_values_to_engine_files(tmp_path):
    service, account = configuration(tmp_path)
    page = CommentConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.delivery.controls["comment-percentage"].setText("40-50")
    page.delivery.controls["max-comments-pro-user"].setText("2")
    page.limits.controls["total-comments-limit"].setText("25")
    page.limit_behaviour.controls["end-if-comments-limit-reached"].setChecked(True)
    page.content_filters.controls["comment_videos"].setChecked(False)
    page.source_filters.controls["comment_feed"].setChecked(True)
    page.comments.set_text("%PHOTO\nGreat {photo|shot} 😊\nSecond comment\n")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    config_bytes = account.config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    filters_bytes = (account.config_path.parent / "filters.yml").read_bytes()
    filters = yaml.safe_load(filters_bytes)
    assert config["comment-percentage"] == "40-50"
    assert config["max-comments-pro-user"] == "2"
    assert config["total-comments-limit"] == "25"
    assert config["end-if-comments-limit-reached"] is True
    assert "comment_photos" not in config
    assert "comments_list.txt" not in config
    assert filters["comment_videos"] is False
    assert filters["comment_feed"] is True
    assert (account.config_path.parent / "comments_list.txt").read_text(
        encoding="utf-8"
    ) == "%PHOTO\nGreat {photo|shot} 😊\nSecond comment\n"
    assert b"# retained config comment\r\n" in config_bytes
    assert b"# retained inline\r\n" in config_bytes
    assert b"# retained filter comment\r\n" in filters_bytes


def test_comment_generates_engine_text_resource(tmp_path):
    service, account = configuration(tmp_path, comments=None)
    page = CommentConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.comments.set_text("A new {comment|message} 😊")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    assert (account.config_path.parent / "comments_list.txt").read_text(
        encoding="utf-8"
    ) == "A new {comment|message} 😊"
    assert "comments_list.txt" not in yaml.safe_load(account.config_path.read_bytes())


def test_comment_validation_and_disabled_method():
    QApplication.instance() or QApplication([])
    page = CommentConfigurationPage()
    page.set_configuration({})
    page.delivery.controls["comment-percentage"].setText("101")
    with pytest.raises(ValueError, match="cannot exceed 100"):
        page.values()

    page.delivery.controls["comment-percentage"].setText("10")
    with pytest.raises(ValueError, match="at least one comment"):
        page.values()

    page.disabled_method.click()
    assert page.values()["comment-percentage"] == "0"
    assert page.status.text() == "● Disabled"


def test_empty_disabled_comment_page_does_not_create_engine_values():
    page = CommentConfigurationPage()
    page.set_configuration({})

    assert page.values() == {}


def test_comment_resource_failure_restores_every_file(tmp_path, monkeypatch):
    service, account = configuration(tmp_path)
    page = CommentConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.delivery.controls["comment-percentage"].setText("60")
    page.content_filters.controls["comment_photos"].setChecked(False)
    page.comments.set_text("Replacement")
    paths = {
        path: path.read_bytes()
        for path in (
            account.config_path,
            account.config_path.parent / "filters.yml",
            account.config_path.parent / "comments_list.txt",
        )
    }
    original_write = service._write_configuration
    failed = False

    def fail_comment_write(path, content):
        nonlocal failed
        if path.name == "comments_list.txt" and not failed:
            failed = True
            raise OSError("simulated comment write failure")
        original_write(path, content)

    monkeypatch.setattr(service, "_write_configuration", fail_comment_write)
    with pytest.raises(RuntimeError, match="original files were restored"):
        service.update_configuration(
            account, "account", "secret", "com.instagram.clone", page.values()
        )

    assert all(path.read_bytes() == content for path, content in paths.items())
