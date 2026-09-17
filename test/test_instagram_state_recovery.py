from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.account_verification import AndroidInstagramStateProvider
from IGBot.runtime.application import ApplicationLaunchResult
from IGBot.runtime.startup import (
    InstagramStateRecovery,
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


def make_context(tmp_path):
    return RuntimeContext(
        SessionContext(
            session_id=uuid4(),
            account_username="expected_user",
            phone_id="device-1",
            application_id="com.instagram.clone",
            account_directory=tmp_path,
            created_at=datetime.now(timezone.utc),
        ),
        RecordingLogger(),
    )


class SequenceStateProvider:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def recover(self, context):
        self.calls += 1
        return next(self.outcomes)


class RecordingApplicationProvider:
    def __init__(self, *, stopped=True, launched=True):
        self.stopped = stopped
        self.launched = launched
        self.calls = []

    def force_stop(self, context, package):
        self.calls.append(("force_stop", package))
        return ApplicationLaunchResult(self.stopped)

    def launch(self, context, package):
        self.calls.append(("launch", package))
        return ApplicationLaunchResult(self.launched)

    def foreground(self, context):  # pragma: no cover - unused contract member
        raise AssertionError("foreground is not part of state recovery")


class RecordingRelauncher:
    def __init__(self, *, succeeds=True):
        self.succeeds = succeeds
        self.calls = 0

    def execute(self, context):
        self.calls += 1
        return StartupStageResult(
            StartupStageName.INSTAGRAM_LAUNCH,
            StartupStageStatus.SUCCESS if self.succeeds else StartupStageStatus.FAILED,
        )


def test_recovery_reaches_profile_without_restarting(tmp_path):
    context = make_context(tmp_path)
    state = SequenceStateProvider([True])
    application = RecordingApplicationProvider()
    relauncher = RecordingRelauncher()

    result = InstagramStateRecovery(state, application, relauncher).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert state.calls == 1
    assert application.calls == []
    assert relauncher.calls == 0


def test_recovery_force_stops_and_relaunches_after_navigation_exhaustion(tmp_path):
    context = make_context(tmp_path)
    state = SequenceStateProvider([False, True])
    application = RecordingApplicationProvider()
    relauncher = RecordingRelauncher()

    result = InstagramStateRecovery(state, application, relauncher).execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert state.calls == 2
    assert application.calls == [("force_stop", "com.instagram.clone")]
    assert relauncher.calls == 1


def test_recovery_failure_stops_pipeline_before_account_verification(tmp_path):
    context = make_context(tmp_path)
    recovery = InstagramStateRecovery(
        SequenceStateProvider([False, False]),
        RecordingApplicationProvider(),
        RecordingRelauncher(),
    )
    events = []

    class Stage:
        def __init__(self, name):
            self.name = name

        def execute(self, context):
            events.append(self.name)
            return StartupStageResult(self.name, StartupStageStatus.SKIPPED)

    pipeline = StartupPipeline.with_initial_stages(
        Stage(StartupStageName.INTERNET),
        Stage(StartupStageName.AIRPLANE_MODE),
        Stage(StartupStageName.INSTAGRAM_LAUNCH),
        Stage(StartupStageName.ACCOUNT_VERIFICATION),
        instagram_state_recovery=recovery,
    )

    result = pipeline.execute(context)

    assert result.startup_failed is True
    assert events == [
        StartupStageName.INTERNET,
        StartupStageName.AIRPLANE_MODE,
        StartupStageName.INSTAGRAM_LAUNCH,
    ]
    assert result.stage_results[-1].stage is StartupStageName.INSTAGRAM_STATE_RECOVERY


def hierarchy(*nodes):
    return "<hierarchy>" + "".join(nodes) + "</hierarchy>"


def node(*, resource_id="", description="", bounds="[0,0][100,100]"):
    return (
        f'<node resource-id="{resource_id}" content-desc="{description}" '
        f'bounds="{bounds}" />'
    )


class FakeDevice:
    def __init__(self, hierarchies):
        self.hierarchies = iter(hierarchies)
        self.clicks = []
        self.presses = []

    def dump_hierarchy(self, *, compressed):
        assert compressed is False
        return next(self.hierarchies)

    def click(self, x, y):
        self.clicks.append((x, y))

    def press(self, key):
        self.presses.append(key)


def test_android_recovery_backs_out_of_nested_screen_then_opens_profile(tmp_path):
    nested = hierarchy(node(resource_id="com.instagram.clone:id/follow_list_container"))
    main = hierarchy(
        node(
            resource_id="com.instagram.clone:id/tab_avatar",
            description="Profile",
            bounds="[900,1800][1080,1920]",
        )
    )
    profile = hierarchy(node(resource_id="com.instagram.clone:id/action_bar_title"))
    device = FakeDevice((nested, main, profile))
    provider = AndroidInstagramStateProvider(
        device_factory=lambda _: device,
        sleeper=lambda _: None,
        attempts=3,
    )

    assert provider.recover(make_context(tmp_path)) is True
    assert device.presses == ["back"]
    assert device.clicks == [(990, 1860)]


def test_android_recovery_is_bounded_when_no_known_surface_appears(tmp_path):
    unknown = hierarchy(node(resource_id="com.instagram.clone:id/unknown"))
    device = FakeDevice((unknown, unknown, unknown))
    provider = AndroidInstagramStateProvider(
        device_factory=lambda _: device,
        sleeper=lambda _: None,
        attempts=3,
    )

    assert provider.recover(make_context(tmp_path)) is False
    assert device.presses == ["back", "back", "back"]
