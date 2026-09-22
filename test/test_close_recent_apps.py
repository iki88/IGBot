import subprocess
from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.recent_apps import (
    AndroidRecentAppsProvider,
    CloseRecentAppsResult,
)
from IGBot.runtime.startup import (
    CloseRecentApps,
    StartupStageName,
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

    def close(self, context):
        self.contexts.append(context)
        return self.result


class FakeDevice:
    def __init__(self, hierarchies):
        self.hierarchies = list(hierarchies)
        self.presses = []
        self.clicks = []

    def press(self, key):
        self.presses.append(key)

    def click(self, x, y):
        self.clicks.append((x, y))

    def dump_hierarchy(self, compressed=False):
        assert compressed is False
        return self.hierarchies.pop(0)


def context(tmp_path, *, enabled=True):
    return RuntimeContext(
        SessionContext(
            session_id=uuid4(),
            account_username="account",
            phone_id="phone-1",
            application_id="com.instagram.clone",
            account_directory=tmp_path,
            created_at=datetime.now(timezone.utc),
        ),
        RecordingLogger(),
        runtime_settings={CloseRecentApps.SETTING_KEY: enabled},
    )


def test_close_recent_apps_stage_skips_disabled_setting(tmp_path):
    runtime_context = context(tmp_path, enabled=False)
    provider = RecordingProvider(CloseRecentAppsResult(True, 3))

    result = CloseRecentApps(provider).execute(runtime_context)

    assert result.status is StartupStageStatus.SKIPPED
    assert result.stage is StartupStageName.CLOSE_RECENT_APPS
    assert provider.contexts == []


def test_close_recent_apps_stage_logs_closed_count_once(tmp_path):
    runtime_context = context(tmp_path)
    provider = RecordingProvider(CloseRecentAppsResult(True, 2))

    result = CloseRecentApps(provider).execute(runtime_context)

    assert result.status is StartupStageStatus.SUCCESS
    assert provider.contexts == [runtime_context]
    assert runtime_context.logger.messages == [("info", "Closed 2 recent apps.", {})]


def test_close_recent_apps_stage_reports_empty_recents(tmp_path):
    runtime_context = context(tmp_path)

    result = CloseRecentApps(RecordingProvider(CloseRecentAppsResult(True))).execute(
        runtime_context
    )

    assert result.status is StartupStageStatus.SUCCESS
    assert runtime_context.logger.messages[-1][1] == ("No removable recent apps found.")


def test_android_provider_uses_system_close_all_and_preserves_locked_task(tmp_path):
    close_all = (
        '<hierarchy><node text="Close all" resource-id="com.sec.android.app.launcher:id/btn_clear_all" '
        'bounds="[100,1800][980,1920]" /></hierarchy>'
    )
    closed = '<hierarchy><node text="Home" bounds="[0,0][100,100]" /></hierarchy>'
    device = FakeDevice((close_all, closed))
    dumps = iter(
        (
            "Recent tasks:\n  Task{abc #101}\n  Task{def #202}",
            "Recent tasks:\n  Task{def #202}",
        )
    )

    def run(command, **options):
        return subprocess.CompletedProcess(command, 0, next(dumps), "")

    result = AndroidRecentAppsProvider(
        device_factory=lambda _serial: device,
        command_runner=run,
        adb_executable="adb-test",
        sleeper=lambda _seconds: None,
    ).close(context(tmp_path))

    assert result == CloseRecentAppsResult(True, 1)
    assert device.presses == ["recent"]
    assert device.clicks == [(540, 1860)]


def test_android_provider_does_not_swipe_or_close_locked_apps_individually(tmp_path):
    empty = '<hierarchy><node text="Home" bounds="[0,0][100,100]" /></hierarchy>'
    device = FakeDevice((empty,))

    result = AndroidRecentAppsProvider(
        device_factory=lambda _serial: device,
        command_runner=lambda command, **options: subprocess.CompletedProcess(
            command, 0, "Recent tasks:\n  Task{locked #202}", ""
        ),
        adb_executable="adb-test",
        sleeper=lambda _seconds: None,
        timeout=0,
    ).close(context(tmp_path))

    assert result == CloseRecentAppsResult(True)
    assert device.presses == ["recent", "home"]
    assert not hasattr(device, "swipes")
