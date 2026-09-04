from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.modules import InteractionModule
from IGBot.runtime.scheduler import (
    BudgetCalculator,
    ExecutionBudget,
    ExecutionCoordinator,
    ModuleExecutionResult,
    ModulePoolBuilder,
    ModuleSelector,
    Scheduler,
    SchedulerResult,
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


class StubModule:
    def __init__(
        self,
        context,
        module,
        *,
        eligible=True,
        budget_configuration=15,
        daily_remaining=100,
        state=ModuleState.READY,
    ):
        self.context = context
        self.module = module
        self.enabled = state is not ModuleState.DISABLED
        self.backoff_until = None
        self.state = state
        self.budget_configuration = budget_configuration
        self.daily_remaining = daily_remaining
        self.eligible = eligible
        self.eligibility_checks = 0

    def is_eligible(self):
        self.eligibility_checks += 1
        return self.eligible


class RecordingExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, context, module, budget):
        self.calls.append((context, module, budget))
        return self.result


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


def test_module_pool_builder_includes_only_self_reported_eligible_modules(tmp_path):
    context = make_context(tmp_path)
    eligible = StubModule(context, InteractionModule.FOLLOW)
    ineligible = StubModule(context, InteractionModule.LIKE, eligible=False)

    pool = ModulePoolBuilder().build((eligible, ineligible))

    assert pool == (eligible,)
    assert eligible.eligibility_checks == 1
    assert ineligible.eligibility_checks == 1


def test_module_selector_uses_unweighted_injected_random_choice(tmp_path):
    context = make_context(tmp_path)
    modules = (
        StubModule(context, InteractionModule.FOLLOW),
        StubModule(context, InteractionModule.DM),
    )
    received = []
    selector = ModuleSelector(
        chooser=lambda pool: received.append(tuple(pool)) or pool[1]
    )

    assert selector.select(modules) is modules[1]
    assert received == [modules]
    assert selector.select(()) is None


def test_budget_calculator_supports_fixed_values_and_daily_clamping(tmp_path):
    module = StubModule(
        make_context(tmp_path),
        InteractionModule.LIKE,
        budget_configuration="15",
        daily_remaining=9,
    )

    budget = BudgetCalculator().calculate(module)

    assert budget == ExecutionBudget(
        InteractionModule.LIKE,
        configured="15",
        resolved=15,
        daily_remaining=9,
        final=9,
    )


def test_budget_calculator_supports_inclusive_ranges(tmp_path):
    calls = []
    module = StubModule(
        make_context(tmp_path),
        InteractionModule.STORY,
        budget_configuration="10-20",
        daily_remaining=50,
    )
    calculator = BudgetCalculator(
        randint=lambda minimum, maximum: calls.append((minimum, maximum)) or 17
    )

    budget = calculator.calculate(module)

    assert calls == [(10, 20)]
    assert budget.resolved == 17
    assert budget.final == 17


@pytest.mark.parametrize("configured", ("", "0", "20-10", "ten", "1-"))
def test_budget_calculator_rejects_invalid_configuration(tmp_path, configured):
    module = StubModule(
        make_context(tmp_path),
        InteractionModule.COMMENT,
        budget_configuration=configured,
    )

    with pytest.raises(ValueError, match="positive integer or range"):
        BudgetCalculator().calculate(module)


def test_execution_coordinator_delegates_without_module_behavior(tmp_path):
    context = make_context(tmp_path)
    module = StubModule(context, InteractionModule.DM)
    budget = BudgetCalculator().calculate(module)
    execution = ModuleExecutionResult(
        execution_started=True,
        execution_finished=True,
        next_module_state=ModuleState.READY,
    )
    executor = RecordingExecutor(execution)

    result = ExecutionCoordinator(executor).coordinate(context, module, budget)

    assert result is execution
    assert executor.calls == [(context, module, budget)]


def test_scheduler_framework_returns_structured_cycle_result(tmp_path):
    context = make_context(tmp_path)
    ineligible = StubModule(context, InteractionModule.FOLLOW, eligible=False)
    selected = StubModule(
        context,
        InteractionModule.LIKE,
        budget_configuration="10-20",
        daily_remaining=12,
    )
    execution = ModuleExecutionResult(
        execution_started=True,
        execution_finished=True,
        next_module_state=ModuleState.BACKOFF,
        detail="Source exhausted.",
    )
    executor = RecordingExecutor(execution)
    scheduler = Scheduler(
        ModulePoolBuilder(),
        ModuleSelector(chooser=lambda pool: pool[0]),
        BudgetCalculator(randint=lambda _minimum, _maximum: 15),
        ExecutionCoordinator(executor),
    )

    result = scheduler.evaluate_once(context, (ineligible, selected))

    assert result == SchedulerResult(
        selected_module=InteractionModule.LIKE,
        budget=ExecutionBudget(
            module=InteractionModule.LIKE,
            configured="10-20",
            resolved=15,
            daily_remaining=12,
            final=12,
        ),
        execution_started=True,
        execution_finished=True,
        next_module_state=ModuleState.BACKOFF,
        detail="Source exhausted.",
    )
    assert executor.calls[0][0] is context
    assert executor.calls[0][1] is selected


def test_scheduler_does_not_execute_when_no_module_is_eligible(tmp_path):
    context = make_context(tmp_path)
    executor = RecordingExecutor(ModuleExecutionResult(True, True, ModuleState.READY))
    scheduler = Scheduler(
        ModulePoolBuilder(),
        ModuleSelector(),
        BudgetCalculator(),
        ExecutionCoordinator(executor),
    )

    result = scheduler.evaluate_once(
        context,
        (StubModule(context, InteractionModule.FOLLOW, eligible=False),),
    )

    assert result.selected_module is None
    assert result.execution_started is False
    assert result.detail == "No eligible modules."
    assert executor.calls == []


def test_scheduler_respects_zero_remaining_daily_limit(tmp_path):
    context = make_context(tmp_path)
    module = StubModule(
        context,
        InteractionModule.FOLLOW,
        daily_remaining=0,
    )
    executor = RecordingExecutor(ModuleExecutionResult(True, True, ModuleState.READY))
    scheduler = Scheduler(
        ModulePoolBuilder(),
        ModuleSelector(chooser=lambda pool: pool[0]),
        BudgetCalculator(),
        ExecutionCoordinator(executor),
    )

    result = scheduler.evaluate_once(context, (module,))

    assert result.budget.final == 0
    assert result.execution_started is False
    assert result.detail == "Daily limit reached."
    assert executor.calls == []
