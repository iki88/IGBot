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

    assert page.follow_page.settings.controls["follow-limit"].text() == "3-6"
    assert page.follow_page.additional.controls[
        "end-if-follows-limit-reached"
    ].isChecked()
    assert not page.is_dirty
    assert page.tabs.tabText(2) == "● Follow"

    page.follow_page.settings.controls["follow-limit"].setText("4-8")
    assert page.is_dirty
    page.mark_clean()
    assert not page.is_dirty


def test_follow_configuration_saves_without_changing_unrelated_yaml(tmp_path):
    service, account = _configuration(tmp_path)
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.settings.controls["total-follows-limit"].setText("7-15")
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
        "min_followers: 100\nmax_followers: 5000\nskip_if_private: true\n",
        encoding="utf-8",
    )
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.filter_numbers.controls["min_followers"].value() == 100
    assert page.filter_switches.controls["skip_if_private"].isChecked()
    page.filter_numbers.controls["max_followers"].setValue(7500)
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    filters = yaml.safe_load(filters_path.read_text(encoding="utf-8"))
    assert filters["min_followers"] == 100
    assert filters["max_followers"] == 7500
    assert filters["skip_if_private"] is True


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

    page.filter_editors[key].name.click()
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    assert page.filter_editors[key].entries() == entries
    assert yaml.safe_load(filters_path.read_text(encoding="utf-8"))[key] == entries


def test_internal_skip_following_filter_is_hidden_and_preserved(tmp_path):
    service, account = _configuration(tmp_path)
    filters_path = account.config_path.parent / "filters.yml"
    filters_path.write_text("skip_following: true\n", encoding="utf-8")
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    assert "skip_following" not in page.filter_switches.controls
    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )
    assert (
        yaml.safe_load(filters_path.read_text(encoding="utf-8"))["skip_following"]
        is True
    )


def test_follow_filter_labels_checkbox_style_and_operator_order():
    page = FollowConfigurationPage()

    required = page.filter_editors["mandatory_words"]
    blocked = page.filter_editors["blacklist_words"]
    assert required.name.text() == "Follow only if user contains these words"
    assert blocked.name.text() == "Don't follow if user contains these words"
    assert required.enabled.objectName() != "configurationSwitch"
    assert blocked.enabled.objectName() != "configurationSwitch"

    numeric_layout = page.filter_numbers.layout()
    positions = {
        key: numeric_layout.getItemPosition(numeric_layout.indexOf(control))[:2]
        for key, control in page.filter_numbers.controls.items()
    }
    assert positions["min_followers"][0] == positions["max_followers"][0] == 0
    assert positions["min_followings"][0] == positions["max_followings"][0] == 1
    assert positions["min_posts"][0] == 2

    list_layout = page.filter_lists.layout()
    list_rows = [
        list_layout.getItemPosition(list_layout.indexOf(control))[0]
        for control in page.filter_lists.controls.values()
    ]
    assert list_rows == [0, 1, 2]
    assert list(page.filter_lists.controls) == [
        "specific_alphabet",
        "biography_language",
        "biography_banned_language",
    ]


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
