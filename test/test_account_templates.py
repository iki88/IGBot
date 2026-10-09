import yaml
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from IGBot.core.device import DeviceRecord
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.account_template_service import AccountTemplateService
from IGBot.services.device_inventory_service import DeviceInventoryService
from IGBot.services.specific_lists_service import SpecificListsService
from IGBot.ui.pages.follow_configuration_page import FollowConfigurationPage
from IGBot.ui.pages.like_configuration_page import LikeConfigurationPage
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
    assert not dialog.follow.sources.isHidden()
    assert not dialog.unfollow.search_method.isHidden()
    assert not dialog.unfollow.following_list_search_method.isHidden()
    assert not dialog.unfollow.specific_users.isHidden()
    assert not dialog.unfollow.all_followings_method.isHidden()
    assert not dialog.like.sources.isHidden()
    assert not dialog.dm.sources.isHidden()
    assert "working-hours" not in dialog.values()
    assert "total-follows-limit" not in dialog.values()
    assert dialog.tabs.objectName() == "accountTabs"


def test_template_method_choices_save_and_reload_without_target_lists(tmp_path):
    QApplication.instance() or QApplication([])
    service = AccountTemplateService(tmp_path / "templates")
    service.create("Methods")
    editor = TemplateEditorDialog("Methods", {})
    editor.follow.sources.rows["blogger-followers"].enabled.setChecked(True)
    editor.follow.sources.rows["blogger"].enabled.setChecked(True)
    editor.unfollow.following_list_search_method.setChecked(True)
    editor.like.sources.rows["blogger-followers"].enabled.setChecked(True)
    editor.dm.specific_accounts.enabled.setChecked(True)

    service.save("Methods", editor.values())
    stored = service.load("Methods")

    assert stored["igbot-template-follow-methods"] == [
        "blogger-followers",
        "blogger",
    ]
    assert stored["igbot-template-like-methods"] == ["blogger-followers"]
    assert stored["igbot-unfollow-method"] == "following-list-search"
    assert stored["igbot-dm-method"] == "specific-users"
    assert not ({"blogger-followers", "blogger-following", "blogger"} & stored.keys())
    reopened = TemplateEditorDialog("Methods", stored)
    assert reopened.follow.sources.rows["blogger-followers"].enabled.isChecked()
    assert reopened.follow.sources.rows["blogger"].enabled.isChecked()
    assert reopened.unfollow.following_list_search_method.isChecked()
    assert reopened.like.sources.rows["blogger-followers"].enabled.isChecked()
    assert reopened.dm.specific_accounts.enabled.isChecked()


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
    editor.follow.follow_limit.controls["total-follows-limit"].setText("25-40")
    editor.like.interaction.controls["likes-percentage"].setText("65")

    service.save("Persistent", editor.values())

    reopened = TemplateEditorDialog("Persistent", service.load("Persistent"))
    assert (
        reopened.follow.follow_limit.controls["total-follows-limit"].text() == "25-40"
    )
    assert reopened.like.interaction.controls["likes-percentage"].text() == "65"


