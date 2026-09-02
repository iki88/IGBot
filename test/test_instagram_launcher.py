import subprocess
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.application import (
    AndroidApplicationProvider,
    ApplicationLaunchResult,
    ApplicationProvider,
    ForegroundApplicationResult,
)
from IGBot.runtime.startup import (
    InstagramLauncher,
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


class RecordingApplicationProvider:
    def __init__(
        self,
        launch_result=None,
        foreground_result=None,
    ):
        self.launch_result = launch_result or ApplicationLaunchResult(True)
        self.foreground_result = foreground_result or ForegroundApplicationResult(
            "com.instagram.clone"
        )
        self.calls = []

    def launch(self, context, package):
        self.calls.append(("launch", context, package))
        return self.launch_result

    def foreground(self, context):
        self.calls.append(("foreground", context))
        return self.foreground_result


class RecordingStage:
    def __init__(self, stage, events):
        self._stage = stage
        self._events = events

    def execute(self, context):
        self._events.append(self._stage)
        return StartupStageResult(self._stage, StartupStageStatus.SKIPPED)


def make_context(tmp_path, *, application_id="com.instagram.clone", delay=0):
    session = SessionContext(
        session_id=uuid4(),
        account_username="runtime_account",
        phone_id="device-1",
        application_id=application_id,
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )
    return RuntimeContext(
        session,
        RecordingLogger(),
        runtime_settings={InstagramLauncher.WAIT_SETTING_KEY: delay},
    )


def test_application_provider_exposes_launch_and_foreground_only():
    methods = {
        name
        for name, value in ApplicationProvider.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"launch", "foreground"}


def test_launcher_uses_runtime_context_and_verifies_foreground(tmp_path):
    context = make_context(tmp_path)
    provider = RecordingApplicationProvider()
    sleeps = []

    result = InstagramLauncher(provider, sleeper=sleeps.append).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert provider.calls == [
        ("launch", context, "com.instagram.clone"),
        ("foreground", context),
    ]
    assert sleeps == []
    assert context.logger.messages == [
        (
            "info",
            "Launching Instagram",
            {"application_id": "com.instagram.clone"},
        ),
        (
            "info",
            "Instagram is in the foreground",
            {"application_id": "com.instagram.clone"},
        ),
    ]


@pytest.mark.parametrize(("configured", "expected"), (("10", 10), (10, 10)))
def test_fixed_wait_runs_only_after_successful_launch(tmp_path, configured, expected):
    context = make_context(tmp_path, delay=configured)
    provider = RecordingApplicationProvider()
    events = []

    class EventProvider:
        def launch(self, runtime_context, package):
            events.append("launch")
            return provider.launch(runtime_context, package)

        def foreground(self, runtime_context):
            events.append("foreground")
            return provider.foreground(runtime_context)

    result = InstagramLauncher(
        EventProvider(),
        sleeper=lambda seconds: events.append(("sleep", seconds)),
    ).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert events == ["launch", ("sleep", expected), "foreground"]


def test_range_wait_selects_one_inclusive_value(tmp_path):
    context = make_context(tmp_path, delay="8-12")
    selected_ranges = []
    sleeps = []

    result = InstagramLauncher(
        RecordingApplicationProvider(),
        sleeper=sleeps.append,
        range_selector=lambda minimum, maximum: (
            selected_ranges.append((minimum, maximum)) or 11
        ),
    ).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert selected_ranges == [(8, 12)]
    assert sleeps == [11]


def test_failed_launch_does_not_wait_or_query_foreground(tmp_path):
    context = make_context(tmp_path, delay="10")
    provider = RecordingApplicationProvider(
        launch_result=ApplicationLaunchResult(False, "Package is not installed.")
    )
    sleeps = []

    result = InstagramLauncher(provider, sleeper=sleeps.append).execute(context)

    assert result == StartupStageResult(
        StartupStageName.INSTAGRAM_LAUNCH,
        StartupStageStatus.FAILED,
        detail="Package is not installed.",
    )
    assert [call[0] for call in provider.calls] == ["launch"]
    assert sleeps == []
    assert context.logger.messages[-1] == (
        "error",
        "Package is not installed.",
        {},
    )


def test_wrong_foreground_package_fails_startup(tmp_path):
    context = make_context(tmp_path)
    provider = RecordingApplicationProvider(
        foreground_result=ForegroundApplicationResult("com.android.settings")
    )

    result = InstagramLauncher(provider, sleeper=lambda _: None).execute(context)

    assert result.status is StartupStageStatus.FAILED
    assert result.detail == (
        "Instagram foreground verification failed: expected com.instagram.clone, "
        "observed com.android.settings."
    )


@pytest.mark.parametrize("delay", ("8-", "12-8", "ten", True, -1))
def test_invalid_wait_configuration_fails_before_launch(tmp_path, delay):
    context = make_context(tmp_path, delay=delay)
    provider = RecordingApplicationProvider()

    result = InstagramLauncher(provider, sleeper=lambda _: None).execute(context)

    assert result.status is StartupStageStatus.FAILED
    assert provider.calls == []


def test_invalid_application_id_fails_before_launch(tmp_path):
    context = make_context(tmp_path, application_id="")
    provider = RecordingApplicationProvider()

    result = InstagramLauncher(provider, sleeper=lambda _: None).execute(context)

    assert result.status is StartupStageStatus.FAILED
    assert "Application ID" in result.detail
    assert provider.calls == []


def test_android_provider_launches_configured_package(tmp_path):
    calls = []

    def command_runner(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 0, "Status: ok", "")

    context = make_context(tmp_path)
    result = AndroidApplicationProvider(
        command_runner=command_runner,
        adb_executable="adb-test",
    ).launch(context, "com.instagram.clone")

    assert result == ApplicationLaunchResult(True)
    assert calls[0][0] == [
        "adb-test",
        "-s",
        "device-1",
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.LAUNCHER",
        "-p",
        "com.instagram.clone",
    ]


def test_android_provider_uses_foreground_query_fallback(tmp_path):
    calls = []
    outputs = iter(
        (
            "no current focus",
            "mResumedActivity: ActivityRecord{1 com.instagram.clone/.MainActivity}",
        )
    )

    def command_runner(command, **options):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, next(outputs), "")

    context = make_context(tmp_path)
    result = AndroidApplicationProvider(
        command_runner=command_runner,
        adb_executable="adb-test",
    ).foreground(context)

    assert result == ForegroundApplicationResult("com.instagram.clone")
    assert calls[0][-3:] == ["dumpsys", "window", "windows"]
    assert calls[1][-3:] == ["dumpsys", "activity", "activities"]


def test_pipeline_places_instagram_launcher_third(tmp_path):
    events = []
    stages = (
        RecordingStage(StartupStageName.INTERNET, events),
        RecordingStage(StartupStageName.AIRPLANE_MODE, events),
        RecordingStage(StartupStageName.INSTAGRAM_LAUNCH, events),
        RecordingStage(StartupStageName.ACCOUNT_VERIFICATION, events),
    )
    pipeline = StartupPipeline.with_initial_stages(
        stages[0], stages[1], stages[2], stages[3]
    )

    pipeline.execute(make_context(tmp_path))

    assert events == [
        StartupStageName.INTERNET,
        StartupStageName.AIRPLANE_MODE,
        StartupStageName.INSTAGRAM_LAUNCH,
        StartupStageName.ACCOUNT_VERIFICATION,
    ]
