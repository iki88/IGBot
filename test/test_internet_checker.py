import subprocess
from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.network import (
    AndroidNetworkProvider,
    NetworkCheckResult,
    NetworkProvider,
)
from IGBot.runtime.session import SessionController
from IGBot.runtime.startup import (
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


class SequenceNetworkProvider:
    def __init__(self, observations, events=None):
        self._observations = list(observations)
        self.contexts = []
        self._events = events

    def check(self, context):
        self.contexts.append(context)
        if self._events is not None:
            self._events.append("network-check")
        return self._observations.pop(0)


class RecordingStage:
    def __init__(self, events):
        self._events = events

    def execute(self, context):
        self._events.append("next-stage")
        return StartupStageResult(
            StartupStageName.AIRPLANE_MODE,
            StartupStageStatus.SKIPPED,
        )


class RecordingScheduler:
    def __init__(self, events):
        self._events = events
        self.contexts = []

    def start(self, context):
        self._events.append("scheduler")
        self.contexts.append(context)


def make_context(tmp_path, logger=None):
    session = SessionContext(
        session_id=uuid4(),
        account_username="runtime_account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )
    return RuntimeContext(session, logger or RecordingLogger())


def test_network_provider_is_a_single_method_abstraction():
    methods = {
        name
        for name, value in NetworkProvider.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"check"}


def test_internet_checker_returns_success_when_available(tmp_path):
    context = make_context(tmp_path)
    provider = SequenceNetworkProvider((NetworkCheckResult(True),))
    sleeps = []

    result = InternetChecker(provider, sleeper=sleeps.append).execute(context)

    assert result == StartupStageResult(
        StartupStageName.INTERNET,
        StartupStageStatus.SUCCESS,
        internet_available=True,
    )
    assert provider.contexts == [context]
    assert sleeps == []
    assert context.logger.messages == []


def test_internet_checker_retries_every_sixty_seconds_until_restored(tmp_path):
    context = make_context(tmp_path)
    provider = SequenceNetworkProvider(
        (
            NetworkCheckResult(False),
            NetworkCheckResult(False, "probe failed"),
            NetworkCheckResult(True),
        )
    )
    sleeps = []

    result = InternetChecker(provider, sleeper=sleeps.append).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert result.internet_available is True
    assert provider.contexts == [context, context, context]
    assert sleeps == [60, 60]
    assert context.logger.messages == [
        ("warning", InternetChecker.RETRY_MESSAGE, {}),
        ("warning", InternetChecker.RETRY_MESSAGE, {}),
    ]


def test_provider_exception_returns_structured_failure(tmp_path):
    class FailingProvider:
        def check(self, context):
            raise RuntimeError("provider unavailable")

    context = make_context(tmp_path)

    result = InternetChecker(FailingProvider(), sleeper=lambda _: None).execute(context)

    assert result.status is StartupStageStatus.FAILED
    assert result.internet_available is False
    assert result.detail == "Internet provider failed: provider unavailable"
    assert context.logger.messages == [
        ("error", "Internet provider failed: provider unavailable", {})
    ]


def test_internet_checker_is_first_pipeline_stage(tmp_path):
    events = []
    context = make_context(tmp_path)
    provider = SequenceNetworkProvider((NetworkCheckResult(True),), events)
    checker = InternetChecker(provider, sleeper=lambda _: None)
    pipeline = StartupPipeline.with_internet_checker(
        checker,
        (RecordingStage(events),),
    )

    result = pipeline.execute(context)

    assert events == ["network-check", "next-stage"]
    assert [item.stage for item in result.stage_results] == [
        StartupStageName.INTERNET,
        StartupStageName.AIRPLANE_MODE,
    ]
    assert pipeline.stages[0] is checker


def test_scheduler_starts_only_after_connectivity_is_restored(tmp_path):
    events = []
    logger = RecordingLogger()
    runtime_context = make_context(tmp_path, logger)
    provider = SequenceNetworkProvider(
        (NetworkCheckResult(False), NetworkCheckResult(True)), events
    )
    checker = InternetChecker(
        provider,
        sleeper=lambda seconds: events.append(f"sleep-{seconds}"),
    )
    scheduler = RecordingScheduler(events)
    controller = SessionController(
        StartupPipeline.with_internet_checker(checker),
        scheduler,
        logger,
    )

    result = controller.start(runtime_context.session)

    assert events == ["network-check", "sleep-60", "network-check", "scheduler"]
    assert scheduler.contexts == [result.context]
    assert result.startup_result.internet_available is True


def test_android_network_provider_isolates_the_adb_probe(tmp_path):
    calls = []

    def command_runner(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 0, "", "")

    context = make_context(tmp_path)
    provider = AndroidNetworkProvider(
        command_runner=command_runner,
        adb_executable="adb-test",
        probe_host="203.0.113.1",
    )

    result = provider.check(context)

    assert result == NetworkCheckResult(True)
    assert calls == [
        (
            [
                "adb-test",
                "-s",
                "device-1",
                "shell",
                "ping",
                "-c",
                "1",
                "-W",
                "5",
                "203.0.113.1",
            ],
            {
                "capture_output": True,
                "text": True,
                "check": False,
                "timeout": 10,
            },
        )
    ]


def test_android_network_provider_returns_unavailable_without_raising(tmp_path):
    def command_runner(command, **options):
        return subprocess.CompletedProcess(command, 1, "", "network unreachable")

    context = make_context(tmp_path)
    provider = AndroidNetworkProvider(
        command_runner=command_runner,
        adb_executable="adb-test",
    )

    assert provider.check(context) == NetworkCheckResult(False, "network unreachable")
