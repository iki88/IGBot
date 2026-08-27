import yaml
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from IGBot.core.device import DeviceRecord
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.account_template_service import AccountTemplateService
from IGBot.services.device_inventory_service import DeviceInventoryService
from IGBot.ui.pages.templates_page import TemplatesPage
from IGBot.ui.widgets.add_account_dialog import AddAccountDialog
from IGBot.ui.widgets.template_editor_dialog import TemplateEditorDialog


def inventory_service(tmp_path):
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    examples = tmp_path / "config-examples"
    examples.mkdir()
    (examples / "config.yml").write_text(
        "# base account configuration\n"
        "username: myusername\n"
        "# device: serial\n"
        "app-id: com.instagram.android\n"
        'working-hours: ["00.00-23.59"]\n'
        'total-follows-limit: "50"\n',
        encoding="utf-8",
    )
    (examples / "filters.yml").write_text(
        "# base filters\ncomment_photos: true\n", encoding="utf-8"
    )
    service = DeviceInventoryService(
        tmp_path / "data" / "devices.json",
        AccountAssignmentService(accounts),
        tmp_path,
    )
    service._save_state(
        {"devices": [{"serial": "phone-a", "phone_name": "T1"}], "deleted": []}
    )
    return service


def test_template_create_rename_and_delete(tmp_path):
    service = AccountTemplateService(tmp_path / "templates")

    created = service.create("Warmup")
    assert created.name == "Warmup"
    assert (created.directory / "config.yml").is_file()
    assert (created.directory / "filters.yml").is_file()

    renamed = service.rename("Warmup", "Mature Account")
    assert renamed.name == "Mature Account"
    assert [item.name for item in service.list_templates()] == ["Mature Account"]

    service.delete("Mature Account")
    assert service.list_templates() == ()


def test_template_rejects_identity_timer_targets_and_resources(tmp_path):
    service = AccountTemplateService(tmp_path / "templates")
    service.create("Safe")

    for key in (
        "username",
        "password",
        "device",
        "app-id",
        "working-hours",
        "blogger-followers",
        "pm_list.txt",
        "comments_list.txt",
    ):
        try:
            service.save("Safe", {key: "forbidden"})
        except ValueError as error:
            assert "account-specific" in str(error)
        else:
            raise AssertionError(f"{key} must not be accepted by templates")


def test_create_account_without_template_keeps_blank_defaults(tmp_path):
    service = inventory_service(tmp_path)

    account = service.add_account("plain_account", "secret", "phone-a")
    config = yaml.safe_load(account.config_path.read_bytes())

    assert config["total-follows-limit"] == "50"
    assert config["working-hours"] == ["00.00-23.59"]
    assert config["app-id"] == ""


def test_create_account_applies_template_once_without_identity_fields(tmp_path):
    service = inventory_service(tmp_path)
    service.template_service.create("High Engagement")
    service.template_service.save(
        "High Engagement",
        {
            "total-follows-limit": "80-100",
            "likes-percentage": "70",
            "stories-count": "2-3",
            "pm_to_private_or_empty": False,
        },
    )

    account = service.add_account(
        "templated_account", "secret", "phone-a", "High Engagement"
    )
    config = yaml.safe_load(account.config_path.read_bytes())
    filters = yaml.safe_load((account.config_path.parent / "filters.yml").read_bytes())

    assert config["username"] == "templated_account"
    assert config["device"] == "phone-a"
    assert config["app-id"] == ""
    assert config["working-hours"] == ["00.00-23.59"]
    assert config["total-follows-limit"] == "80-100"
    assert config["likes-percentage"] == "70"
    assert config["stories-count"] == "2-3"
    assert filters["pm_to_private_or_empty"] is False
    assert not (account.config_path.parent / "pm_list.txt").exists()
    assert not (account.config_path.parent / "comments_list.txt").exists()


def test_later_template_edits_do_not_change_existing_accounts(tmp_path):
    service = inventory_service(tmp_path)
    service.template_service.create("Reusable")
    service.template_service.save("Reusable", {"total-follows-limit": "60"})
    account = service.add_account("existing", "secret", "phone-a", "Reusable")
    original = account.config_path.read_bytes()

    service.template_service.save("Reusable", {"total-follows-limit": "120"})

    assert account.config_path.read_bytes() == original


def test_add_account_dialog_lists_optional_templates():
    QApplication.instance() or QApplication([])
    dialog = AddAccountDialog(DeviceRecord("phone-a", "T1", True), ("Warmup", "Mature"))

    assert [
        dialog.template.itemText(index) for index in range(dialog.template.count())
    ] == [
        "None",
        "Warmup",
        "Mature",
    ]
    dialog.template.setCurrentText("Mature")
    assert dialog.selected_template() == "Mature"