def test_template_persists_and_applies_all_account_runtime_extensions(tmp_path):
    QApplication.instance() or QApplication([])
    service = inventory_service(tmp_path)
    service.template_service.create("Complete Behavior")
    editor = TemplateEditorDialog("Complete Behavior", {})

    editor.follow.mute_after_follow.setChecked(True)
    editor.follow.only_active_stories.setChecked(True)
    editor.follow.automatic_daily_increment.enabled.setChecked(True)
    editor.follow.automatic_daily_increment.increment.setText("5")
    editor.follow.automatic_daily_increment.maximum.setText("80-90")

    editor.unfollow.enabled.setChecked(True)
    editor.unfollow.following_list_search_method.setChecked(True)
    editor.unfollow.sort_earliest.setChecked(True)
    editor.unfollow.unfollow_amount.minimum.setValue(3)
    editor.unfollow.unfollow_amount.maximum.setValue(6)
    editor.unfollow.unfollow_action_delay.minimum.setValue(4)
    editor.unfollow.unfollow_action_delay.maximum.setValue(7)
    editor.unfollow.automatic_daily_increment.enabled.setChecked(True)
    editor.unfollow.automatic_daily_increment.increment.setText("2")
    editor.unfollow.automatic_daily_increment.maximum.setText("30")

    editor.like.user_amount.minimum.setValue(2)
    editor.like.user_amount.maximum.setValue(4)
    editor.like.delay.minimum.setValue(8)
    editor.like.delay.maximum.setValue(12)
    editor.like.automatic_daily_increment.enabled.setChecked(True)
    editor.like.automatic_daily_increment.increment.setText("3")
    editor.like.automatic_daily_increment.maximum.setText("40-50")

    editor.dm.message_amount.minimum.setValue(5)
    editor.dm.message_amount.maximum.setValue(9)
    editor.dm.delay.minimum.setValue(10)
    editor.dm.delay.maximum.setValue(15)

    service.template_service.save("Complete Behavior", editor.values())
    stored = service.template_service.load("Complete Behavior")

    assert stored["igbot-follow-auto-increment-enabled"] is True
    assert stored["igbot-follow-auto-increment-by"] == "5"
    assert stored["igbot-follow-auto-increment-maximum"] == "80-90"
    assert stored["igbot-unfollow-enabled"] is True
    assert stored["igbot-unfollow-method"] == "following-list-search"
    assert stored["igbot-unfollow-sort"] == "earliest"
    assert stored["igbot-unfollow-budget"] == "3-6"
    assert stored["igbot-unfollow-action-delay"] == "4-7"
    assert stored["igbot-like-budget"] == "2-4"
    assert stored["igbot-like-action-delay"] == "8-12"
    assert stored["igbot-dm-budget"] == "5-9"
    assert stored["igbot-dm-action-delay"] == "10-15"

    reopened = TemplateEditorDialog("Complete Behavior", stored)
    assert reopened.follow.automatic_daily_increment.enabled.isChecked()
    assert reopened.unfollow.enabled.isChecked()
    assert reopened.unfollow.sort_earliest.isChecked()
    assert reopened.unfollow.unfollow_amount.value() == "3-6"
    assert reopened.like.user_amount.value() == "2-4"
    assert reopened.dm.message_amount.value() == "5-9"

    account = service.add_account("complete_account", "secret", "phone-a")
    service.template_service.apply("Complete Behavior", account.config_path.parent)
    applied = service._account_assignments.load_configuration(account.config_path)

    for key in (
        "igbot-follow-mute-after-follow",
        "igbot-follow-only-active-stories",
        "igbot-follow-auto-increment-enabled",
        "igbot-unfollow-enabled",
        "igbot-unfollow-auto-increment-enabled",
        "igbot-like-auto-increment-enabled",
    ):
        assert applied[key] is True
    assert applied["igbot-follow-auto-increment-by"] == "5"
    assert applied["igbot-follow-auto-increment-maximum"] == "80-90"
    assert applied["igbot-unfollow-method"] == "following-list-search"
    assert applied["igbot-unfollow-sort"] == "earliest"
    assert applied["igbot-unfollow-budget"] == "3-6"
    assert applied["igbot-unfollow-action-delay"] == "4-7"
    assert applied["igbot-unfollow-auto-increment-by"] == "2"
    assert applied["igbot-unfollow-auto-increment-maximum"] == "30"
    assert applied["igbot-like-budget"] == "2-4"
    assert applied["igbot-like-action-delay"] == "8-12"
    assert applied["igbot-like-auto-increment-by"] == "3"
    assert applied["igbot-like-auto-increment-maximum"] == "40-50"
    assert applied["igbot-dm-budget"] == "5-9"
    assert applied["igbot-dm-action-delay"] == "10-15"


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
    service._account_assignments.metadata.save(
        account.config_path.parent,
        account.username,
        "secret",
        account.device_id,
        tag="account-specific",
    )
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
    assert (
        service._account_assignments.metadata.load(account.config_path.parent)["tag"]
        == "account-specific"
    )


