import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest

from IGBot.runtime import (
    RuntimeContext,
    RuntimeFoundation,
    SessionContext,
    SessionState,
)
from IGBot.runtime.compatibility import ExecutionRequest, ExecutionStatus
from IGBot.runtime.scheduler import LimitScope, ModuleBudget, SchedulingDecision
from IGBot.runtime.startup import StartupStageName

RUNTIME_MODULES = (
    "IGBot.runtime",
    "IGBot.runtime.compatibility",
    "IGBot.runtime.database",
    "IGBot.runtime.follower_synchronization",
    "IGBot.runtime.hooks",
    "IGBot.runtime.logging",
    "IGBot.runtime.network",
    "IGBot.runtime.recovery",
    "IGBot.runtime.scheduler",
    "IGBot.runtime.session",
    "IGBot.runtime.shutdown",
    "IGBot.runtime.startup",
    "IGBot.runtime.state",
)


def test_runtime_subsystems_import_without_cycles():
    for module_name in RUNTIME_MODULES:
        assert import_module(module_name).__name__ == module_name


def test_session_context_is_immutable_and_excludes_credentials(tmp_path):
    context = SessionContext(
        session_id=uuid4(),
        account_username="operator_account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )

    assert "password" not in context.__dataclass_fields__
    with pytest.raises(FrozenInstanceError):
        context.account_username = "changed"


def test_state_and_stage_vocabulary_matches_runtime_architecture():
    assert SessionState.RECOVERING.value == "Recovering"
    assert StartupStageName.FOLLOWER_SYNCHRONIZATION.value == "FollowerSynchronization"
    assert LimitScope.DAILY.value == "Daily"


def test_scheduler_and_compatibility_models_are_provider_neutral(tmp_path):
    context = SessionContext(
        session_id=uuid4(),
        account_username="operator_account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=Path(tmp_path),
        created_at=datetime.now(timezone.utc),
    )
    budget = ModuleBudget("Follow", 10, 50, 20)
    decision = SchedulingDecision(module="Follow", reason="Eligible budget")
    runtime_context = RuntimeContext(context, object())
    request = ExecutionRequest(
        runtime_context, decision.module, budget.session_remaining, {}
    )

    assert request.module == "Follow"
    assert ExecutionStatus.COMPLETED.value == "Completed"


def test_foundation_is_a_composition_root_only():
    collaborators = [object() for _ in range(7)]
    foundation = RuntimeFoundation(*collaborators)

    assert foundation.sessions is collaborators[0]
    assert foundation.compatibility is collaborators[-1]


def test_native_runtime_does_not_import_the_legacy_engine():
    runtime_root = Path(__file__).parents[1] / "IGBot" / "runtime"
    imported_roots = set()
    for path in runtime_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.partition(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.partition(".")[0])

    assert "InstaAddict" not in imported_roots
