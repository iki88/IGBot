import pytest
import yaml
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.unfollow_configuration_page import UnfollowConfigurationPage


def configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# retained comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'unfollow-non-followers: "5-10" # retained inline\r\n'
        b"min-following: 100\r\n"
        b"sort-followers-newest-to-oldest: true\r\n"
        b'unfollow-delay: "3"\r\n'
        b'unfollow-from-file: ["targets.txt 5-10"]\r\n'
        b"screen-sleep: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_unfollow_load_status_and_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.unfollow_page.modes.controls["unfollow-non-followers"].text() == "5-10"
    assert page.unfollow_page.numeric.controls["min-following"].value() == 100
    assert page.tabs.tabText(3) == "● Unfollow"
    assert not page.is_dirty

    page.unfollow_page.limits.controls["total-unfollows-limit"].setText("20-30")
    assert page.is_dirty


def test_unfollow_save_uses_only_documented_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    page = UnfollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.modes.controls["unfollow-any"].setText("2-4")
    page.limits.controls["total-unfollows-limit"].setText("20")
    page.behaviour.controls["delete-removed-followers"].setChecked(True)
    page.files.controls["remove-followers-from-file"].setPlainText("remove.txt")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["unfollow-any"] == "2-4"
    assert parsed["total-unfollows-limit"] == "20"
    assert parsed["delete-removed-followers"] is True
    assert parsed["remove-followers-from-file"] == ["remove.txt"]
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert b"# retained inline\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)


def test_unfollow_rejects_invalid_or_reversed_ranges():
    QApplication.instance() or QApplication([])
    page = UnfollowConfigurationPage()
    page.set_configuration({})

    page.modes.controls["unfollow"].setText("invalid")
    with pytest.raises(ValueError, match="unfollow must be"):
        page.values()

    page.modes.controls["unfollow"].setText("20-10")
    with pytest.raises(ValueError, match="ascending range"):
        page.values()


def test_empty_unfollow_page_does_not_create_engine_keys():
    page = UnfollowConfigurationPage()
    page.set_configuration({})

    assert page.values() == {}
