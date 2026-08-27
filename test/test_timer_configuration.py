import yaml
from PySide6.QtWidgets import QApplication

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
        b"working-hours: [8-12, 16-20, 20-24] # exact input\r\n"
        b"shuffle-jobs: true\r\n"
        b"igbot-timer-enable-warmup: true\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.example.app", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_timer_loads_exact_schedule_and_tracks_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = _configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.timer_page.start_hours.text() == "8,16,20"
    assert page.timer_page.end_hours.text() == "12,20,24"
    assert page.timer_page.random_action_order.isChecked()
    assert not page.is_dirty

    page.timer_page.start_hours.setText("9, 17,21")
    assert page.is_dirty


def test_timer_save_preserves_exact_input_comments_and_unrelated_values(tmp_path):
    service, account = _configuration(tmp_path)
    page = TimerConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.start_hours.setText("8,16,20")
    page.end_hours.setText("12,20,24")
    page.randomization.controls["minimum-pause"].setValue(3)
    page.randomization.controls["maximum-pause"].setValue(5)

    service.update_configuration(
        account, "account", "secret", "com.example.app", page.values()
    )

    content = account.config_path.read_bytes()
    configuration = yaml.safe_load(content)
    assert configuration["working-hours"] == ["8-12", "16-20", "20-24"]
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


def test_timer_validation_highlights_invalid_schedule():
    QApplication.instance() or QApplication([])
    page = TimerConfigurationPage()
    page.start_hours.setText("8,invalid")
    page.end_hours.setText("12,20")

    try:
        page.values()
    except ValueError as error:
        assert "hours from 0 to 24" in str(error)
    else:
        raise AssertionError("Invalid schedule was accepted")
    assert "EF4444" in page.start_hours.styleSheet()


def test_timer_rejects_reversed_pause_range():
    QApplication.instance() or QApplication([])
    page = TimerConfigurationPage()
    page.randomization.controls["minimum-pause"].setValue(20)
    page.randomization.controls["maximum-pause"].setValue(10)

    try:
        page.values()
    except ValueError as error:
        assert "Minimum Pause" in str(error)
    else:
        raise AssertionError("Reversed pause range was accepted")
