from datetime import datetime, timezone
from inspect import signature
from uuid import uuid4

from IGBot.runtime import RuntimeContext, RuntimeLogger, SessionContext
from IGBot.runtime.compatibility import ExecutionRequest
from IGBot.runtime.hooks import HookEvent
from IGBot.runtime.recovery import RecoveryRequest
from IGBot.runtime.scheduler import SchedulerEntryPoint
from IGBot.runtime.session import SessionController
from IGBot.runtime.shutdown import ShutdownRequest
from IGBot.runtime.startup import (
    StartupPipeline,
    StartupStage,
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)
from IGBot.runtime.state import SessionState


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


class CapturingStage:
    def __init__(self):
        self.contexts = []

    def execute(self, context):
        self.contexts.append(context)
        return StartupStageResult(
            StartupStageName.INTERNET,
            StartupStageStatus.SKIPPED,
        )


class CapturingScheduler:
    def __init__(self):
        self.contexts = []

    def start(self, context):
        self.contexts.append(context)


def make_session_context(tmp_path):
    return SessionContext(
        session_id=uuid4(),
        account_username="runtime_account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )


def test_runtime_context_construction_uses_session_scoped_defaults(tmp_path):
    session = make_session_context(tmp_path)
    logger = RecordingLogger()

    context = RuntimeContext(session, logger)

    assert context.session is session
    assert context.logger is logger
    assert context.runtime_settings == {}
    assert context.session_state is SessionState.PENDING
    assert context.startup_result is None


def test_runtime_logger_exposes_provider_independent_levels():
    methods = {
        name
        for name, value in RuntimeLogger.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"debug", "info", "warning", "error"}
    for method_name in methods:
        parameters = signature(getattr(RuntimeLogger, method_name)).parameters
        assert tuple(parameters) == ("self", "message", "fields")


def test_session_controller_passes_one_runtime_context_everywhere(tmp_path):
    session = make_session_context(tmp_path)
    logger = RecordingLogger()
    stage = CapturingStage()
    scheduler = CapturingScheduler()
    controller = SessionController(StartupPipeline((stage,)), scheduler, logger)

    result = controller.start(session)

    assert stage.contexts == [result.context]
    assert scheduler.contexts == [result.context]
    assert controller.context_for(session.session_id) is result.context
    assert result.context.logger is logger
    assert result.context.startup_result is result.startup_result


def test_runtime_boundaries_depend_on_runtime_context():
    assert StartupStage.execute.__annotations__["context"] == "RuntimeContext"
    assert SchedulerEntryPoint.start.__annotations__["context"] == "RuntimeContext"
    for model in (
        HookEvent,
        RecoveryRequest,
        ShutdownRequest,
        ExecutionRequest,
    ):
        assert model.__annotations__["context"] == "RuntimeContext"
