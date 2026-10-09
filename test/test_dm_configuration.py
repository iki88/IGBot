import pytest
import yaml
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QPushButton

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.specific_lists_service import SpecificListsService
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
        message_directory = directory / "Messages"
        message_directory.mkdir()
        (message_directory / "welcome_dm.txt").write_text(
            messages, encoding="utf-8"
        )
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
    assert "welcome_dm.txt" not in config
    assert filters["pm_to_private_or_empty"] is False
    assert (account.config_path.parent / "Messages" / "welcome_dm.txt").read_text(
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

    assert (account.config_path.parent / "Messages" / "welcome_dm.txt").read_text(
        encoding="utf-8"
    ) == "A new direct message"
    config = yaml.safe_load(account.config_path.read_bytes())
    assert "welcome_dm.txt" not in config


def test_welcome_dm_storage_preserves_utf8_whitespace_and_blank_lines(tmp_path):
    service, account = configuration(tmp_path, messages=None)
    page = DMConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    message = "  Hello 😊\n\nThank you  "
    page.messages.set_text(message)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    path = account.config_path.parent / "Messages" / "welcome_dm.txt"
    assert path.read_bytes() == message.encode("utf-8")
    loaded = service.load_configuration(account.config_path)
    assert loaded["welcome_dm.txt"] == message


def test_dm_validation_rejects_invalid_values_but_allows_empty_messages():
    QApplication.instance() or QApplication([])
    page = DMConfigurationPage()
    page.set_configuration({})
    page.delivery.controls["pm-percentage"].setText("101")
    with pytest.raises(ValueError, match="cannot exceed 100"):
        page.values()

    page.delivery.controls["pm-percentage"].setText("10")
    assert page.values()["pm-percentage"] == "10"


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
            account.config_path.parent / "Messages" / "welcome_dm.txt",
        )
    }
    original_write = service._write_configuration
    failed = False

    def fail_message_write(path, content):
        nonlocal failed
        if path.name == "welcome_dm.txt" and not failed:
            failed = True
            raise OSError("simulated message write failure")
        original_write(path, content)

    monkeypatch.setattr(service, "_write_configuration", fail_message_write)
    with pytest.raises(RuntimeError, match="original files were restored"):
        service.update_configuration(
            account, "account", "secret", "com.instagram.clone", page.values()
        )

    assert all(path.read_bytes() == content for path, content in paths.items())
    assert (
        account.config_path.parent / "Messages" / "welcome_dm.txt"
    ).read_text(encoding="utf-8") != "Replacement"


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
    assert page.delay.minimum_label.text() == "Minimum delay between sent messages"
    assert page.delay.maximum_label.text() == "Maximum delay between sent messages"
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
    page.set_configuration(
        {"welcome_dm.txt": "Hello {friend|there}!\nWelcome 😊"}
    )
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

    assert page.messages.text() == "Updated {friend|there}!\nWelcome 😊"


def test_dm_message_editor_has_no_target_list_actions():
    dialog = DMMessageEditorDialog("Hello {friend|there}!\nWelcome 😊")

    assert dialog.message() == "Hello {friend|there}!\nWelcome 😊"
    assert not any(
        button.text() == "Remove Duplicates"
        for button in dialog.findChildren(QPushButton)
    )


def test_dm_message_editor_opens_blank_and_accepts_empty_message():
    dialog = DMMessageEditorDialog()

    assert dialog.message() == ""
    assert dialog.editor.placeholderText() == "Write the direct message here…"
    assert "private message" not in dialog.editor.toPlainText().casefold()
    assert dialog.counter.text() == "0 / 1000 characters"

    dialog._validate_and_accept()

    assert dialog.result() == DMMessageEditorDialog.Accepted


def test_explicit_empty_message_save_creates_empty_welcome_file(
    tmp_path, mocker
):
    service, account = configuration(tmp_path, messages=None)
    page = DMConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    mocker.patch.object(
        DMMessageEditorDialog, "exec", return_value=DMMessageEditorDialog.Accepted
    )
    mocker.patch.object(DMMessageEditorDialog, "message", return_value="")

    page.edit_messages_button.click()
    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    path = account.config_path.parent / "Messages" / "welcome_dm.txt"
    assert path.is_file()
    assert path.read_bytes() == b""


def test_dm_message_editor_preserves_text_and_enforces_live_character_limit():
    original = "  Hello 😊\n\nThank you  "
    dialog = DMMessageEditorDialog(original)

    assert dialog.message() == original
    assert dialog.counter.text() == f"{len(original)} / 1000 characters"

    dialog.editor.setPlainText("x" * 1001)

    assert dialog.message() == "x" * 1000
    assert dialog.counter.text() == "1000 / 1000 characters"


def test_dm_runtime_extensions_do_not_write_engine_keys():
    page = DMConfigurationPage()
    page.set_configuration(
        {
            "pm-percentage": "1",
            "welcome_dm.txt": "Hello",
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


def test_dm_specific_method_and_account_list_round_trip_independently(tmp_path):
    service, account = configuration(tmp_path)
    lists = SpecificListsService(account.config_path.parent)
    lists.save("dmspecific.txt", ["specific.one", "specific.two"])
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    page.dm_page.specific_accounts.enabled.setChecked(True)
    assert not page.dm_page.new_followers.isChecked()
    values = page.configuration_values()
    assert values["igbot-dm-method"] == "specific-users"

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", values
    )
    loaded = service.load_configuration(account.config_path)
    restored = DMConfigurationPage()
    restored.sources.set_account_directory(account.config_path.parent)
    restored.set_configuration(loaded)

    assert loaded["igbot-dm-method"] == "specific-users"
    assert restored.specific_accounts.enabled.isChecked()
    assert not restored.new_followers.isChecked()
    assert restored.specific_accounts.entries() == ["specific.one", "specific.two"]


def test_dm_action_budget_and_delay_round_trip_as_account_metadata(tmp_path):
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))
    page.dm_page.message_amount.minimum.setValue(3)
    page.dm_page.message_amount.maximum.setValue(7)
    page.dm_page.delay.minimum.setValue(12)
    page.dm_page.delay.maximum.setValue(24)

    service.update_configuration(
        account,
        "account",
        "secret",
        "com.instagram.clone",
        page.configuration_values(),
    )
    loaded = service.load_configuration(account.config_path)

    assert loaded["igbot-dm-budget"] == "3-7"
    assert loaded["igbot-dm-action-delay"] == "12-24"
    restored = DMConfigurationPage()
    restored.set_configuration(loaded)
    assert restored.message_amount.minimum.value() == 3
    assert restored.message_amount.maximum.value() == 7
    assert restored.delay.minimum.value() == 12
    assert restored.delay.maximum.value() == 24


def test_dm_runtime_range_validation():
    page = DMConfigurationPage()
    page.set_configuration({})
    page.message_amount.minimum.setValue(5)
    page.message_amount.maximum.setValue(2)

    with pytest.raises(ValueError, match="Minimum users to message"):
        page.values()