def test_template_editor_hides_account_specific_pages_and_resources():
    QApplication.instance() or QApplication([])
    dialog = TemplateEditorDialog("Reusable", {})

    assert [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())] == [
        "Follow",
        "Unfollow",
        "Like",
        "Story",
        "DM",
        "Comment",
    ]
    assert not dialog.unfollow.files_section.isVisible()
    assert not dialog.like.files_section.isVisible()
    assert not dialog.dm.messages_section.isVisible()
    assert not dialog.comment.comments_section.isVisible()
    assert "working-hours" not in dialog.values()
    assert "total-follows-limit" not in dialog.values()
    assert dialog.tabs.objectName() == "accountTabs"


def test_templates_page_renders_templates_and_exposes_all_actions(tmp_path):
    QApplication.instance() or QApplication([])
    service = AccountTemplateService(tmp_path / "templates")
    template = service.create("Warmup")
    page = TemplatesPage()
    page.set_templates(service.list_templates())

    assert page.list.count() == 1
    assert page.list.item(0).text() == template.name
    assert page.empty.isHidden()

    page.list.setCurrentRow(0)
    assert page.edit.isEnabled()
    assert page.rename.isEnabled()
    assert page.delete.isEnabled()

    edit_spy = QSignalSpy(page.edit_requested)
    rename_spy = QSignalSpy(page.rename_requested)
    delete_spy = QSignalSpy(page.delete_requested)
    page.edit.click()
    page.rename.click()
    page.delete.click()
    assert [list(spy.at(0)) for spy in (edit_spy, rename_spy, delete_spy)] == [
        ["Warmup"],
        ["Warmup"],
        ["Warmup"],
    ]

    activated_spy = QSignalSpy(page.edit_requested)
    page.list.itemActivated.emit(page.list.item(0))
    assert list(activated_spy.at(0)) == ["Warmup"]


def test_templates_page_keeps_selection_after_refresh(tmp_path):
    QApplication.instance() or QApplication([])
    service = AccountTemplateService(tmp_path / "templates")
    service.create("First")
    service.create("Second")
    page = TemplatesPage()
    page.set_templates(service.list_templates())
    page.list.setCurrentRow(1)

    page.set_templates(service.list_templates())

    assert page.selected_name() == "Second"


def test_edit_save_and_reopen_template_configuration(tmp_path):
    QApplication.instance() or QApplication([])
    service = AccountTemplateService(tmp_path / "templates")
    service.create("Persistent")
    editor = TemplateEditorDialog("Persistent", service.load("Persistent"))
    editor.follow.limits.controls["minimum"].setValue(25)
    editor.follow.limits.controls["maximum"].setValue(40)
    editor.like.interaction.controls["likes-percentage"].setText("65")

    service.save("Persistent", editor.values())

    reopened = TemplateEditorDialog("Persistent", service.load("Persistent"))
    assert reopened.follow.limits.controls["minimum"].text() == "25"
    assert reopened.follow.limits.controls["maximum"].text() == "40"
    assert reopened.like.interaction.controls["likes-percentage"].text() == "65"


def test_template_enabled_state_persists_and_is_applied(tmp_path):
    QApplication.instance() or QApplication([])
    service = inventory_service(tmp_path)
    service.template_service.create("Enabled Follow")
    editor = TemplateEditorDialog("Enabled Follow", {})
    editor.follow.enabled.setChecked(True)
    service.template_service.save("Enabled Follow", editor.values())

    reopened = TemplateEditorDialog(
        "Enabled Follow", service.template_service.load("Enabled Follow")
    )
    assert reopened.follow.enabled.isChecked()

    account = service.add_account(
        "enabled_account", "secret", "phone-a", "Enabled Follow"
    )
    assert yaml.safe_load(account.config_path.read_bytes())["follow-percentage"] == "1"


def test_apply_template_to_existing_account_preserves_identity_and_targets(tmp_path):
    service = inventory_service(tmp_path)
    account = service.add_account("existing_account", "secret", "phone-a")
    service._account_assignments._update_yaml_fields(
        account.config_path, {"blogger-followers": ["target.one"]}
    )
    service.template_service.create("Reusable")
    service.template_service.save(
        "Reusable", {"follow-percentage": "1", "total-follows-limit": "20-30"}
    )

    service.template_service.apply("Reusable", account.config_path.parent)

    configuration = yaml.safe_load(account.config_path.read_bytes())
    assert configuration["username"] == "existing_account"
    assert configuration["device"] == "phone-a"
    assert configuration["blogger-followers"] == ["target.one"]
    assert configuration["follow-percentage"] == "1"
    assert configuration["total-follows-limit"] == "20-30"
