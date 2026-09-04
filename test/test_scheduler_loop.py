from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.modules import InteractionModule
from IGBot.runtime.recovery import FailureKind, RecoveryDecision
from IGBot.runtime.scheduler import (
    BackoffPolicy,
    BudgetCalculator,
    ExecutionCoordinator,
    ModuleExecutionOutcome,
    ModuleExecutionResult,
    ModulePoolBuilder,
    ModuleSelector,
    Scheduler,
    SchedulerLoop,
)
from IGBot.runtime.startup import StartupResult
from IGBot.runtime.state import ModuleState, SessionState


class StubLogger:
    def __init__(self):
        self.messages = []

    def debug(self, message, **fields):
        self.messages.append(("debug", message, fields))

    def info(self, message, **fields):
        self.messages.append(("info", message, fields))

    def warning(self, message, **fields):
        self.messages.append(("warning", message, fields))

    def error(self, message, **fields):
        self.messages.append(("error", message, fields))


class StubModule:
    def __init__(self, context, module, *, daily_remaining=100):
        self.context = context
        self.module = module
        self.enabled = True
        self.configured = True
        self.state = ModuleState.READY
        self.backoff_until = None
        self.budget_configuration = 5
        self.daily_remaining = daily_remaining

    def is_eligible(self):
        return self.state is ModuleState.READY and self.enabled

    def start(self):
        self.state = ModuleState.RUNNING

    def mark_ready(self):
        self.state = ModuleState.READY

    def enter_backoff(self, backoff_until):
        self.backoff_until = backoff_until
        self.state = ModuleState.BACKOFF

    def mark_daily_limit_reached(self):
        self.state = ModuleState.DAILY_LIMIT_REACHED


class StaticModuleProvider:
    def __init__(self, modules):
        self.modules = modules

    def modules_for(self, context):
        assert all(module.context is context for module in self.modules)
        return self.modules


class CountedActivity:
    def __init__(self, active_cycles):
        self.remaining = active_cycles

    def is_active(self, context):
        if self.remaining == 0:
            return False
        self.remaining -= 1
        return True


class SequenceExecutor:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def execute(self, context, module, budget):
        self.calls.append((context, module, budget))
        outcome = self.outcomes.pop(0)
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=module.state,
            outcome=outcome,
        )


class RecordingRecovery:
    def __init__(self):
        self.requests = []

    def recover(self, request):
        self.requests.append(request)
        return RecoveryDecision(False, True, "Paused after action block.")


