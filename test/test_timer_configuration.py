import pytest
import yaml
from PySide6.QtWidgets import QApplication, QLineEdit

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.timer_configuration_page import TimerConfigurationPage
from InstaAddict.core.config import Config


def _configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# keep timer comments\r\n"
        b'username: "account"\r\n'
        b'password: "secret"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.example.app\r\n"
        b"screen-sleep: true\r\n"
        b"working-hours: [8-12, 16.30-20.05, 20-24] # exact input\r\n"
        b"shuffle-jobs: true\r\n"
        b"igbot-timer-enable-warmup: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.example.app", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_timer_loads_engine_schedule_as_operator_times_and_tracks_dirty_state(
    tmp_path,
):
    QApplication.instance() or QApplication([])
    service, account = _configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.timer_page.start_hours.text() == "8:00,16:30,20:00"
    assert page.timer_page.end_hours.text() == "12:00,20:05,24:00"
    assert not hasattr(page.timer_page, "random_action_order")
    assert not hasattr(page.timer_page, "enable_warmup")
    assert not page.is_dirty

    page.timer_page.start_hours.setText("9,17:30,21")
    assert page.is_dirty


def test_timer_serializes_shorthand_minutes_and_multiple_sessions():
    page = TimerConfigurationPage()
    page.start_hours.setText("10:30,15:15,20")
    page.end_hours.setText("12,17:00,23:30")

    assert page.values() == {
        "working-hours": [
            "10.30-12.00",
            "15.15-17.00",
            "20.00-23.30",
        ]
    }


def test_timer_save_preserves_comments_and_unrelated_engine_values(tmp_path):
    service, account = _configuration(tmp_path)
    page = TimerConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.start_hours.setText("10,15,20")
    page.end_hours.setText("12,17,22")

    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    content = account.config_path.read_bytes()
    configuration = yaml.safe_load(content)
    assert configuration["working-hours"] == [
        "10.00-12.00",
        "15.00-17.00",
        "20.00-22.00",
    ]
    assert configuration["shuffle-jobs"] is True
    assert configuration["screen-sleep"] is True
    assert b"# keep timer comments\r\n" in content
    assert b"# exact input\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in configuration)


def test_saved_configuration_has_no_unknown_engine_arguments(tmp_path, mocker):
    service, account = _configuration(tmp_path)
    page = TimerConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    service.update_configuration(
        account, "account", "ignored-placeholder", "com.example.app", page.values()
    )
    mocker.patch("sys.argv", ["igbot", "--config", str(account.config_path)])

    engine_configuration = Config()

    assert engine_configuration.unknown_args == []


@pytest.mark.parametrize(
    ("start", "end", "message"),
    (
        ("8,invalid", "12,20", "Invalid Start Time"),
        ("10:60", "12", "minutes must be 0–59"),
        ("24:30", "24:00", "24 is only valid as 24:00"),
        ("8,16", "12", "same number of sessions"),
    ),
)
def test_timer_rejects_malformed_schedules(start, end, message):
    page = TimerConfigurationPage()
    page.start_hours.setText(start)
    page.end_hours.setText(end)

    with pytest.raises(ValueError, match=message):
        page.values()


def test_timer_page_contains_only_time_fields():
    page = TimerConfigurationPage()

    assert page.start_hours.placeholderText() == "10 or 10:30,15:15,20"
    assert page.end_hours.placeholderText() == "12 or 12:30,17,23:30"
    assert page.findChildren(QLineEdit) == [page.start_hours, page.end_hours]
