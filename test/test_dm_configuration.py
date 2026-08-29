import pytest
import yaml
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QPushButton

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.dm_configuration_page import DMConfigurationPage
from IGBot.ui.widgets.dm_message_editor_dialog import DMMessageEditorDialog
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
    assert page.dm_page.recipients.isHidden()
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


def test_dm_product_layout_exposes_only_operator_methods_and_ai_placeholder():
    page = DMConfigurationPage()

    assert page.enabled.text() == "Enable DM"
    assert page.new_followers.text() == "Send DMs to New Followers"
    assert page.new_followers.isChecked()
    assert page.specific_accounts.name.text() == "Send DMs to Specific Accounts"
    assert page.new_followers.objectName() != "configurationSwitch"
    assert page.specific_accounts.enabled.objectName() != "configurationSwitch"
    assert page.specific_accounts.name.objectName() == "checkboxLinkButton"
    assert page.sources.rows["blogger-followers"].isHidden()
    assert page.sources.rows["blogger-following"].isHidden()
    assert page.messages_section.title.text() == "Message"
    assert page.edit_messages_button.text() == "Edit DM Message"
    assert page.edit_ai_prompt_button.text() == "Edit AI Prompt"
    assert not page.edit_ai_prompt_button.isEnabled()
    assert page.delivery.controls["pm-percentage"].isHidden()
    assert page.limit_behaviour.isHidden()
    assert page.recipients.isHidden()
    assert page.dm_all_new_followers.text() == "DM All New Followers"
    assert "outside IGBot" in page.dm_all_new_followers.toolTip()
    assert "outside IGBot" in page.dm_all_new_followers_description.text()
    assert page.reply_to_incoming.text() == "Reply to Incoming DM Messages"
    assert page.schedule_section.body.isHidden()
    assert page.delay.minimum_label.text() == "Minimum delay after sending DM"
    assert page.delay.maximum_label.text() == "Maximum delay after sending DM"
    assert (
        page.check_interval.labels["check-new-followers-every"].text()
        == "Check for New Followers Every (minutes)"
    )
    assert page.check_interval.isEnabled()


def test_new_follower_interval_follows_method_state_and_marks_dirty():
    page = DMConfigurationPage()
    changes = []
    page.changed.connect(lambda: changes.append(True))

    page.new_followers.setChecked(False)

    assert not page.check_interval.isEnabled()
    assert changes

    page.new_followers.setChecked(True)
    assert page.check_interval.isEnabled()


def test_dm_message_button_uses_dedicated_single_message_editor(mocker):
    page = DMConfigurationPage()
    page.set_configuration({"pm_list.txt": "Hello {friend|there}!\\nWelcome 😊"})
    mocker.patch.object(
        DMMessageEditorDialog,
        "exec",
        return_value=DMMessageEditorDialog.Accepted,
    )
    mocker.patch.object(
        DMMessageEditorDialog,
        "message",
        return_value="Updated {friend|there}!\nWelcome 😊",
    )

    page.edit_messages_button.click()

    assert page.messages.text() == "Updated {friend|there}!\\nWelcome 😊"


def test_dm_message_editor_has_no_target_list_actions():
    dialog = DMMessageEditorDialog("Hello {friend|there}!\nWelcome 😊")

    assert dialog.message() == "Hello {friend|there}!\nWelcome 😊"
    assert not any(
        button.text() == "Remove Duplicates"
        for button in dialog.findChildren(QPushButton)
    )


def test_dm_runtime_extensions_do_not_write_engine_keys():
    page = DMConfigurationPage()
    page.set_configuration(
        {
            "pm-percentage": "1",
            "pm_list.txt": "Hello",
            "total-pm-limit": "10",
        }
    )
    page.message_amount.minimum.setValue(2)
    page.message_amount.maximum.setValue(5)
    page.delay.minimum.setValue(10)
    page.delay.maximum.setValue(20)
    page.check_interval.controls["check-new-followers-every"].setValue(60)
    page.dm_all_new_followers.setChecked(True)
    page.reply_to_incoming.setChecked(True)
    page.schedule_days.controls["monday"].setChecked(False)

    values = page.values()

    assert values["pm-percentage"] == "1"
    assert values["total-pm-limit"] == "10"
    assert not any(
        fragment in key
        for key in values
        for fragment in ("users-to-message", "delay", "check-new", "reply", "schedule")
    )


def test_dm_runtime_range_validation():
    page = DMConfigurationPage()
    page.set_configuration({})
    page.message_amount.minimum.setValue(5)
    page.message_amount.maximum.setValue(2)

    with pytest.raises(ValueError, match="Minimum users to message"):
        page.values()
