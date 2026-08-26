import pytest
import yaml
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.like_configuration_page import LikeConfigurationPage


def configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# retained comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'likes-count: "1-2"\r\n'
        b'likes-percentage: "80-90"\r\n'
        b'total-likes-limit: "250" # retained inline\r\n'
        b"end-if-likes-limit-reached: false\r\n"
        b'carousel-count: "1"\r\n'
        b'carousel-percentage: "60-70"\r\n'
        b'watch-photo-time: "3-4"\r\n'
        b'watch-video-time: "15-30"\r\n'
        b'posts-from-file: ["posts.txt"]\r\n'
        b"screen-sleep: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_like_load_status_and_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.like_page.interaction.controls["likes-count"].text() == "1-2"
    assert page.like_page.media.controls["watch-video-time"].text() == "15-30"
    assert page.tabs.tabText(4) == "● Like"
    assert not page.is_dirty

    page.like_page.limits.controls["total-likes-limit"].setText("300")
    assert page.is_dirty


def test_like_save_uses_only_documented_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    page = LikeConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.interaction.controls["likes-count"].setText("2-3")
    page.limits.controls["total-likes-limit"].setText("300")
    page.limit_behaviour.controls["end-if-likes-limit-reached"].setChecked(True)
    page.files.controls["posts-from-file"].setPlainText("first.txt\nsecond.txt")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["likes-count"] == "2-3"
    assert parsed["total-likes-limit"] == "300"
    assert parsed["end-if-likes-limit-reached"] is True
    assert parsed["posts-from-file"] == ["first.txt", "second.txt"]
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert b"# retained inline\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)


def test_like_validation_rejects_ranges_and_percentages():
    QApplication.instance() or QApplication([])
    page = LikeConfigurationPage()
    page.set_configuration({})

    page.interaction.controls["likes-count"].setText("5-2")
    with pytest.raises(ValueError, match="ascending range"):
        page.values()

    page.interaction.controls["likes-count"].setText("1")
    page.interaction.controls["likes-percentage"].setText("101")
    with pytest.raises(ValueError, match="cannot exceed 100"):
        page.values()


def test_empty_like_page_does_not_create_engine_keys():
    page = LikeConfigurationPage()
    page.set_configuration({})

    assert page.values() == {}
