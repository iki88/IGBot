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
        b'total-follows-limit: "5-10" # retained inline\r\n'
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

    assert page.follow_page.limits.controls["minimum"].value() == 5
    assert not page.is_dirty
    assert page.tabs.tabText(2) == "○ Follow"

    page.follow_page.limits.controls["maximum"].setValue(12)
    assert page.is_dirty
    page.mark_clean()
    assert not page.is_dirty


def test_follow_configuration_saves_without_changing_unrelated_yaml(tmp_path):
    service, account = _configuration(tmp_path)
    page = FollowConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.limits.controls["minimum"].setValue(7)
    page.limits.controls["maximum"].setValue(15)
    page.enabled.setChecked(True)
    page.methods.controls["method-followers"].setChecked(True)

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
