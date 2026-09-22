import json
import logging
import threading
from datetime import datetime, timezone

import pytest

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.core.phone_scheduler import PhoneScheduler, RuntimeMode
from IGBot.core.session_engine import SessionState
from IGBot.runtime.database import FollowRecord, RuntimeDatabase


def account(tmp_path, username, window):
    directory = tmp_path / "accounts" / username
    directory.mkdir(parents=True)
    config = directory / "config.yml"
    config.write_text(
        f'username: "{username}"\ndevice: "PHONE"\n'
        f'app-id: "com.instagram.{username}"\n'
        f'working-hours: [{window}]\nfollow-percentage: "100"\n'
        'blogger-followers: ["source"]\n',
        encoding="utf-8",
    )
    (directory / "account.json").write_text(
        json.dumps(
            {
                "username": username,
                "password": "secret",
                "assigned_device_id": "PHONE",
            }
        ),
        encoding="utf-8",
    )
    (directory / "sessions.json").write_text("[]\n", encoding="utf-8")
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


def test_schedule_decision_excludes_account_without_application_id(tmp_path, caplog):
    invalid = account(tmp_path, "invalid", "09.00-11.00")
    invalid = AssignedAccount(
        invalid.username, invalid.device_id, "", invalid.config_path
    )
    valid = account(tmp_path, "valid", "09.00-11.00")
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (invalid, valid)),
        tmp_path,
        device_validator=lambda _: True,
    )

    with caplog.at_level(logging.INFO):
        decision = scheduler.evaluate(
            (invalid, valid), datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
        )

    assert decision.selected == valid
    assert (
        "invalid (not runtime-ready: no valid Application ID configured)" in caplog.text
    )


@pytest.mark.parametrize(
    "provider",
    ("blogger-followers", "blogger-following", "blogger"),
)
def test_native_readiness_accepts_every_supported_follow_provider(tmp_path, provider):
    current = account(tmp_path, provider.replace("-", "_"), "09.00-11.00")
    configuration = current.config_path.read_text(encoding="utf-8")
    configuration = configuration.replace(
        'blogger-followers: ["source"]', f'{provider}: ["source"]'
    )
    current.config_path.write_text(configuration, encoding="utf-8")
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
    )

    decision = scheduler.evaluate(
        (current,), datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    )

    assert decision.selected == current


def test_native_readiness_rejects_follow_without_a_configured_provider(tmp_path):
    current = account(tmp_path, "missing_provider", "09.00-11.00")
    configuration = current.config_path.read_text(encoding="utf-8")
    current.config_path.write_text(
        configuration.replace('blogger-followers: ["source"]\n', ""),
        encoding="utf-8",
    )
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
    )

    decision = scheduler.evaluate(
        (current,), datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    )

    assert decision.selected is None


def test_schedule_decision_excludes_account_without_onboarding_evidence(
    tmp_path, caplog
):
    testing_only = account(tmp_path, "testing_only", "09.00-11.00")
    (testing_only.config_path.parent / "sessions.json").unlink()
    ready = account(tmp_path, "ready", "09.00-11.00")
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (testing_only, ready)),
        tmp_path,
        device_validator=lambda _: True,
    )

    with caplog.at_level(logging.INFO):
        decision = scheduler.evaluate(
            (testing_only, ready), datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
        )

    assert decision.selected == ready
    assert "no completed onboarding/session history is available" in caplog.text


def test_active_account_is_deferred_without_future_session_message(tmp_path, caplog):
    first = account(tmp_path, "first", "22.00-23.00")
    second = account(tmp_path, "second", "22.00-23.00")
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (first, second)),
        tmp_path,
        device_validator=lambda _: True,
    )

    with caplog.at_level(logging.INFO):
        decision = scheduler.evaluate(
            (first, second), datetime(2026, 8, 26, 22, 5)  # noqa: DTZ001
        )

    assert decision.selected == first
    assert decision.next_session == datetime(2026, 8, 26, 22, 5)  # noqa: DTZ001
    assert "Deferring eligible account second" in caplog.text
    assert "second (next session 22:05)" not in caplog.text


