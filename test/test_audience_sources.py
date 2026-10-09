import yaml
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QKeySequence, QTextCursor
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.specific_lists_service import SpecificListsService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.audience_sources_page import AudienceSourcesPage
from IGBot.ui.widgets.configuration_widgets import (
    CollapsibleSection,
    ConfigurationSection,
)
from IGBot.ui.widgets.target_editor_dialog import TargetEditorDialog
from IGBot.ui.widgets.target_source_row import TargetSourceRow
from IGBot.ui.widgets.top_toolbar import TopToolbar


def configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# retained comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'blogger-followers: ["source.one", "source_two"]\r\n'
        b'blogger-following: ["following.source"]\r\n'
        b'blogger: ["specific.user"] # retained inline\r\n'
        b'hashtag-posts-recent: ["cats", "dogs"]\r\n'
        b"screen-sleep: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_audience_sources_load_and_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    sources = page.follow_page.sources
    assert sources.rows["blogger-followers"].entries() == [
        "source.one",
        "source_two",
    ]
    assert sources.rows["blogger-followers"].enabled.isChecked()
    assert "hashtag-posts-recent" not in sources.rows
    assert sources.state_values()["hashtag-posts-recent"] == ["cats", "dogs"]
    assert "Audience Sources" not in [
        page.tabs.tabText(index) for index in range(page.tabs.count())
    ]
    assert not page.is_dirty
    assert TopToolbar().save_action.shortcut() == QKeySequence.Save

    sources.rows["blogger-followers"].enabled.setChecked(False)
    assert page.is_dirty


def test_specific_users_files_are_account_local_and_initialized(tmp_path):
    account_directory = tmp_path / "Accounts" / "account"
    lists = SpecificListsService(account_directory)

    lists.initialize()

    assert {path.name for path in lists.directory.iterdir()} == set(lists.FILENAMES)
    assert all(
        not path.read_text(encoding="utf-8") for path in lists.directory.iterdir()
    )


def test_inventory_initializes_specific_users_files_for_existing_account(tmp_path):
    service, account = configuration(tmp_path)

    service.load_by_device()

    lists = SpecificListsService(account.config_path.parent)
    assert lists.directory.is_dir()
    assert {path.name for path in lists.directory.iterdir()} == set(lists.FILENAMES)


def test_legacy_sources_migrate_once_into_independent_module_files(tmp_path):
    service, account = configuration(tmp_path)

    loaded = service.load_configuration(account.config_path)
    lists = SpecificListsService(account.config_path.parent)

    assert lists.load("follow_sources_followers.txt") == [
        "source.one",
        "source_two",
    ]
    assert lists.load("follow_sources_following.txt") == ["following.source"]
    for filename in (
        "like_sources_followers.txt",
        "story_sources_followers.txt",
        "comment_sources_followers.txt",
    ):
        assert lists.load(filename) == ["source.one", "source_two"]
    assert loaded["igbot-follow-sources-followers"] == [
        "source.one",
        "source_two",
    ]
    assert loaded["igbot-like-sources-followers"] == [
        "source.one",
        "source_two",
    ]

    lists.save("like_sources_followers.txt", ["like.only"])
    service.load_configuration(account.config_path)

    assert lists.load("like_sources_followers.txt") == ["like.only"]
    assert lists.load("follow_sources_followers.txt") == [
        "source.one",
        "source_two",
    ]


