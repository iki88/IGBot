import json

import pytest
import yaml
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.specific_lists_service import SpecificListsService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.unfollow_configuration_page import UnfollowConfigurationPage
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog


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


def test_enabling_unfollow_does_not_select_method_or_filter():
    page = UnfollowConfigurationPage()
    page.set_configuration({})

    page.enabled.setChecked(True)

    assert not page.search_method.isChecked()
    assert not page.following_list_search_method.isChecked()
    assert not page.specific_users.enabled.isChecked()
    assert not page.all_followings_method.isChecked()
    assert not any(page.mode_options.values().values())


def test_unfollow_child_edits_do_not_disable_module():
    page = UnfollowConfigurationPage()
    page.set_configuration({})
    page.enabled.setChecked(True)

    page.search_method.setChecked(True)
    page.limits.controls["total-unfollows-limit"].setText("2-5")
    page.numeric.controls["unfollow-delay"].setValue(3)
    page.mode_options.controls["unfollow"].setChecked(True)
    page.behaviour.controls["delete-removed-followers"].setChecked(True)

    assert page.enabled.isChecked()


def test_unfollow_child_edits_do_not_enable_module():
    page = UnfollowConfigurationPage()
    page.set_configuration({})

    page.search_method.setChecked(True)
    page.limits.controls["total-unfollows-limit"].setText("2")
    page.numeric.controls["unfollow-delay"].setValue(3)
    page.mode_options.controls["unfollow"].setChecked(True)

    assert not page.enabled.isChecked()


@pytest.mark.parametrize(
    ("configuration", "expected"),
    (({"unfollow": "2"}, True), ({}, False)),
)
def test_loading_configuration_restores_unfollow_enable_state(configuration, expected):
    page = UnfollowConfigurationPage()

    page.set_configuration(configuration)

    assert page.enabled.isChecked() is expected


@pytest.mark.parametrize("limit", ("2", "2-5"))
def test_implemented_unfollow_accepts_fixed_and_ranged_limits(tmp_path, limit):
    service, account = configuration(tmp_path)

    updated = service.update_configuration(
        account,
        "account",
        "secret",
        "com.instagram.clone",
        {
            "unfollow": "1",
            "total-unfollows-limit": limit,
            "unfollow-delay": "3",
        },
    )

    saved = yaml.safe_load(updated.config_path.read_bytes())
    assert saved["total-unfollows-limit"] == limit


def test_unimplemented_unfollow_options_do_not_block_save(tmp_path):
    service, account = configuration(tmp_path)

    updated = service.update_configuration(
        account,
        "account",
        "secret",
        "com.instagram.clone",
        {
            "unfollow": "1",
            "unfollow-non-followers": "",
            "unfollow-any-non-followers": "not-implemented",
            "unfollow-any-followers": None,
        },
    )

    assert updated.username == "account"


def test_unfollow_uses_operator_layout_and_collapsed_schedule():
    page = UnfollowConfigurationPage()

    assert page.enabled.text() == "Enable Unfollow"
    assert page.schedule_section.toggle.text() == "Schedule"
    assert not page.schedule_section.body.isVisible()
    assert page.specific_users.name.text() == "Unfollow Specific Users"
    assert page.modes.labels["unfollow"].text() == "Only Users Followed by IGBot"
    assert page.search_method.text() == "Unfollow Using Search"
    assert (
        page.following_list_search_method.text()
        == "Unfollow Using Following List Search"
    )
    assert page.all_followings_method.text() == "Unfollow All Followings"
    assert page.actions_section.title.text() == "Unfollow Actions"
    assert page.timing_section.title.text() == "Unfollow Timing"
    assert page.additional_section.title.text() == "Additional Unfollow Settings"
    assert set(page.mode_options.controls) == {
        "unfollow",
        "unfollow-non-followers",
    }


def test_unfollow_methods_are_mutually_exclusive():
    page = UnfollowConfigurationPage()
    methods = (
        page.search_method,
        page.following_list_search_method,
        page.specific_users.enabled,
        page.all_followings_method,
    )

    for selected in methods:
        selected.setChecked(True)
        assert [method.isChecked() for method in methods].count(True) == 1
        assert selected.isChecked()


def test_all_followings_disables_history_settings_and_shows_warning_and_sorting():
    page = UnfollowConfigurationPage()
    page.search_method.setChecked(True)
    page.mode_options.controls["unfollow"].setChecked(True)

    page.all_followings_method.setChecked(True)

    assert not any(page.mode_options.values().values())
    assert not any(
        control.isEnabled() for control in page.mode_options.controls.values()
    )
    assert not page.all_followings_warning.isHidden()
    assert not page.sort_following_list.isHidden()

    page.search_method.setChecked(True)

    assert all(control.isEnabled() for control in page.mode_options.controls.values())
    assert page.all_followings_warning.isHidden()
    assert page.sort_following_list.isHidden()


