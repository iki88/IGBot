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
    assert page.unfollow_page.filters.controls["min-following"].value() == 100
    assert page.tabs.tabText(3) == "Unfollow"
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
    page.remove_followers.set_entries(["remove.me"])
    page.remove_followers.enabled.setChecked(True)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["unfollow-any"] == "2-4"
    assert parsed["total-unfollows-limit"] == "20"
    assert parsed["delete-removed-followers"] is True
    assert parsed["remove-followers-from-file"] == ["remove_followers_users.txt"]
    assert (
        account.config_path.parent / "remove_followers_users.txt"
    ).read_text() == "remove.me\n"
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


def test_unfollow_uses_operator_layout_and_collapsed_schedule():
    page = UnfollowConfigurationPage()

    assert page.enabled.text() == "Enable Unfollow"
    assert page.schedule_section.toggle.text() == "Schedule"
    assert not page.schedule_section.body.isVisible()
    assert page.specific_users.name.text() == "Unfollow Specific Users"
    assert page.modes.labels["unfollow"].text() == "Only Users Followed by IGBot"
    assert page.search_method.text() == "Unfollow Using Search"
    assert page.own_following_method.text() == "Unfollow Using Own Following List"
    assert set(page.mode_options.controls) == {
        "unfollow",
        "unfollow-non-followers",
        "unfollow-any-non-followers",
        "unfollow-any-followers",
    }


def test_unfollow_action_range_updates_selected_engine_method_only():
    page = UnfollowConfigurationPage()
    page.set_configuration({"unfollow": "5-10", "min-following": 125})

    page.unfollow_amount.minimum.setValue(8)
    page.unfollow_amount.maximum.setValue(12)
    values = page.values()

    assert values["unfollow"] == "8-12"
    assert values["min-following"] == 125
    assert "unfollow-any" not in values


def test_unfollow_action_fields_share_follow_alignment():
    page = UnfollowConfigurationPage()
    grid = page.action_grid

    minimum = page.unfollow_amount.minimum
    maximum = page.unfollow_amount.maximum
    limit = page.limits.controls["total-unfollows-limit"]
    delay = page.numeric.controls["unfollow-delay"]

    assert minimum.width() == maximum.width() == limit.width() == delay.width() == 180
    assert grid.getItemPosition(grid.indexOf(minimum))[:2] == (0, 1)
    assert grid.getItemPosition(grid.indexOf(maximum))[:2] == (0, 3)
    assert grid.getItemPosition(grid.indexOf(limit))[:2] == (1, 1)
    assert grid.getItemPosition(grid.indexOf(delay))[:2] == (2, 1)


def test_specific_users_use_popup_resource_without_new_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    page = UnfollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.specific_users.set_entries(["first.user", "second_user"])
    page.specific_users.enabled.setChecked(True)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    parsed = yaml.safe_load(account.config_path.read_bytes())
    assert parsed["unfollow-from-file"] == ["unfollow_users.txt"]
    assert (account.config_path.parent / "unfollow_users.txt").read_text() == (
        "first.user\nsecond_user\n"
    )
    assert not any(str(key).startswith("igbot-") for key in parsed)
