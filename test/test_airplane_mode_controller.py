import subprocess
from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.airplane_mode import (
    AirplaneModeProvider,
    AirplaneModeToggleResult,
    AndroidAirplaneModeProvider,
)
from IGBot.runtime.startup import (
    AirplaneModeController,
    InternetChecker,
    StartupPipeline,
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


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


class RecordingProvider:
    def __init__(self, result):
        self.result = result
        self.contexts = []

    def toggle(self, context):
        self.contexts.append(context)
        return self.result


class AvailableNetworkProvider:
    def check(self, context):
        from IGBot.runtime.network import NetworkCheckResult

        return NetworkCheckResult(True)


class RecordingFinalStage:
    def __init__(self, events):
        self._events = events

    def execute(self, context):
        self._events.append("final")
        return StartupStageResult(
            StartupStageName.INSTAGRAM_LAUNCH,
            StartupStageStatus.SKIPPED,
        )


def make_context(tmp_path, *, enabled=False):
    session = SessionContext(
        session_id=uuid4(),
        account_username="runtime_account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )
    logger = RecordingLogger()
    return RuntimeContext(
        session,
        logger,
        runtime_settings={
            AirplaneModeController.SETTING_KEY: enabled,
        },
    )


def test_airplane_mode_provider_is_a_single_method_abstraction():
    methods = {
        name
        for name, value in AirplaneModeProvider.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"toggle"}


def test_controller_skips_provider_when_global_setting_is_disabled(tmp_path):
    context = make_context(tmp_path)
    provider = RecordingProvider(AirplaneModeToggleResult(True))

    result = AirplaneModeController(provider).execute(context)

    assert result == StartupStageResult(
        StartupStageName.AIRPLANE_MODE,
        StartupStageStatus.SKIPPED,
    )
    assert provider.contexts == []
    assert context.logger.messages == [
        ("debug", "Airplane Mode toggle is disabled", {})
    ]


def test_controller_toggles_with_runtime_context_and_logs_success(tmp_path):
    context = make_context(tmp_path, enabled=True)
    provider = RecordingProvider(AirplaneModeToggleResult(True))

    result = AirplaneModeController(provider).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert provider.contexts == [context]
    assert context.logger.messages == [
        ("info", "Toggling Airplane Mode between sessions", {}),
        ("info", "Airplane Mode toggle complete", {}),
    ]


def test_controller_returns_and_logs_structured_provider_failure(tmp_path):
    context = make_context(tmp_path, enabled=True)
    provider = RecordingProvider(
        AirplaneModeToggleResult(False, "Airplane Mode command was rejected.")
    )

    result = AirplaneModeController(provider).execute(context)

    assert result == StartupStageResult(
        StartupStageName.AIRPLANE_MODE,
        StartupStageStatus.FAILED,
        detail="Airplane Mode command was rejected.",
    )
    assert context.logger.messages[-1] == (
        "error",
        "Airplane Mode command was rejected.",
        {},
    )


def test_android_provider_uses_verified_connectivity_service_cycle(tmp_path):
    calls = []
    outputs = iter(("", "enabled\n", "", "disabled\n"))

    def command_runner(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 0, next(outputs), "")

    context = make_context(tmp_path, enabled=True)
    provider = AndroidAirplaneModeProvider(
        command_runner=command_runner,
        adb_executable="adb-test",
    )

    assert provider.toggle(context) == AirplaneModeToggleResult(True)
    assert [call[0][-1] for call in calls] == [
        "enable",
        "airplane-mode",
        "disable",
        "airplane-mode",
    ]
    assert all(call[0][1:3] == ["-s", "device-1"] for call in calls)
    assert all(call[1]["timeout"] == 15 for call in calls)


def test_android_provider_reports_failed_verification_and_disables(tmp_path):
    calls = []
    outputs = iter(("", "disabled\n", ""))

    def command_runner(command, **options):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, next(outputs), "")

    context = make_context(tmp_path, enabled=True)
    result = AndroidAirplaneModeProvider(
        command_runner=command_runner,
        adb_executable="adb-test",
    ).toggle(context)

    assert result.succeeded is False
    assert "expected enabled, observed disabled" in result.detail
    assert calls[-1][-1] == "disable"


def test_pipeline_fixes_airplane_mode_immediately_after_internet(tmp_path):
    events = []

    class EventNetworkProvider:
        def check(self, context):
            from IGBot.runtime.network import NetworkCheckResult

            events.append("internet")
            return NetworkCheckResult(True)

    class EventAirplaneProvider:
        def toggle(self, context):
            events.append("airplane")
            return AirplaneModeToggleResult(True)

    context = make_context(tmp_path, enabled=True)
    internet = InternetChecker(EventNetworkProvider(), sleeper=lambda _: None)
    airplane = AirplaneModeController(EventAirplaneProvider())
    pipeline = StartupPipeline.with_initial_stages(
        internet,
        airplane,
        (RecordingFinalStage(events),),
    )

    result = pipeline.execute(context)

    assert events == ["internet", "airplane", "final"]
    assert [stage.stage for stage in result.stage_results] == [
        StartupStageName.INTERNET,
        StartupStageName.AIRPLANE_MODE,
        StartupStageName.INSTAGRAM_LAUNCH,
    ]
