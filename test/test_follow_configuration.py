import json
import subprocess

import pytest
import yaml
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.android_package_service import AndroidPackageService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.follow_configuration_page import FollowConfigurationPage
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.top_toolbar import TopToolbar


def _configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# retained comment\r\n"
        b'username: "account"\r\n'
        b'password: "secret"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.example.app\r\n"
        b"screen-sleep: true\r\n"
        b'follow-percentage: "30-40"\r\n'
        b'follow-limit: "3-6"\r\n'
        b'total-follows-limit: "5-10" # retained inline\r\n'
        b"end-if-follows-limit-reached: true\r\n"
        b"igbot-follow-enabled: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.example.app", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_follow_configuration_loads_and_tracks_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = _configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.follow_page.follow_amount.minimum.value() == 3
    assert page.follow_page.follow_amount.maximum.value() == 6
    assert not page.is_dirty
    assert page.tabs.tabText(2) == "Follow"

    page.follow_page.follow_amount.maximum.setValue(8)
    assert page.is_dirty
    page.mark_clean()
    assert not page.is_dirty


def test_follow_configuration_saves_without_changing_unrelated_yaml(tmp_path):
    service, account = _configuration(tmp_path)
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.follow_limit.controls["total-follows-limit"].setText("7-15")
    page.enabled.setChecked(True)
    page.sources.rows["blogger-followers"].set_entries(["source.account"])
    page.sources.rows["blogger-followers"].enabled.setChecked(True)

    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["total-follows-limit"] == "7-15"
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert b"# retained inline\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)


def test_follow_runtime_extensions_persist_as_account_metadata(tmp_path):
    service, account = _configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))
    page.follow_page.mute_after_follow.setChecked(True)
    page.follow_page.only_active_stories.setChecked(True)

    updated = service.update_configuration(
        account,
        "account",
        "secret",
        "com.example.app",
        page.configuration_values(),
    )

    metadata = json.loads(
        (updated.config_path.parent / "account.json").read_text(encoding="utf-8")
    )
    assert metadata["runtime_extensions"]["follow"]["mute_after_follow"] is True
    assert metadata["runtime_extensions"]["follow"]["only_active_stories"] is True
    assert (
        service.load_configuration(updated.config_path)[
            "igbot-follow-mute-after-follow"
        ]
        is True
    )
    assert "igbot-follow-mute-after-follow" not in yaml.safe_load(
        updated.config_path.read_text(encoding="utf-8")
    )
    assert (
        service.load_configuration(updated.config_path)[
            "igbot-follow-only-active-stories"
        ]
        is True
    )


def test_follow_only_save_keeps_selected_engine_identity_when_metadata_is_stale(
    tmp_path,
):
    service, account = _configuration(tmp_path)
    service.metadata.save(
        account.config_path.parent,
        "metadata_account",
        "secret",
        account.device_id,
    )
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))
    page.follow_page.follow_amount.maximum.setValue(8)

    updated = service.update_configuration(
        account,
        page.username.text(),
        page.password.text(),
        page.application_id.text(),
        page.configuration_values(),
        page.tag.text(),
    )

    saved = service.load_configuration(updated.config_path)
    assert updated.username == "account"
    assert saved["follow-limit"] == "3-8"
    assert saved["username"] == "account"
    metadata = json.loads(
        (updated.config_path.parent / "account.json").read_text(encoding="utf-8")
    )
    assert metadata["username"] == "account"


def test_follow_exposes_only_production_methods_and_preserves_hidden_sources(tmp_path):
    service, account = _configuration(tmp_path)
    content = account.config_path.read_bytes() + b'hashtag-posts-top: ["cats"]\r\n'
    account.config_path.write_bytes(content)
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert list(page.sources.rows) == [
        "blogger-followers",
        "blogger-following",
        "blogger",
    ]

    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )
    assert yaml.safe_load(account.config_path.read_bytes())["hashtag-posts-top"] == [
        "cats"
    ]