def test_apply_template_preserves_module_source_files(tmp_path):
    service = inventory_service(tmp_path)
    account = service.add_account("source_account", "secret", "phone-a")
    lists = SpecificListsService(account.config_path.parent)
    expected = {
        "follow_sources_followers.txt": ["follow.source"],
        "follow_sources_following.txt": ["following.source"],
        "like_sources_followers.txt": ["like.source"],
        "story_sources_followers.txt": ["story.source"],
        "comment_sources_followers.txt": ["comment.source"],
    }
    for filename, usernames in expected.items():
        lists.save(filename, usernames)
    service.template_service.create("Behavior Only")
    service.template_service.save(
        "Behavior Only",
        {
            "igbot-template-follow-methods": ["blogger-followers"],
            "igbot-template-like-methods": ["blogger-followers"],
            "follow-percentage": "1",
            "likes-percentage": "1",
        },
    )

    service.template_service.apply("Behavior Only", account.config_path.parent)

    assert {
        filename: lists.load(filename) for filename in expected
    } == expected


def test_apply_template_transfers_methods_without_copying_targets(tmp_path):
    service = inventory_service(tmp_path)
    account = service.add_account("method_account", "secret", "phone-a")
    service._account_assignments._update_yaml_fields(
        account.config_path,
        {
            "blogger-followers": ["owned.followers.source"],
            "blogger-following": ["owned.following.source"],
        },
    )
    service.template_service.create("Methods")
    service.template_service.save(
        "Methods",
        {
            "igbot-template-follow-methods": ["blogger-followers"],
            "igbot-template-like-methods": ["blogger-followers"],
            "igbot-unfollow-method": "all-followings",
            "igbot-dm-method": "specific-users",
        },
    )

    service.template_service.apply("Methods", account.config_path.parent)

    configuration = yaml.safe_load(account.config_path.read_bytes())
    assert configuration["blogger-followers"] == ["owned.followers.source"]
    assert "blogger-following" not in configuration
    assert "igbot-template-follow-methods" not in configuration
    assert "igbot-template-like-methods" not in configuration
    metadata = service._account_assignments.metadata.load(account.config_path.parent)
    assert metadata["runtime_extensions"]["unfollow"]["method"] == "all-followings"
    assert metadata["runtime_extensions"]["dm"]["method"] == "specific-users"


def test_template_apply_replaces_complete_mixed_behavior_snapshot(tmp_path):
    QApplication.instance() or QApplication([])
    service = inventory_service(tmp_path)
    service.template_service.create("Mixed Behavior")
    editor = TemplateEditorDialog("Mixed Behavior", {})

    editor.follow.enabled.setChecked(True)
    editor.follow.additional_settings.controls["skip_business"].setChecked(True)
    editor.follow.additional_settings.controls["follow_only_business"].setChecked(
        False
    )

    for key, entries, enabled in (
        ("mandatory_words", ["should-not-enable"], False),
        ("blacklist_words", ["also-disabled"], False),
        ("specific_alphabet", ["latin"], True),
        ("biography_language", [], False),
    ):
        row = editor.like.word_filters[key]
        row.set_entries(entries)
        row.enabled.setChecked(True)
        row.enabled.setChecked(enabled)

    editor.like.post_filter.controls["min_posts"].setValue(6)
    editor.like.post_filter_enabled.setChecked(True)
    editor.like.followers_filter.controls["min_followers"].setValue(500)
    editor.like.followers_filter.controls["max_followers"].setValue(5000)
    editor.like.followers_filter_enabled.setChecked(True)
    editor.like.followers_filter_enabled.setChecked(False)
    editor.like.filters.controls["min_likers"].setValue(25)
    editor.like.filters.controls["max_likers"].setValue(250)
    editor.like.likes_filter_enabled.setChecked(True)
    editor.like.likes_filter_enabled.setChecked(False)

    editor.unfollow.enabled.setChecked(True)
    editor.unfollow.search_method.setChecked(True)
    editor.unfollow.mode_options.controls["unfollow-non-followers"].setChecked(True)
    editor.dm.enabled.setChecked(True)
    editor.dm.message_amount.minimum.setValue(2)
    editor.dm.message_amount.maximum.setValue(5)

    service.template_service.save("Mixed Behavior", editor.values())
    stored = service.template_service.load("Mixed Behavior")

    assert stored["specific_alphabet"] == ["latin"]
    assert stored["mandatory_words"] is None
    assert stored["blacklist_words"] is None
    assert stored["min_posts"] == 6
    assert stored["min_followers"] is None
    assert stored["max_followers"] is None
    assert stored["min_likers"] is None
    assert stored["max_likers"] is None

    reopened = TemplateEditorDialog("Mixed Behavior", stored)
    assert reopened.like.word_filters["specific_alphabet"].enabled.isChecked()
    assert not reopened.like.word_filters["mandatory_words"].enabled.isChecked()
    assert not reopened.like.word_filters["blacklist_words"].enabled.isChecked()
    assert reopened.like.post_filter_enabled.isChecked()
    assert not reopened.like.followers_filter_enabled.isChecked()
    assert not reopened.like.likes_filter_enabled.isChecked()

    account = service.add_account("mixed_account", "secret", "phone-a")
    service._account_assignments._update_yaml_fields(
        account.config_path,
        {
            "end-if-likes-limit-reached": True,
            "delete-interacted-users": True,
        },
    )
    service._account_assignments._update_yaml_fields(
        account.config_path.parent / "filters.yml",
        {
            "mandatory_words": ["stale-required"],
            "blacklist_words": ["stale-blocked"],
            "min_followers": 999,
            "max_followers": 1000,
            "min_likers": 10,
            "max_likers": 20,
        },
    )

    service.template_service.apply("Mixed Behavior", account.config_path.parent)
    applied = service._account_assignments.load_configuration(account.config_path)

    for key in service.template_service.FILTER_KEYS:
        assert applied.get(key) == stored.get(key), key
    comparable_config_keys = (
        service.template_service.CONFIG_KEYS
        - service.template_service.METHOD_CONFIG_KEYS
    )
    for key in comparable_config_keys:
        assert applied.get(key) == stored.get(key), key