def test_failed_account_does_not_cascade_within_scheduling_cycle(tmp_path):
    first = account(tmp_path, "first", "09.00-11.00")
    second = account(tmp_path, "second", "09.00-11.00")
    attempts = []
    failed = threading.Event()

    class FailingRuntime:
        state = SessionState.IDLE

        def __init__(self, selected, _workspace):
            attempts.append(selected.username)

        def start(self, _callback):
            failed.set()
            raise RuntimeError("failed")

        def request_stop(self, _callback):
            pass

    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (first, second)),
        tmp_path,
        runtime_factory=FailingRuntime,
        device_validator=lambda _: True,
        clock=lambda: datetime(2026, 8, 26, 10, 0),  # noqa: DTZ001
        decision_interval=60,
    )
    states = []
    thread = threading.Thread(
        target=scheduler.start, args=(states.append, lambda *_: None)
    )

    thread.start()
    assert failed.wait(timeout=2)
    assert _wait_for(lambda: scheduler.state is SessionState.WAITING)
    assert attempts == ["first"]
    scheduler.stop(states.append)
    thread.join(timeout=2)

    assert attempts == ["first"]


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


def test_daily_limit_increase_wakes_completed_active_account(tmp_path):
    current = account(tmp_path, "current", "09.00-11.00")
    configuration = current.config_path.read_text(encoding="utf-8")
    current.config_path.write_text(
        configuration + 'total-follows-limit: "2"\n', encoding="utf-8"
    )
    persisted_at = datetime.now(timezone.utc)
    with RuntimeDatabase(current.config_path.parent) as database:
        for username in ("first", "second"):
            user = database.users.create(username, persisted_at, "FOLLOW")
            database.follow.save(
                FollowRecord(
                    user.id,
                    user.username,
                    source="source",
                    follow_date=persisted_at.isoformat(),
                )
            )
    now = datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
        clock=lambda: now,
    )
    decision = scheduler.evaluate((current,), now)
    scheduler._completed_sessions.add(decision.session_key)
    scheduler._state = SessionState.WAITING
    current.config_path.write_text(
        configuration + 'total-follows-limit: "5"\n', encoding="utf-8"
    )

    assert scheduler.account_configuration_changed(current)
    assert decision.session_key not in scheduler._completed_sessions
    assert scheduler._wake_event.is_set()


def test_generic_runtime_eligibility_transition_wakes_account(tmp_path):
    current = account(tmp_path, "current", "09.00-11.00")
    configuration = current.config_path.read_text(encoding="utf-8")
    current.config_path.write_text(
        configuration + "custom-module-ready: false\n", encoding="utf-8"
    )
    now = datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
        runtime_eligibility=lambda _account, config: bool(
            config.get("custom-module-ready")
        ),
        clock=lambda: now,
    )
    decision = scheduler.evaluate((current,), now)
    scheduler._completed_sessions.add(decision.session_key)
    scheduler._state = SessionState.WAITING
    current.config_path.write_text(
        configuration + "custom-module-ready: true\n", encoding="utf-8"
    )

    assert scheduler.account_configuration_changed(current)
    assert decision.session_key not in scheduler._completed_sessions


def test_daily_limit_increase_does_not_wake_outside_run_hours(tmp_path):
    current = account(tmp_path, "current", "09.00-11.00")
    configuration = current.config_path.read_text(encoding="utf-8")
    current.config_path.write_text(
        configuration + 'total-follows-limit: "2"\n', encoding="utf-8"
    )
    inside = datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    outside = datetime(2026, 8, 26, 12, 0)  # noqa: DTZ001
    current_time = [inside]
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
        runtime_eligibility=lambda _account, config: int(config["total-follows-limit"])
        > 2,
        clock=lambda: current_time[0],
    )
    decision = scheduler.evaluate((current,), inside)
    scheduler._completed_sessions.add(decision.session_key)
    scheduler._state = SessionState.WAITING
    current_time[0] = outside
    current.config_path.write_text(
        configuration + 'total-follows-limit: "5"\n', encoding="utf-8"
    )

    assert not scheduler.account_configuration_changed(current)
    assert decision.session_key in scheduler._completed_sessions
    assert not scheduler._wake_event.is_set()