def test_account_module_source_editors_are_independent(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    follow = page.follow_page.sources.rows["blogger-followers"]
    follow.set_entries(["follow.only"])
    page.follow_page.sources._changed()

    assert follow.entries() == ["follow.only"]
    assert page.like_page.sources.rows["blogger-followers"].entries() == [
        "source.one",
        "source_two",
    ]
    assert page.story_page.sources.rows["blogger-followers"].entries() == [
        "source.one",
        "source_two",
    ]
    assert page.comment_page.sources.rows["blogger-followers"].entries() == [
        "source.one",
        "source_two",
    ]
    lists = SpecificListsService(account.config_path.parent)
    assert lists.load("follow_sources_followers.txt") == ["follow.only"]
    assert lists.load("like_sources_followers.txt") == [
        "source.one",
        "source_two",
    ]


def test_follow_specific_users_popup_loads_and_saves_account_file(tmp_path, mocker):
    account_directory = tmp_path / "Accounts" / "account"
    account_directory.mkdir(parents=True)
    (account_directory / "config.yml").write_text(
        "username: account\n", encoding="utf-8"
    )
    lists = SpecificListsService(account_directory)
    lists.save("followspecific.txt", ["stored.one", "stored.two"])
    page = AudienceSourcesPage()
    page.set_account_directory(account_directory)
    page.set_configuration({"blogger": ["legacy.config"]})
    mocker.patch.object(
        TargetEditorDialog, "exec", return_value=TargetEditorDialog.Accepted
    )
    entries = mocker.patch.object(
        TargetEditorDialog, "entries", return_value=["saved.one", "saved.two"]
    )

    page._edit_source("blogger")

    assert entries.called
    assert lists.load("followspecific.txt") == ["saved.one", "saved.two"]
    assert page.rows["blogger"].entries() == ["saved.one", "saved.two"]


def test_existing_specific_users_configuration_seeds_empty_account_file(tmp_path):
    account_directory = tmp_path / "Accounts" / "account"
    account_directory.mkdir(parents=True)
    (account_directory / "config.yml").write_text(
        "username: account\n", encoding="utf-8"
    )
    page = AudienceSourcesPage()
    page.set_account_directory(account_directory)

    page.set_configuration({"blogger": ["legacy.one", "legacy.two"]})

    assert SpecificListsService(account_directory).load("followspecific.txt") == [
        "legacy.one",
        "legacy.two",
    ]


def test_account_editor_does_not_create_lists_for_placeholder_path(tmp_path):
    placeholder = tmp_path / "accounts" / "placeholder"
    page = AudienceSourcesPage()

    page.set_account_directory(placeholder)

    assert not placeholder.exists()


def test_account_page_binding_does_not_create_placeholder_account_folder(tmp_path):
    config_path = tmp_path / "accounts" / "placeholder" / "config.yml"
    page = AccountPage()

    page.set_account(
        AssignedAccount("placeholder", "phone-a", "com.instagram.android", config_path)
    )

    assert not config_path.parent.exists()


def test_audience_sources_save_only_documented_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    page = AudienceSourcesPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.rows["blogger-followers"].set_entries(["new.source", "another.source"])
    page.rows["blogger"].enabled.setChecked(False)
    page.rows["place-posts-top"].set_entries(["Sarajevo", "Mostar"])
    page.rows["place-posts-top"].enabled.setChecked(True)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["blogger-followers"] == ["new.source", "another.source"]
    assert "blogger" not in parsed
    assert parsed["place-posts-top"] == ["Sarajevo", "Mostar"]
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)


def test_target_editor_cleans_empty_lines_and_removes_duplicates():
    QApplication.instance() or QApplication([])
    dialog = TargetEditorDialog("Targets", validator=lambda value: " " not in value)
    dialog.editor.setPlainText("first\n\nSECOND\nsecond\n")
    dialog.remove_duplicates()

    assert dialog.entries() == ["first", "SECOND"]
    dialog._validate_and_accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.editor.toPlainText() == "first\nSECOND"


def test_target_editor_supports_copy_paste_and_save_shortcut():
    application = QApplication.instance() or QApplication([])
    dialog = TargetEditorDialog("Targets", ["copy.me"])
    dialog.show()
    dialog.editor.setFocus()
    application.processEvents()
    dialog.editor.selectAll()
    dialog.editor.copy()
    assert application.clipboard().text() == "copy.me"

    dialog.editor.moveCursor(QTextCursor.End)
    pasted = QMimeData()
    pasted.setText("\npasted.target")
    dialog.editor.insertFromMimeData(pasted)
    assert dialog.entries() == ["copy.me", "pasted.target"]
    dialog.save_shortcut.activated.emit()
    assert dialog.result() == QDialog.Accepted


def test_specific_users_editor_matches_plain_ignore_list_editor():
    QApplication.instance() or QApplication([])
    dialog = TargetEditorDialog(
        "Follow Specific Users",
        [" First.User ", "first.user", "SECOND"],
        specific_users=True,
    )

    assert dialog.count.text() == "2 accounts"
    assert dialog.guidance.text() == (
        "One username per line.\n"
        "Usernames are automatically normalized to lowercase, trimmed, and "
        "deduplicated when saving."
    )
    assert [
        button.text()
        for button in dialog.findChildren(QPushButton)
        if button.isVisibleTo(dialog)
    ] == ["Cancel", "Save"]

    dialog.editor.setPlainText(" New.User \nnew.user\n Another_User\n\n")
    dialog._validate_and_accept()

    assert dialog.result() == QDialog.Accepted
    assert dialog.editor.toPlainText() == "new.user\nanother_user"


def test_audience_source_validation_rejects_enabled_empty_source():
    account_page = AccountPage()
    page = account_page.follow_page.sources
    page.set_configuration({})
    page.rows["blogger-followers"].enabled.setChecked(True)

    try:
        page.values()
    except ValueError as error:
        assert "at least one target" in str(error)
    else:
        raise AssertionError("An enabled empty source must be rejected.")


def test_account_save_ignores_disabled_like_provider_requirements():
    page = AccountPage()
    page.set_configuration({})
    page.follow_page.enabled.setChecked(True)
    page.follow_page.sources.rows["blogger-followers"].set_entries(["follow.source"])
    page.follow_page.sources.rows["blogger-followers"].enabled.setChecked(True)
    page.like_page.enabled.setChecked(False)
    page.like_page.sources.rows["blogger-followers"].enabled.setChecked(True)

    values = page.configuration_values()

    assert values["follow-percentage"] != "0"
    assert values.get("likes-percentage", "0") == "0"


def test_enabled_like_without_source_provider_does_not_require_targets():
    page = AccountPage()
    page.set_configuration({})
    page.like_page.enabled.setChecked(True)

    values = page.configuration_values()

    assert values["likes-percentage"] != "0"
    assert values["igbot-like-methods"] == []