def make_context(tmp_path, *, new_followers=0):
    context = RuntimeContext(
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
    context.session_state = SessionState.RUNNING
    context.startup_result = StartupResult(
        startup_completed=True,
        internet_available=True,
        account_verified=True,
        new_followers_found=new_followers,
        startup_failed=False,
        stage_results=(),
    )
    return context


def make_loop(modules, executor, activity, *, chooser=None, now=None, sleeps=None):
    scheduler = Scheduler(
        ModulePoolBuilder(),
        ModuleSelector(chooser=chooser) if chooser else ModuleSelector(),
        BudgetCalculator(),
        ExecutionCoordinator(executor),
    )
    return SchedulerLoop(
        scheduler,
        StaticModuleProvider(modules),
        activity,
        BackoffPolicy(randint=lambda _minimum, _maximum: 17),
        RecordingRecovery(),
        clock=(lambda: now) if now else lambda: datetime.now(timezone.utc),
        sleeper=(
            (lambda seconds: sleeps.append(seconds))
            if sleeps is not None
            else lambda _seconds: None
        ),
    )


def test_loop_repeats_cycles_and_stops_at_session_boundary(tmp_path):
    context = make_context(tmp_path)
    follow = StubModule(context, InteractionModule.FOLLOW)
    like = StubModule(context, InteractionModule.LIKE)
    selected = iter((follow, like))
    executor = SequenceExecutor(
        (ModuleExecutionOutcome.SUCCESS, ModuleExecutionOutcome.SUCCESS)
    )
    loop = make_loop(
        (follow, like),
        executor,
        CountedActivity(2),
        chooser=lambda _pool: next(selected),
    )

    result = loop.start(context)

    assert [call[1].module for call in executor.calls] == [
        InteractionModule.FOLLOW,
        InteractionModule.LIKE,
    ]
    assert follow.state is ModuleState.READY
    assert like.state is ModuleState.READY
    assert result.session_ended is True
    assert len(result.cycles) == 2


def test_startup_new_followers_prioritize_one_initial_dm_cycle(tmp_path):
    context = make_context(tmp_path, new_followers=3)
    follow = StubModule(context, InteractionModule.FOLLOW)
    dm = StubModule(context, InteractionModule.DM)
    executor = SequenceExecutor(
        (ModuleExecutionOutcome.SUCCESS, ModuleExecutionOutcome.SUCCESS)
    )
    loop = make_loop(
        (follow, dm),
        executor,
        CountedActivity(2),
        chooser=lambda pool: next(
            module for module in pool if module.module is InteractionModule.FOLLOW
        ),
    )

    result = loop.start(context)

    assert [call[1].module for call in executor.calls] == [
        InteractionModule.DM,
        InteractionModule.FOLLOW,
    ]
    assert result.initial_dm_executed is True


@pytest.mark.parametrize(
    ("outcome", "expected_state", "minutes"),
    (
        (ModuleExecutionOutcome.NO_CANDIDATES, ModuleState.BACKOFF, 17),
        (ModuleExecutionOutcome.SCROLL_BLOCK, ModuleState.BACKOFF, 60),
        (
            ModuleExecutionOutcome.DAILY_LIMIT_REACHED,
            ModuleState.DAILY_LIMIT_REACHED,
            None,
        ),
    ),
)
def test_loop_applies_scheduler_owned_outcome_policy(
    tmp_path, outcome, expected_state, minutes
):
    context = make_context(tmp_path)
    module = StubModule(context, InteractionModule.FOLLOW)
    now = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)
    executor = SequenceExecutor((outcome,))
    loop = make_loop((module,), executor, CountedActivity(1), now=now)

    result = loop.start(context)

    assert module.state is expected_state
    if minutes is not None:
        assert module.backoff_until == now + timedelta(minutes=minutes)
    assert result.cycles[0].next_module_state is expected_state


def test_action_block_is_delegated_to_recovery(tmp_path):
    context = make_context(tmp_path)
    module = StubModule(context, InteractionModule.DM)
    executor = SequenceExecutor((ModuleExecutionOutcome.ACTION_BLOCK,))
    recovery = RecordingRecovery()
    scheduler = Scheduler(
        ModulePoolBuilder(),
        ModuleSelector(chooser=lambda pool: pool[0]),
        BudgetCalculator(),
        ExecutionCoordinator(executor),
    )
    loop = SchedulerLoop(
        scheduler,
        StaticModuleProvider((module,)),
        CountedActivity(1),
        BackoffPolicy(),
        recovery,
        sleeper=lambda _seconds: None,
    )

    loop.start(context)

    assert len(recovery.requests) == 1
    assert recovery.requests[0].failure is FailureKind.ACTION_BLOCK


def test_no_eligible_modules_waits_without_executing(tmp_path):
    context = make_context(tmp_path)
    module = StubModule(context, InteractionModule.STORY)
    module.state = ModuleState.DISABLED
    module.enabled = False
    sleeps = []
    executor = SequenceExecutor(())
    loop = make_loop((module,), executor, CountedActivity(2), sleeps=sleeps)

    result = loop.start(context)

    assert executor.calls == []
    assert sleeps == [1.0, 1.0]
    assert len(result.cycles) == 2


def test_inactive_session_terminates_before_any_scheduler_work(tmp_path):
    context = make_context(tmp_path)
    module = StubModule(context, InteractionModule.FOLLOW)
    executor = SequenceExecutor(())
    loop = make_loop((module,), executor, CountedActivity(0))

    result = loop.start(context)

    assert executor.calls == []
    assert result.cycles == ()
