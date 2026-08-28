import pytest
import yaml
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.dm_configuration_page import DMConfigurationPage
from IGBot.ui.widgets.top_toolbar import TopToolbar


def configuration(tmp_path, messages="Hello {friend|there}!\nWelcome 😊\n"):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    config_path = directory / "config.yml"
    config_path.write_bytes(
        b"# retained config comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'pm-percentage: "20-30"\r\n'
        b'total-pm-limit: "10" # retained inline\r\n'
        b"end-if-pm-limit-reached: false\r\n"
        b"screen-sleep: true\r\n"
    )
    (directory / "filters.yml").write_bytes(
        b"# retained filter comment\r\npm_to_private_or_empty: true\r\n"
    )
    if messages is not None:
        (directory / "pm_list.txt").write_text(messages, encoding="utf-8")
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", config_path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_dm_load_status_dirty_state_and_shared_shortcut(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.dm_page.delivery.controls["pm-percentage"].text() == "20-30"
    assert "Welcome 😊" in page.dm_page.messages.text()
    assert page.dm_page.recipients.controls["pm_to_private_or_empty"].isChecked()
    assert page.tabs.tabText(7) == "DM"
    assert not page.is_dirty
    assert TopToolbar().save_action.shortcut() == QKeySequence.Save

    page.dm_page.messages.editor.appendPlainText("Another message")
    assert page.is_dirty


def test_dm_save_routes_values_to_engine_files(tmp_path):
    service, account = configuration(tmp_path)
    page = DMConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.delivery.controls["pm-percentage"].setText("40-50")
    page.delivery.controls["total-pm-limit"].setText("25")
    page.limit_behaviour.controls["end-if-pm-limit-reached"].setChecked(True)
    page.recipients.controls["pm_to_private_or_empty"].setChecked(False)
    page.messages.set_text("First {message|note}\nSecond 😊\n")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    config_bytes = account.config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    filters_bytes = (account.config_path.parent / "filters.yml").read_bytes()
    filters = yaml.safe_load(filters_bytes)
    assert config["pm-percentage"] == "40-50"
    assert config["total-pm-limit"] == "25"
    assert config["end-if-pm-limit-reached"] is True
    assert "pm_to_private_or_empty" not in config
    assert "pm_list.txt" not in config
    assert filters["pm_to_private_or_empty"] is False
    assert (account.config_path.parent / "pm_list.txt").read_text(
        encoding="utf-8"
    ) == "First {message|note}\nSecond 😊\n"
    assert b"# retained config comment\r\n" in config_bytes
    assert b"# retained inline\r\n" in config_bytes
    assert b"# retained filter comment\r\n" in filters_bytes


def test_dm_generates_message_resource_without_empty_yaml_values(tmp_path):
    service, account = configuration(tmp_path, messages=None)
    page = DMConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.messages.set_text("A new direct message")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    assert (account.config_path.parent / "pm_list.txt").read_text(
        encoding="utf-8"
    ) == "A new direct message"
    config = yaml.safe_load(account.config_path.read_bytes())
    assert "pm_list.txt" not in config


def test_dm_validation_rejects_invalid_values_and_missing_messages():
    QApplication.instance() or QApplication([])
    page = DMConfigurationPage()
    page.set_configuration({})
    page.delivery.controls["pm-percentage"].setText("101")
    with pytest.raises(ValueError, match="cannot exceed 100"):
        page.values()

    page.delivery.controls["pm-percentage"].setText("10")
    with pytest.raises(ValueError, match="at least one direct message"):
        page.values()


def test_empty_disabled_dm_page_does_not_create_engine_values():
    page = DMConfigurationPage()
    page.set_configuration({})

    assert page.values() == {}


def test_dm_resource_failure_restores_every_file(tmp_path, monkeypatch):
    service, account = configuration(tmp_path)
    page = DMConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.delivery.controls["pm-percentage"].setText("60")
    page.recipients.controls["pm_to_private_or_empty"].setChecked(False)
    page.messages.set_text("Replacement")
    paths = {
        path: path.read_bytes()
        for path in (
            account.config_path,
            account.config_path.parent / "filters.yml",
            account.config_path.parent / "pm_list.txt",
        )
    }
    original_write = service._write_configuration
    failed = False

    def fail_message_write(path, content):
        nonlocal failed
        if path.name == "pm_list.txt" and not failed:
            failed = True
            raise OSError("simulated message write failure")
        original_write(path, content)

    monkeypatch.setattr(service, "_write_configuration", fail_message_write)
    with pytest.raises(RuntimeError, match="original files were restored"):
        service.update_configuration(
            account, "account", "secret", "com.instagram.clone", page.values()
        )

    assert all(path.read_bytes() == content for path, content in paths.items())