def test_follow_filters_load_and_save_through_engine_filters_file(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text(
        "min_followers: 100\nmax_followers: 5000\nskip_business: true\n",
        encoding="utf-8",
    )
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.profile_settings.controls["min_followers"].value() == 100
    assert page.followers_filter_enabled.isChecked()
    assert not page.following_filter_enabled.isChecked()
    assert not page.posts_filter_enabled.isChecked()
    assert page.additional_settings.controls["skip_business"].isChecked()
    page.profile_settings.controls["max_followers"].setValue(7500)
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    filters = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert filters["min_followers"] == 100
    assert filters["max_followers"] == 7500
    assert filters["skip_business"] is True


def test_follow_business_filters_are_default_off_and_mutually_exclusive():
    page = FollowConfigurationPage()
    page.set_configuration({})
    skip_business = page.additional_settings.controls["skip_business"]
    only_business = page.additional_settings.controls["follow_only_business"]

    assert not skip_business.isChecked()
    assert not only_business.isChecked()
    keys = tuple(page.additional_settings.controls)
    assert keys.index("follow_only_business") == keys.index("skip_business") + 1

    skip_business.setChecked(True)
    assert skip_business.isChecked()
    assert not only_business.isChecked()

    only_business.setChecked(True)
    assert only_business.isChecked()
    assert not skip_business.isChecked()


def test_follow_only_business_filter_loads_and_saves(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text("follow_only_business: true\n", encoding="utf-8")
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.additional_settings.controls["follow_only_business"].isChecked()
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    saved = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert saved["follow_only_business"] is True


def test_follow_private_filters_are_default_off_and_mutually_exclusive():
    page = FollowConfigurationPage()
    page.set_configuration({})
    follow_private = page.additional_settings.controls["follow_private_or_empty"]
    only_private = page.additional_settings.controls["follow_only_private"]

    assert not follow_private.isChecked()
    assert not only_private.isChecked()
    keys = tuple(page.additional_settings.controls)
    assert (
        keys.index("follow_only_private") == keys.index("follow_private_or_empty") + 1
    )

    follow_private.setChecked(True)
    assert follow_private.isChecked()
    assert not only_private.isChecked()

    only_private.setChecked(True)
    assert only_private.isChecked()
    assert not follow_private.isChecked()


def test_follow_only_private_filter_loads_and_saves(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text("follow_only_private: true\n", encoding="utf-8")
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.additional_settings.controls["follow_only_private"].isChecked()
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    saved = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert saved["follow_only_private"] is True


def test_follow_link_filters_are_default_off_and_mutually_exclusive():
    page = FollowConfigurationPage()
    page.set_configuration({})
    skip_link = page.additional_settings.controls["skip_if_link_in_bio"]
    only_link = page.additional_settings.controls["follow_only_link_in_bio"]

    assert not skip_link.isChecked()
    assert not only_link.isChecked()
    keys = tuple(page.additional_settings.controls)
    assert (
        keys.index("follow_only_link_in_bio") == keys.index("skip_if_link_in_bio") + 1
    )

    skip_link.setChecked(True)
    assert skip_link.isChecked()
    assert not only_link.isChecked()

    only_link.setChecked(True)
    assert only_link.isChecked()
    assert not skip_link.isChecked()


def test_follow_only_link_filter_loads_and_saves(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text("follow_only_link_in_bio: true\n", encoding="utf-8")
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.additional_settings.controls["follow_only_link_in_bio"].isChecked()
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    saved = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert saved["follow_only_link_in_bio"] is True


def test_follow_numeric_filter_toggles_save_values_or_none():
    page = FollowConfigurationPage()
    page.set_configuration({})

    assert not page.followers_filter_enabled.isChecked()
    assert not page.following_filter_enabled.isChecked()
    assert not page.posts_filter_enabled.isChecked()
    assert not page.profile_settings.controls["min_followers"].isEnabled()
    assert not (set(page.values()) & set(page.PROFILE_SETTINGS))

    page.followers_filter_enabled.setChecked(True)
    page.following_filter_enabled.setChecked(True)
    page.posts_filter_enabled.setChecked(True)
    page.profile_settings.controls["min_followers"].setValue(100)
    page.profile_settings.controls["max_followers"].setValue(5000)
    page.profile_settings.controls["min_followings"].setValue(25)
    page.profile_settings.controls["max_followings"].setValue(750)
    page.profile_settings.controls["min_posts"].setValue(3)

    values = page.values()
    assert values["min_followers"] == 100
    assert values["max_followers"] == 5000
    assert values["min_followings"] == 25
    assert values["max_followings"] == 750
    assert values["min_posts"] == 3


def test_follow_numeric_filter_toggles_load_zero_as_enabled_and_null_as_disabled():
    page = FollowConfigurationPage()
    page.set_configuration(
        {
            "min_followers": 0,
            "max_followers": 0,
            "min_followings": None,
            "max_followings": None,
            "min_posts": 0,
        }
    )

    assert page.followers_filter_enabled.isChecked()
    assert not page.following_filter_enabled.isChecked()
    assert page.posts_filter_enabled.isChecked()
    assert page.profile_settings.controls["max_followers"].isEnabled()
    assert not page.profile_settings.controls["max_followings"].isEnabled()


def test_follow_numeric_filters_accept_and_persist_values_in_the_millions(tmp_path):
    service, account = _configuration(tmp_path)
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.followers_filter_enabled.setChecked(True)
    maximum = page.profile_settings.controls["max_followers"]

    maximum.setValue(12_345_678)
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    assert maximum.value() == 12_345_678
    assert maximum.width() == page.follow_amount.maximum.width()
    saved = service.load_configuration(account.config_path)
    assert saved["max_followers"] == 12_345_678


def test_disabling_follow_numeric_filter_removes_saved_bounds(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text(
        "min_followers: 100\nmax_followers: 5000\nmin_posts: 3\n",
        encoding="utf-8",
    )
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    page.followers_filter_enabled.setChecked(False)
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    filters = yaml.safe_load(filters_path.read_text(encoding="utf-8")) or {}
    assert "min_followers" not in filters
    assert "max_followers" not in filters
    assert filters["min_posts"] == 3


@pytest.mark.parametrize(
    ("key", "entries"),
    (
        ("mandatory_words", ["cat lover", "animal rescue"]),
        ("blacklist_words", ["giveaway", "follow me"]),
    ),
)
def test_follow_word_filters_use_shared_popup_and_serialize_as_lists(
    tmp_path, mocker, key, entries
):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text(f"{key}: [existing]\n", encoding="utf-8")
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    mocker.patch.object(
        TargetEditorDialog, "exec", return_value=TargetEditorDialog.Accepted
    )
    mocker.patch.object(TargetEditorDialog, "entries", return_value=entries)

    page.word_filters[key].name.click()
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    assert page.word_filters[key].entries() == entries
    assert yaml.safe_load(filters_path.read_text(encoding="utf-8"))[key] == entries


def test_internal_skip_following_filter_is_hidden_and_preserved(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text("skip_following: true\n", encoding="utf-8")
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert "skip_following" not in page.additional_settings.controls
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )
    assert (
        yaml.safe_load(filters_path.read_text(encoding="utf-8"))["skip_following"]
        is True
    )


def test_follow_product_layout_and_runtime_extensions_are_not_persisted():
    page = FollowConfigurationPage()

    required = page.word_filters["mandatory_words"]
    blocked = page.word_filters["blacklist_words"]
    assert required.name.text() == "Follow only if profile contains these words"
    assert blocked.name.text() == "Don't follow if profile contain these words"
    assert "skip_non_business" not in page.additional_settings.controls
    assert "biography_banned_language" not in page.list_filters
    assert (
        page.additional_settings.controls["follow_private_or_empty"].text()
        == "Follow private profiles"
    )
    assert page.only_active_stories.text() == "Only follow profiles with active stories"
    assert not page.only_active_stories.isChecked()
    assert all(
        row.enabled.objectName() != "configurationSwitch"
        for row in page.sources.rows.values()
    )
    followers_label = page.profile_settings.labels["min_followers"]
    followers_maximum = page.profile_settings.labels["max_followers"]
    following_label = page.profile_settings.labels["min_followings"]
    posts_label = page.profile_settings.labels["min_posts"]
    for widget, expected_row in (
        (page.followers_filter_enabled, 0),
        (followers_label, 1),
        (followers_maximum, 1),
        (page.following_filter_enabled, 2),
        (following_label, 3),
        (page.posts_filter_enabled, 4),
        (posts_label, 5),
    ):
        assert (
            page.profile_grid.getItemPosition(page.profile_grid.indexOf(widget))[0]
            == expected_row
        )
    assert required.enabled.objectName() != "configurationSwitch"
    assert blocked.enabled.objectName() != "configurationSwitch"
    assert all(control.isChecked() for control in page.schedule_days.controls.values())
    assert (
        page.action_grid.getItemPosition(
            page.action_grid.indexOf(page.follow_limit_help)
        )[0]
        == 3
    )
    assert "Daily hard limit" in page.follow_limit_help.text()

    page.delay.minimum.setValue(4)
    page.delay.maximum.setValue(9)
    page.mute_after_follow.setChecked(True)
    page.same_tagged_account.setChecked(True)
    page.schedule_days.controls["monday"].setChecked(False)

    values = page.values()
    assert not any(
        "delay" in key or "mute" in key or "schedule" in key for key in values
    )
    assert not any(
        "tagged" in key or key in page.schedule_days.controls for key in values
    )
    limit = page.follow_limit.controls["total-follows-limit"]
    assert limit.minimumWidth() == limit.maximumWidth() == 180
    assert page.follow_amount.minimum.width() == limit.width()
    assert page.follow_amount.maximum.width() == limit.width()
    assert page.action_grid.getItemPosition(page.action_grid.indexOf(limit))[:2] == (
        2,
        1,
    )
    assert page.action_grid.getItemPosition(
        page.action_grid.indexOf(page.delay.minimum)
    )[:2] == (1, 1)
    for row in page.list_filters.values():
        assert row.name.objectName() == "checkboxLinkButton"
        assert row.layout().spacing() == 0


def test_follow_save_removes_obsolete_filter_fields(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text(
        "skip_non_business: true\n"
        "biography_banned_language: [de]\n"
        "skip_business: false\n",
        encoding="utf-8",
    )
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    saved = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert "skip_non_business" not in saved
    assert "biography_banned_language" not in saved
    assert saved["skip_business"] is False


def test_all_module_tabs_use_consistent_filled_status_indicators():
    page = AccountPage()
    page.set_configuration({})

    for index, name in enumerate(
        ("Follow", "Unfollow", "Like", "Comment", "Story", "DM"), start=2
    ):
        assert page.tabs.tabText(index) == name
        marker = page.tabs.tabIcon(index).pixmap(12, 12).toImage().pixelColor(6, 6)
        assert marker.name().upper() == "#A1A1AA"

    page.follow_page.enabled.setChecked(True)
    assert page.tabs.tabText(2) == "Follow"
    marker = page.tabs.tabIcon(2).pixmap(12, 12).toImage().pixelColor(6, 6)
    assert marker.name().upper() == "#22C55E"


def test_installed_packages_uses_read_only_adb_query(mocker):
    run = mocker.patch("subprocess.run")
    run.return_value = subprocess.CompletedProcess(
        [], 0, "package:com.example.second\npackage:com.example.first\n", ""
    )
    assert AndroidPackageService.installed_packages("phone-a") == (
        "com.example.first",
        "com.example.second",
    )
    run.assert_called_once_with(
        ["adb", "-s", "phone-a", "shell", "pm", "list", "packages"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def test_foreground_package_uses_read_only_adb_query(mocker):
    run = mocker.patch("subprocess.run")
    run.return_value = subprocess.CompletedProcess(
        [],
        0,
        "mCurrentFocus=Window{123 u0 com.instagram.clone/com.instagram.MainActivity}",
        "",
    )

    assert AndroidPackageService.foreground_package("phone-a") == (
        "com.instagram.clone"
    )
    run.assert_called_once_with(
        ["adb", "-s", "phone-a", "shell", "dumpsys", "window", "windows"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )


def test_foreground_package_reports_missing_foreground_application(mocker):
    run = mocker.patch("subprocess.run")
    run.return_value = subprocess.CompletedProcess([], 0, "no focused window", "")

    with pytest.raises(RuntimeError, match="No foreground Android application"):
        AndroidPackageService.foreground_package("phone-a")


def test_foreground_package_falls_back_to_activity_manager(mocker):
    run = mocker.patch("subprocess.run")
    run.side_effect = (
        subprocess.CompletedProcess([], 0, "mCurrentFocus=null", ""),
        subprocess.CompletedProcess(
            [],
            0,
            "mResumedActivity: ActivityRecord{abc u0 com.instagram.clone/.Main}",
            "",
        ),
    )

    assert AndroidPackageService.foreground_package("phone-a") == (
        "com.instagram.clone"
    )


def test_save_action_uses_platform_save_shortcut():
    QApplication.instance() or QApplication([])
    toolbar = TopToolbar()
    assert toolbar.save_action.shortcut() == QKeySequence.Save