def test_add_account_template_matches_manual_template_application(tmp_path):
    QApplication.instance() or QApplication([])
    service = inventory_service(tmp_path)
    service.template_service.create("Add Workflow")
    editor = TemplateEditorDialog("Add Workflow", {})
    editor.follow.sources.rows["blogger-followers"].enabled.setChecked(True)
    editor.like.sources.rows["blogger-followers"].enabled.setChecked(True)
    editor.unfollow.enabled.setChecked(True)
    editor.unfollow.following_list_search_method.setChecked(True)
    editor.dm.enabled.setChecked(True)
    editor.dm.specific_accounts.enabled.setChecked(True)
    editor.follow.additional_settings.controls["skip_business"].setChecked(True)
    editor.follow.automatic_daily_increment.enabled.setChecked(True)
    editor.follow.automatic_daily_increment.increment.setText("3")
    editor.follow.automatic_daily_increment.maximum.setText("50-60")
    editor.like.word_filters["specific_alphabet"].set_entries(["latin"])
    editor.like.word_filters["specific_alphabet"].enabled.setChecked(True)
    service.template_service.save("Add Workflow", editor.values())

    during_add = service.add_account(
        "template_during_add", "secret", "phone-a", "Add Workflow"
    )
    manual = service.add_account("template_after_add", "secret", "phone-a")
    service.template_service.apply("Add Workflow", manual.config_path.parent)

    during_configuration = service.account_configuration(during_add)
    manual_configuration = service.account_configuration(manual)
    behavioral_keys = (
        service.template_service.CONFIG_KEYS
        | service.template_service.FILTER_KEYS
        | {"igbot-follow-methods", "igbot-like-methods"}
    )
    assert {
        key: during_configuration.get(key) for key in behavioral_keys
    } == {key: manual_configuration.get(key) for key in behavioral_keys}
    assert during_configuration["igbot-follow-methods"] == ["blogger-followers"]
    assert during_configuration["igbot-like-methods"] == ["blogger-followers"]
    follow_page = FollowConfigurationPage()
    follow_page.set_configuration(during_configuration)
    like_page = LikeConfigurationPage()
    like_page.set_configuration(during_configuration)
    assert follow_page.sources.rows["blogger-followers"].enabled.isChecked()
    assert like_page.sources.rows["blogger-followers"].enabled.isChecked()

    during_metadata = service._account_assignments.metadata.load(
        during_add.config_path.parent
    )
    manual_metadata = service._account_assignments.metadata.load(
        manual.config_path.parent
    )
    assert during_metadata["runtime_extensions"] == manual_metadata[
        "runtime_extensions"
    ]
