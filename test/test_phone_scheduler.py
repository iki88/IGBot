import logging
import threading
from datetime import datetime

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.core.phone_scheduler import PhoneScheduler
from IGBot.core.session_engine import SessionState


def account(tmp_path, username, window):
    directory = tmp_path / "accounts" / username
    directory.mkdir(parents=True)
    config = directory / "config.yml"
    config.write_text(
        f'username: "{username}"\ndevice: "PHONE"\n'
        f'app-id: "com.instagram.{username}"\nworking-hours: [{window}]\n',
        encoding="utf-8",
    )
    return AssignedAccount(username, "PHONE", f"com.instagram.{username}", config)


def test_schedule_decision_skips_disabled_and_selects_current_account(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    disabled = account(tmp_path, "disabled", "00.00-00.00")
    future = account(tmp_path, "future", "17.30-18.30")
    current = account(tmp_path, "current", "09.00-11.00")
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (disabled, future, current)),
        tmp_path,
        device_validator=lambda _: True,
    )

    decision = scheduler.evaluate(
        (disabled, future, current), datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    )

    assert decision.selected == current
    assert decision.next_session == datetime(2026, 8, 26, 17, 30)  # noqa: DTZ001
    assert "Skipping account disabled (disabled)" in caplog.text
    assert "Skipping account future (next session 17:30)" in caplog.text


def test_scheduler_remains_waiting_until_stopped_when_no_session(tmp_path):
    disabled = account(tmp_path, "disabled", "00.00-00.00")
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (disabled,)),
        tmp_path,
        device_validator=lambda _: True,
        decision_interval=60,
    )
    states = []
    thread = threading.Thread(
        target=scheduler.start, args=(states.append, lambda *_: None)
    )
    thread.start()
    assert _wait_for(lambda: scheduler.state == SessionState.WAITING)

    scheduler.stop(states.append)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert states == [
        SessionState.STARTING,
        SessionState.WAITING,
        SessionState.STOPPING,
        SessionState.STOPPED,
    ]


def test_stop_terminates_active_account_and_phone_scheduler(tmp_path):
    current = account(tmp_path, "current", "09.00-11.00")
    runtime_started = threading.Event()
    runtime_released = threading.Event()

    class Runtime:
        state = SessionState.IDLE

        def __init__(self, *_):
            pass

        def start(self, callback):
            self.state = SessionState.RUNNING
            callback(self.state)
            runtime_started.set()
            runtime_released.wait(timeout=2)
            self.state = SessionState.STOPPED
            callback(self.state)

        def request_stop(self, callback):
            self.state = SessionState.STOPPING
            callback(self.state)
            runtime_released.set()

    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        runtime_factory=Runtime,
        device_validator=lambda _: True,
        clock=lambda: datetime(2026, 8, 26, 10, 0),  # noqa: DTZ001
    )
    states = []
    account_states = []
    thread = threading.Thread(
        target=scheduler.start,
        args=(
            states.append,
            lambda username, state: account_states.append((username, state)),
        ),
    )
    thread.start()
    assert runtime_started.wait(timeout=2)

    scheduler.stop(states.append)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert SessionState.RUNNING in states
    assert states[-2:] == [SessionState.STOPPING, SessionState.STOPPED]
    assert ("current", SessionState.RUNNING) in account_states


def _wait_for(predicate):
    for _ in range(200):
        if predicate():
            return True
        threading.Event().wait(0.005)
    return False
