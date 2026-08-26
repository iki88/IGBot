import logging
import os
import threading

import pytest

from IGBot.core.device import AssignedAccount
from IGBot.core.session_engine import (
    SessionEngine,
    SessionState,
    SessionValidationError,
)


class FakeProcess:
    def __init__(self, output=(), exit_code=0, block=False):
        self.stdout = iter(output)
        self.exit_code = exit_code
        self.signal = None
        self._released = threading.Event()
        if not block:
            self._released.set()

    def wait(self):
        self._released.wait(timeout=2)
        return self.exit_code

    def send_signal(self, value):
        self.signal = value
        self._released.set()


def make_account(tmp_path, *, app_id="com.instagram.clone", device="SERIAL"):
    directory = tmp_path / "accounts" / "alice"
    directory.mkdir(parents=True)
    config = directory / "config.yml"
    config.write_text(
        f'username: "alice"\ndevice: "{device}"\napp-id: "{app_id}"\n',
        encoding="utf-8",
    )
    return AssignedAccount("alice", device, app_id, config)


def test_successful_runtime_start_and_output_forwarding(tmp_path, caplog):
    account = make_account(tmp_path)
    process = FakeProcess(["engine output\n"])
    calls = []
    engine = SessionEngine(
        account,
        tmp_path,
        process_factory=lambda *args, **kwargs: calls.append((args, kwargs)) or process,
        device_validator=lambda serial: serial == "SERIAL",
    )
    states = []

    with caplog.at_level(logging.INFO):
        engine.run(states.append)

    assert states == [SessionState.STARTING, SessionState.RUNNING, SessionState.STOPPED]
    assert calls[0][0][0][-3:] == ["run", "--config", str(account.config_path)]
    assert "[alice] engine output" in caplog.text
    assert engine._process is None


def test_graceful_stop_and_cleanup(tmp_path):
    account = make_account(tmp_path)
    process = FakeProcess(exit_code=2, block=True)
    engine = SessionEngine(
        account,
        tmp_path,
        process_factory=lambda *args, **kwargs: process,
        device_validator=lambda _: True,
    )
    states = []
    thread = threading.Thread(target=engine.run, args=(states.append,))
    thread.start()
    for _ in range(100):
        if engine.state == SessionState.RUNNING:
            break
        threading.Event().wait(0.005)

    engine.request_stop(states.append)
    thread.join(timeout=2)

    assert states == [
        SessionState.STARTING,
        SessionState.RUNNING,
        SessionState.STOPPING,
        SessionState.STOPPED,
    ]
    assert process.signal is not None
    assert engine._process is None


@pytest.mark.parametrize(
    ("app_id", "connected", "message"),
    [("", True, "Application ID"), ("com.instagram.clone", False, "not connected")],
)
def test_validation_rejects_invalid_configuration_or_device(
    tmp_path, app_id, connected, message
):
    account = make_account(tmp_path, app_id=app_id)
    engine = SessionEngine(
        account,
        tmp_path,
        device_validator=lambda _: connected,
    )

    with pytest.raises(SessionValidationError, match=message):
        engine.validate()


def test_duplicate_start_is_rejected(tmp_path):
    account = make_account(tmp_path)
    engine = SessionEngine(account, tmp_path, device_validator=lambda _: True)
    engine._state = SessionState.RUNNING

    with pytest.raises(RuntimeError, match="already active"):
        engine.run(lambda _: None)


def test_process_group_is_created_on_windows(tmp_path):
    account = make_account(tmp_path)
    captured = {}

    def factory(*args, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    SessionEngine(
        account,
        tmp_path,
        process_factory=factory,
        device_validator=lambda _: True,
    ).run(lambda _: None)

    expected = (
        __import__("subprocess").CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    assert captured["creationflags"] == expected
