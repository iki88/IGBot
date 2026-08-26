import pytest
import yaml
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.story_configuration_page import StoryConfigurationPage
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
        b'stories-count: "2-3"\r\n'
        b'stories-percentage: "30-40"\r\n'
        b'total-watches-limit: "50" # retained inline\r\n'
        b"end-if-watches-limit-reached: false\r\n"
        b"screen-sleep: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_story_load_status_dirty_state_and_shared_shortcut(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.story_page.session.controls["stories-count"].text() == "2-3"
    assert page.story_page.enabled.isChecked()
    assert page.tabs.tabText(6) == "● Story"
    assert not page.is_dirty
    assert TopToolbar().save_action.shortcut() == QKeySequence.Save

    page.story_page.limits.controls["total-watches-limit"].setText("60")
    assert page.is_dirty


def test_story_save_uses_only_documented_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    page = StoryConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.session.controls["stories-count"].setText("3-4")
    page.session.controls["stories-percentage"].setText("60-70")
    page.limits.controls["total-watches-limit"].setText("75")
    page.limit_behaviour.controls["end-if-watches-limit-reached"].setChecked(True)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["stories-count"] == "3-4"
    assert parsed["stories-percentage"] == "60-70"
    assert parsed["total-watches-limit"] == "75"
    assert parsed["end-if-watches-limit-reached"] is True
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert b"# retained inline\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)


def test_story_enable_switch_uses_engine_story_count(tmp_path):
    service, account = configuration(tmp_path)
    page = StoryConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    page.enabled.setChecked(False)

    assert page.values()["stories-count"] == "0"
    assert page.status.text() == "● Disabled"


def test_story_validation_rejects_ranges_and_percentages():
    QApplication.instance() or QApplication([])
    page = StoryConfigurationPage()
    page.set_configuration({})

    page.session.controls["stories-count"].setText("5-2")
    with pytest.raises(ValueError, match="ascending range"):
        page.values()

    page.session.controls["stories-count"].setText("1")
    page.session.controls["stories-percentage"].setText("101")
    with pytest.raises(ValueError, match="cannot exceed 100"):
        page.values()


def test_empty_story_page_does_not_create_engine_keys():
    page = StoryConfigurationPage()
    page.set_configuration({})

    assert page.values() == {}
