from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.session import SessionContext, SessionController
from IGBot.runtime.startup import (
    StartupPipeline,
    StartupStage,
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)
from IGBot.runtime.state import SessionState


class RecordingStage:
    def __init__(self, result, calls):
        self._result = result
        self._calls = calls

    def execute(self, context):
        self._calls.append((self._result.stage, context.session.session_id))
        return self._result


class RecordingScheduler:
    def __init__(self):
        self.calls = []

    def start(self, context):
        self.calls.append(context)


class RecordingLogger:
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


@pytest.fixture
def session_context(tmp_path):
    return SessionContext(
        session_id=uuid4(),
        account_username="runtime_account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def runtime_context(session_context):
    return RuntimeContext(session_context, RecordingLogger())


def test_stage_interface_exposes_exactly_one_public_method():
    methods = {
        name
        for name, value in StartupStage.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"execute"}


def test_pipeline_runs_stages_in_order_and_builds_startup_result(runtime_context):
    calls = []
    stages = (
        RecordingStage(
            StartupStageResult(
                StartupStageName.INTERNET,
                StartupStageStatus.SUCCESS,
                internet_available=True,
            ),
            calls,
        ),
        RecordingStage(
            StartupStageResult(
                StartupStageName.AIRPLANE_MODE,
                StartupStageStatus.SKIPPED,
            ),
            calls,
        ),
        RecordingStage(
            StartupStageResult(
                StartupStageName.ACCOUNT_VERIFICATION,
                StartupStageStatus.SUCCESS,
                account_verified=True,
            ),
            calls,
        ),
        RecordingStage(
            StartupStageResult(
                StartupStageName.FOLLOWER_SYNCHRONIZATION,
                StartupStageStatus.SUCCESS,
                new_followers_found=3,
            ),
            calls,
        ),
    )

    result = StartupPipeline(stages).execute(runtime_context)

    assert [stage for stage, _ in calls] == [stage._result.stage for stage in stages]
    assert result.startup_completed is True
    assert result.startup_failed is False
    assert result.internet_available is True
    assert result.account_verified is True
    assert result.new_followers_found == 3
    assert result.stage_results == tuple(stage._result for stage in stages)


def test_pipeline_stops_after_first_failed_stage(runtime_context):
    calls = []
    failed = StartupStageResult(
        StartupStageName.INSTAGRAM_LAUNCH,
        StartupStageStatus.FAILED,
        detail="Package unavailable",
    )
    stages = (
        RecordingStage(failed, calls),
        RecordingStage(
            StartupStageResult(
                StartupStageName.WAIT_AFTER_LAUNCH,
                StartupStageStatus.SUCCESS,
            ),
            calls,
        ),
    )

    result = StartupPipeline(stages).execute(runtime_context)

    assert len(calls) == 1
    assert result.startup_completed is False
    assert result.startup_failed is True
    assert result.failure_reason == "Package unavailable"
    assert result.stage_results == (failed,)


def test_session_controller_transfers_completed_startup_to_scheduler(session_context):
    stage = RecordingStage(
        StartupStageResult(
            StartupStageName.ACCOUNT_VERIFICATION,
            StartupStageStatus.SUCCESS,
            account_verified=True,
        ),
        [],
    )
    scheduler = RecordingScheduler()
    controller = SessionController(
        StartupPipeline((stage,)), scheduler, RecordingLogger()
    )

    result = controller.start(session_context)

    assert result.scheduler_started is True
    assert result.handle.session_id == session_context.session_id
    assert scheduler.calls == [result.context]
    assert result.context.startup_result is result.startup_result
    assert controller.state_for(session_context.session_id) is SessionState.RUNNING


def test_session_controller_does_not_start_scheduler_after_failure(session_context):
    stage = RecordingStage(
        StartupStageResult(
            StartupStageName.ACCOUNT_VERIFICATION,
            StartupStageStatus.FAILED,
            detail="Account not verified",
            account_verified=False,
        ),
        [],
    )
    scheduler = RecordingScheduler()
    controller = SessionController(
        StartupPipeline((stage,)), scheduler, RecordingLogger()
    )

    result = controller.start(session_context)

    assert result.scheduler_started is False
    assert result.startup_result.account_verified is False
    assert scheduler.calls == []
    assert controller.state_for(session_context.session_id) is SessionState.FAILED


def test_pipeline_rejects_unstructured_stage_results(runtime_context):
    class InvalidStage:
        def execute(self, context):
            return None

    with pytest.raises(TypeError, match="StartupStageResult"):
        StartupPipeline((InvalidStage(),)).execute(runtime_context)


def test_pipeline_rejects_an_empty_stage_registration():
    with pytest.raises(ValueError, match="at least one stage"):
        StartupPipeline(())


def test_session_startup_executes_only_once(session_context):
    stage = RecordingStage(
        StartupStageResult(
            StartupStageName.INTERNET,
            StartupStageStatus.SKIPPED,
        ),
        [],
    )
    controller = SessionController(
        StartupPipeline((stage,)), RecordingScheduler(), RecordingLogger()
    )

    controller.start(session_context)

    with pytest.raises(RuntimeError, match="already executed"):
        controller.start(session_context)


def test_startup_result_rejects_negative_follower_count():
    with pytest.raises(ValueError, match="cannot be negative"):
        StartupStageResult(
            StartupStageName.FOLLOWER_SYNCHRONIZATION,
            StartupStageStatus.SUCCESS,
            new_followers_found=-1,
        )
