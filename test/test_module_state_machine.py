from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.modules import (
    InteractionModule,
    InvalidModuleTransition,
    ModuleStateMachine,
    RuntimeModule,
)
from IGBot.runtime.state import ModuleState


class StubLogger:
    def debug(self, message, **fields):
        pass

    def info(self, message, **fields):
        pass

    def warning(self, message, **fields):
        pass

    def error(self, message, **fields):
        pass


class MutableClock:
    def __init__(self, current):
        self.current = current

    def __call__(self):
        return self.current


def make_context(tmp_path):
    return RuntimeContext(
        SessionContext(
            session_id=uuid4(),
            account_username="account",
            phone_id="device-1",
            application_id="com.instagram.clone",
            account_directory=tmp_path,
            created_at=datetime.now(timezone.utc),
        ),
        StubLogger(),
    )


def test_module_state_vocabulary_is_the_frozen_shared_contract():
    assert {state.value for state in ModuleState} == {
        "READY",
        "RUNNING",
        "BACKOFF",
        "DAILY_LIMIT_REACHED",
        "DISABLED",
    }
    assert {module.value for module in InteractionModule} == {
        "Follow",
        "Like",
        "Comment",
        "Story",
        "DM",
    }


def test_ready_running_ready_transitions_and_eligibility(tmp_path):
    now = datetime(2026, 9, 5, 10, tzinfo=timezone.utc)
    machine = ModuleStateMachine(
        make_context(tmp_path),
        InteractionModule.FOLLOW,
        enabled=True,
        configured=True,
        clock=lambda: now,
    )

    assert machine.is_eligible() is True
    started = machine.start()
    assert started.previous is ModuleState.READY
    assert started.current is ModuleState.RUNNING
    assert machine.is_eligible() is False

    completed = machine.mark_ready()
    assert completed.previous is ModuleState.RUNNING
    assert completed.current is ModuleState.READY
    assert machine.is_eligible() is True


def test_backoff_is_metadata_and_expires_back_to_ready(tmp_path):
    clock = MutableClock(datetime(2026, 9, 5, 10, tzinfo=timezone.utc))
    machine = ModuleStateMachine(
        make_context(tmp_path),
        InteractionModule.LIKE,
        enabled=True,
        configured=True,
        clock=clock,
    )
    boundary = clock.current + timedelta(minutes=15)

    machine.enter_backoff(boundary)

    assert machine.state is ModuleState.BACKOFF
    assert machine.backoff_until == boundary
    assert machine.is_eligible() is False

    clock.current = boundary
    assert machine.is_eligible() is True
    assert machine.state is ModuleState.READY
    assert machine.backoff_until is None


def test_daily_limit_resets_on_the_next_utc_day(tmp_path):
    clock = MutableClock(datetime(2026, 9, 5, 23, 59, tzinfo=timezone.utc))
    machine = ModuleStateMachine(
        make_context(tmp_path),
        InteractionModule.COMMENT,
        enabled=True,
        configured=True,
        clock=clock,
    )

    machine.mark_daily_limit_reached()

    assert machine.state is ModuleState.DAILY_LIMIT_REACHED
    assert machine.is_eligible() is False

    clock.current = datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)
    assert machine.is_eligible() is True
    assert machine.state is ModuleState.READY


def test_disabled_module_is_never_eligible_and_can_be_enabled(tmp_path):
    context = make_context(tmp_path)
    machine = ModuleStateMachine(
        context,
        InteractionModule.STORY,
        enabled=False,
        configured=True,
    )

    assert machine.context is context
    assert machine.state is ModuleState.DISABLED
    assert machine.is_eligible() is False

    machine.enable()
    assert machine.state is ModuleState.READY
    assert machine.is_eligible() is True

    machine.disable()
    assert machine.state is ModuleState.DISABLED
    assert machine.is_eligible() is False


def test_enabled_module_requires_valid_configuration(tmp_path):
    with pytest.raises(ValueError, match="must be configured"):
        ModuleStateMachine(
            make_context(tmp_path),
            InteractionModule.DM,
            enabled=True,
            configured=False,
        )


def test_invalid_transition_is_rejected(tmp_path):
    machine = ModuleStateMachine(
        make_context(tmp_path),
        InteractionModule.DM,
        enabled=False,
        configured=True,
    )

    with pytest.raises(InvalidModuleTransition):
        machine.start()


def test_runtime_module_contract_exposes_only_shared_state_surface():
    methods = {
        name
        for name, value in RuntimeModule.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"is_eligible"}