def test_enabled_like_source_followers_requires_its_own_targets():
    page = AccountPage()
    page.set_configuration({})
    page.like_page.enabled.setChecked(True)
    page.like_page.sources.rows["blogger-followers"].enabled.setChecked(True)

    try:
        page.configuration_values()
    except ValueError as error:
        assert str(error) == "Add at least one target for Like Source Followers."
    else:
        raise AssertionError("An enabled Like source must require Like targets.")


def test_enabled_follow_source_followers_requires_only_follow_targets():
    page = AccountPage()
    page.set_configuration({})
    page.follow_page.enabled.setChecked(True)
    page.follow_page.sources.rows["blogger-followers"].enabled.setChecked(True)
    page.like_page.sources.rows["blogger-followers"].set_entries(["like.source"])
    page.like_page.sources.rows["blogger-followers"].enabled.setChecked(True)

    try:
        page.configuration_values()
    except ValueError as error:
        assert str(error) == "Add at least one target for Follow User's Followers."
    else:
        raise AssertionError("An enabled Follow source must require Follow targets.")


def test_disabled_unfollow_specific_provider_does_not_require_targets():
    page = AccountPage()
    page.set_configuration({})
    page.unfollow_page.specific_users.enabled.setChecked(True)
    page.unfollow_page.enabled.setChecked(False)

    page.configuration_values()


def test_enabled_dm_specific_provider_requires_targets():
    page = AccountPage()
    page.set_configuration({})
    page.dm_page.enabled.setChecked(True)
    page.dm_page.specific_accounts.enabled.setChecked(True)

    try:
        page.configuration_values()
    except ValueError as error:
        assert str(error) == "Add at least one target for Send DMs to Specific Accounts."
    else:
        raise AssertionError("An enabled Specific DM provider must require targets.")


def test_module_source_label_launches_shared_target_editor_request():
    source = TargetSourceRow("Follow User's Followers")
    requested = QSignalSpy(source.edit_requested)

    source.name.click()

    assert requested.count() == 1


def test_module_sources_are_methods_without_duplicate_sources_heading():
    page = AccountPage()
    headings = [
        section.title.text()
        for section in page.follow_page.sources.findChildren(ConfigurationSection)
    ]
    assert headings == ["Follow Method"]
    assert "Sources" not in headings


def test_interaction_modules_share_static_continuous_section_order():
    page = AccountPage()
    expected = {
        page.follow_page: [
            "Enable Follow",
            "Follow Method",
            "Follow Actions",
            "Follow Settings",
            "Additional Follow Settings",
            "Schedule",
        ],
        page.unfollow_page: [
            "Enable Unfollow",
            "Unfollow Method",
            "Unfollow Actions",
            "Unfollow Timing",
            "Additional Unfollow Settings",
            "Schedule",
        ],
        page.like_page: [
            "Enable Like",
            "Like Method",
            "Like Actions",
            "Additional Settings",
            "Filters",
            "Schedule",
        ],
        page.story_page: [
            "Enable / Disable",
            "Method",
            "Settings",
            "Additional Settings",
        ],
        page.dm_page: [
            "Enable DM",
            "DM Method",
            "Message",
            "DM Actions",
            "Additional Settings",
            "Schedule",
        ],
        page.comment_page: [
            "Enable / Disable",
            "Method",
            "Settings",
            "Additional Settings",
            "Filters",
        ],
    }

    for module, expected_headings in expected.items():
        headings = []
        layout = module.widget().layout()
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if isinstance(widget, ConfigurationSection):
                headings.append(widget.title.text())
            elif isinstance(widget, AudienceSourcesPage) and widget.isVisibleTo(
                module.widget()
            ):
                method = widget.findChild(ConfigurationSection)
                headings.append(method.title.text())
            elif isinstance(widget, CollapsibleSection):
                headings.append(widget.toggle.text())
        assert headings == expected_headings
        collapsible = module.findChildren(CollapsibleSection)
        expected_collapsible = {
            page.follow_page: [page.follow_page.schedule_section],
            page.unfollow_page: [page.unfollow_page.schedule_section],
            page.like_page: [page.like_page.schedule_section],
            page.dm_page: [page.dm_page.schedule_section],
        }.get(module, [])
        assert collapsible == expected_collapsible


def test_configuration_sections_are_permanently_expanded():
    section = CollapsibleSection("Limits")
    assert not section.toggle.isCheckable()
    assert section.body.isVisibleTo(section)


def test_follow_schedule_is_collapsed_and_weekdays_are_vertical():
    account_page = AccountPage()
    page = account_page.follow_page

    assert page.schedule_section.toggle.isCheckable()
    assert not page.schedule_section.toggle.isChecked()
    assert page.schedule_section.body.isHidden()
    layout = page.schedule_days.layout()
    positions = [
        layout.getItemPosition(layout.indexOf(control))[:2]
        for control in page.schedule_days.controls.values()
    ]
    assert positions == [(index, 0) for index in range(7)]