def test_unfollow_history_options_are_mutually_exclusive():
    page = UnfollowConfigurationPage()
    page.search_method.setChecked(True)
    followed_by_igbot = page.mode_options.controls["unfollow"]
    did_not_follow_back = page.mode_options.controls["unfollow-non-followers"]

    followed_by_igbot.setChecked(True)
    assert followed_by_igbot.isChecked()
    assert not did_not_follow_back.isChecked()

    did_not_follow_back.setChecked(True)
    assert did_not_follow_back.isChecked()
    assert not followed_by_igbot.isChecked()


@pytest.mark.parametrize("key", ("unfollow", "unfollow-non-followers"))
def test_existing_unfollow_history_option_loads_and_saves(key):
    page = UnfollowConfigurationPage()
    page.set_configuration({key: "2-5"})

    assert page.mode_options.controls[key].isChecked()
    assert page.values()[key] == "2-5"


def test_unfollow_ui_only_method_and_sort_persist_in_account_metadata(tmp_path):
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))
    page.unfollow_page.enabled.setChecked(True)
    page.unfollow_page.following_list_search_method.setChecked(True)

    service.update_configuration(
        account,
        "account",
        "secret",
        "com.instagram.clone",
        page.configuration_values(),
    )

    metadata = json.loads(
        (account.config_path.parent / "account.json").read_text(encoding="utf-8")
    )
    assert metadata["runtime_extensions"]["unfollow"] == {
        "enabled": True,
        "method": "following-list-search",
        "sort": "default",
        "budget": "5-10",
        "action_delay": "0",
    }
    loaded = service.load_configuration(account.config_path)
    assert loaded["igbot-unfollow-enabled"] is True
    assert loaded["igbot-unfollow-method"] == "following-list-search"


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
    action_delay_minimum = page.unfollow_action_delay.minimum
    action_delay_maximum = page.unfollow_action_delay.maximum
    delay = page.numeric.controls["unfollow-delay"]

    assert (
        minimum.width()
        == maximum.width()
        == action_delay_minimum.width()
        == action_delay_maximum.width()
        == limit.width()
        == delay.width()
        == 180
    )
    assert grid.getItemPosition(grid.indexOf(minimum))[:2] == (0, 1)
    assert grid.getItemPosition(grid.indexOf(maximum))[:2] == (0, 3)
    assert grid.getItemPosition(grid.indexOf(action_delay_minimum))[:2] == (1, 1)
    assert grid.getItemPosition(grid.indexOf(action_delay_maximum))[:2] == (1, 3)
    assert grid.getItemPosition(grid.indexOf(limit))[:2] == (2, 1)
    assert grid.getItemPosition(grid.indexOf(page.unfollow_limit_help))[0] == 3
    assert "Daily hard limit" in page.unfollow_limit_help.text()
    assert grid.indexOf(delay) == -1
    assert page.timing_grid.getItemPosition(page.timing_grid.indexOf(delay))[:2] == (
        0,
        1,
    )


def test_unfollow_action_delay_persists_as_account_metadata(tmp_path):
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))
    page.unfollow_page.unfollow_action_delay.minimum.setValue(4)
    page.unfollow_page.unfollow_action_delay.maximum.setValue(8)

    service.update_configuration(
        account,
        "account",
        "secret",
        "com.instagram.clone",
        page.configuration_values(),
    )

    loaded = service.load_configuration(account.config_path)
    assert loaded["igbot-unfollow-action-delay"] == "4-8"


def test_unfollow_delay_availability_and_message_preserve_value():
    page = UnfollowConfigurationPage()
    delay = page.numeric.controls["unfollow-delay"]
    delay.setValue(3)

    page.search_method.setChecked(True)
    assert delay.isEnabled()
    assert page.unfollow_timing_message.isHidden()

    page.specific_users.enabled.setChecked(True)
    assert not delay.isEnabled()
    assert not page.unfollow_timing_message.isHidden()
    assert page.unfollow_timing_message.text() == (
        "Unfollow Delay does not apply to this method.\n"
        "Specific Users are processed immediately."
    )

    page.all_followings_method.setChecked(True)
    assert not delay.isEnabled()
    assert page.unfollow_timing_message.text() == (
        "Unfollow Delay does not apply to this method.\n"
        "This provider walks your Instagram Following list directly."
    )

    page.following_list_search_method.setChecked(True)
    assert delay.isEnabled()
    assert delay.value() == 3
    assert page.unfollow_timing_message.isHidden()


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


def test_specific_unfollow_popup_loads_and_saves_account_list(tmp_path, mocker):
    _service, account = configuration(tmp_path)
    lists = SpecificListsService(account.config_path.parent)
    lists.save("unfollowspecific.txt", ["stored.one", "stored.two"])
    page = UnfollowConfigurationPage()
    page.set_account_directory(account.config_path.parent)
    page.set_configuration(
        {
            "igbot-unfollow-method": "specific-users",
            "igbot-unfollow-enabled": True,
        }
    )
    assert page.specific_users.entries() == ["stored.one", "stored.two"]
    mocker.patch.object(
        TargetEditorDialog, "exec", return_value=TargetEditorDialog.Accepted
    )
    mocker.patch.object(
        TargetEditorDialog, "entries", return_value=["saved.one", "saved.two"]
    )

    page._edit_resource(page.specific_users, "unfollow-from-file")

    assert lists.load("unfollowspecific.txt") == ["saved.one", "saved.two"]