def test_daily_limit_increase_does_not_wake_stopped_or_running_scheduler(tmp_path):
    current = account(tmp_path, "current", "09.00-11.00")
    configuration = current.config_path.read_text(encoding="utf-8")
    current.config_path.write_text(
        configuration + 'total-follows-limit: "2"\n', encoding="utf-8"
    )
    now = datetime(2026, 8, 26, 10, 0)  # noqa: DTZ001
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
        runtime_eligibility=lambda _account, config: int(config["total-follows-limit"])
        > 2,
        clock=lambda: now,
    )
    decision = scheduler.evaluate((current,), now)
    scheduler._completed_sessions.add(decision.session_key)
    current.config_path.write_text(
        configuration + 'total-follows-limit: "5"\n', encoding="utf-8"
    )

    scheduler._state = SessionState.IDLE
    assert not scheduler.account_configuration_changed(current)
    scheduler._state = SessionState.RUNNING
    assert not scheduler.account_configuration_changed(current)
    assert decision.session_key in scheduler._completed_sessions


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


def test_default_scheduler_uses_native_runtime_without_legacy_subprocess(
    tmp_path, monkeypatch, caplog
):
    current = account(tmp_path, "current", "09.00-11.00")
    runtime_started = threading.Event()
    runtime_released = threading.Event()
    created = []

    class NativeRuntime:
        state = SessionState.IDLE

        def __init__(self, selected, workspace):
            created.append((selected, workspace))

        def start(self, callback):
            self.state = SessionState.RUNNING
            callback(self.state)
            runtime_started.set()
            runtime_released.wait(timeout=2)
            self.state = SessionState.STOPPED
            callback(self.state)

        def request_stop(self, _callback):
            self.state = SessionState.STOPPING
            runtime_released.set()

    monkeypatch.setattr(
        "IGBot.runtime.native_integration.create_native_runtime", NativeRuntime
    )
    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        device_validator=lambda _: True,
        clock=lambda: datetime(2026, 8, 26, 10, 0),  # noqa: DTZ001
    )
    states = []
    thread = threading.Thread(
        target=scheduler.start, args=(states.append, lambda *_: None)
    )

    with caplog.at_level(logging.INFO):
        thread.start()
        assert runtime_started.wait(timeout=2)
        scheduler.stop(states.append)
        thread.join(timeout=2)

    assert created == [(current, tmp_path)]
    assert "Starting Native Runtime for current" in caplog.text
    assert "Launching InstaAddict" not in caplog.text
    assert "python -m InstaAddict" not in caplog.text
    assert not thread.is_alive()


def test_native_runtime_exception_is_reported_to_ui_boundary(tmp_path):
    current = account(tmp_path, "broken", "09.00-11.00")
    failures = []
    runtime_started = threading.Event()

    class FailingRuntime:
        state = SessionState.IDLE

        def __init__(self, *_args):
            pass

        def start(self, callback):
            self.state = SessionState.RUNNING
            callback(self.state)
            runtime_started.set()
            raise RuntimeError("native startup exploded")

        def request_stop(self, _callback):
            pass

    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        runtime_factory=FailingRuntime,
        device_validator=lambda _: True,
        clock=lambda: datetime(2026, 8, 26, 10, 0),  # noqa: DTZ001
    )
    states = []
    thread = threading.Thread(
        target=scheduler.start,
        args=(states.append, lambda *_: None, failures.append),
    )

    thread.start()
    assert runtime_started.wait(timeout=2)
    scheduler.stop(states.append)
    thread.join(timeout=2)

    assert failures == ["broken: native startup exploded"]
    assert not thread.is_alive()


def test_legacy_runtime_requires_explicit_compatibility_mode(tmp_path, monkeypatch):
    current = account(tmp_path, "legacy", "09.00-11.00")
    created = []

    class LegacyRuntime:
        pass

    monkeypatch.setattr("IGBot.core.phone_scheduler.SessionEngine", LegacyRuntime)

    scheduler = PhoneScheduler(
        DeviceRecord("PHONE", "T1", True, (current,)),
        tmp_path,
        runtime_mode=RuntimeMode.LEGACY,
    )

    created.append(scheduler._runtime_factory)
    assert created == [LegacyRuntime]


def _wait_for(predicate):
    for _ in range(200):
        if predicate():
            return True
        threading.Event().wait(0.005)
    return False
