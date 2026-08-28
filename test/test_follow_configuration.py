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
    assert page.additional_settings.controls["skip_business"].isChecked()
    page.profile_settings.controls["max_followers"].setValue(7500)
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    filters = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert filters["min_followers"] == 100
    assert filters["max_followers"] == 7500
    assert filters["skip_business"] is True


@pytest.mark.parametrize(
    ("key", "entries"),
    (
        ("mandatory_words", ["cat lover", "animal rescue"]),
        ("blacklist_words", ["giveaway", "follow me"]),
        ("specific_alphabet", ["LATIN", "CYRILLIC"]),
        ("biography_language", ["en", "de"]),
        ("biography_banned_language", ["it", "fr"]),
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
    assert blocked.name.text() == "Don't follow if profile contains these words"
    assert required.enabled.objectName() != "configurationSwitch"
    assert blocked.enabled.objectName() != "configurationSwitch"
    assert all(control.isChecked() for control in page.schedule_days.controls.values())

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
        assert row.layout().spacing() == 8


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
