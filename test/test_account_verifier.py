from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.account_verification import (
    AndroidInstagramProfileProvider,
    InstagramProfileProvider,
    ProfileObservation,
    ProfileObservationState,
    UsernameDetectionResult,
)
from IGBot.runtime.notifications import RuntimeNotificationLevel
from IGBot.runtime.session import SessionController
from IGBot.runtime.startup import (
    AccountVerificationState,
    AccountVerifier,
    StartupPipeline,
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


class RecordingNotifier:
    def __init__(self):
        self.notifications = []

    def notify(self, context, notification):
        self.notifications.append((context, notification))


class RecordingProfileProvider:
    def __init__(self, observation, complete=None):
        self.observation = observation
        self.complete = complete or UsernameDetectionResult()
        self.calls = []

    def open_profile(self, context):
        self.calls.append(("profile", context))
        return self.observation

    def complete_username_from_switcher(self, context):
        self.calls.append(("switcher", context))
        return self.complete


class FakeDevice:
    def __init__(self, hierarchies):
        self._hierarchies = iter(hierarchies)
        self.clicks = []
        self.presses = []

    def dump_hierarchy(self, **options):
        return next(self._hierarchies)

    def click(self, x, y):
        self.clicks.append((x, y))

    def press(self, key):
        self.presses.append(key)


class RecordingStage:
    def __init__(self, stage, events):
        self.stage = stage
        self.events = events

    def execute(self, context):
        self.events.append(self.stage)
        return StartupStageResult(self.stage, StartupStageStatus.SKIPPED)


class RecordingScheduler:
    def __init__(self):
        self.contexts = []

    def start(self, context):
        self.contexts.append(context)


def make_context(tmp_path, username="expected_user", logger=None):
    session = SessionContext(
        session_id=uuid4(),
        account_username=username,
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )
    return RuntimeContext(session, logger or RecordingLogger())


def hierarchy(*nodes):
    body = "".join(
        (
            '<node text="{text}" content-desc="{description}" '
            'resource-id="{resource_id}" bounds="{bounds}" />'
        ).format(**node)
        for node in nodes
    )
    return f'<hierarchy rotation="0">{body}</hierarchy>'


def node(text="", description="", resource_id="", bounds="[0,0][100,100]"):
    return {
        "text": text,
        "description": description,
        "resource_id": resource_id,
        "bounds": bounds,
    }


def test_profile_provider_exposes_only_profile_and_switcher_operations():
    methods = {
        name
        for name, value in InstagramProfileProvider.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"open_profile", "complete_username_from_switcher"}


def test_visible_username_is_verified_without_opening_switcher(tmp_path):
    context = make_context(tmp_path)
    provider = RecordingProfileProvider(
        ProfileObservation(
            ProfileObservationState.USERNAME_VISIBLE,
            username="expected_user",
        )
    )
    notifier = RecordingNotifier()

    result = AccountVerifier(provider, notifier).execute(context)

    assert result == StartupStageResult(
        StartupStageName.ACCOUNT_VERIFICATION,
        StartupStageStatus.SUCCESS,
        account_verified=True,
        account_verification=AccountVerificationState.VERIFIED,
        detected_username="expected_user",
    )
    assert provider.calls == [("profile", context)]
    assert notifier.notifications == []


def test_truncated_username_uses_complete_account_switcher_value(tmp_path):
    context = make_context(tmp_path, username="very_long_expected_user")
    provider = RecordingProfileProvider(
        ProfileObservation(
            ProfileObservationState.USERNAME_TRUNCATED,
            username="very_long_expec...",
        ),
        UsernameDetectionResult(username="very_long_expected_user"),
    )

    result = AccountVerifier(provider, RecordingNotifier()).execute(context)

    assert result.account_verification is AccountVerificationState.VERIFIED
    assert result.detected_username == "very_long_expected_user"
    assert [call[0] for call in provider.calls] == ["profile", "switcher"]


def test_username_mismatch_notifies_and_waits_for_operator(tmp_path):
    context = make_context(tmp_path, username="john123")
    provider = RecordingProfileProvider(
        ProfileObservation(
            ProfileObservationState.USERNAME_VISIBLE,
            username="john_new",
        )
    )
    notifier = RecordingNotifier()

    result = AccountVerifier(provider, notifier).execute(context)

    assert result.account_verification is AccountVerificationState.USERNAME_MISMATCH
    assert result.account_verified is False
    assert result.detected_username == "john_new"
    assert context.session_state is SessionState.WAITING_FOR_OPERATOR
    assert context.logger.messages[-1] == (
        "warning",
        "Instagram username mismatch",
        {"expected_username": "john123", "detected_username": "john_new"},
    )
    notification = notifier.notifications[0][1]
    assert notification.level is RuntimeNotificationLevel.WARNING
    assert "Expected: john123" in notification.message
    assert "Detected: john_new" in notification.message
    assert "Update the username in IGBot" in notification.message


def test_profile_not_available_returns_specific_state(tmp_path):
    context = make_context(tmp_path)
    provider = RecordingProfileProvider(
        ProfileObservation(ProfileObservationState.PROFILE_NOT_AVAILABLE)
    )

    result = AccountVerifier(provider, RecordingNotifier()).execute(context)

    assert result.account_verification is AccountVerificationState.PROFILE_NOT_AVAILABLE
    assert result.status is StartupStageStatus.FAILED


def test_profile_not_loaded_returns_specific_state(tmp_path):
    context = make_context(tmp_path)
    provider = RecordingProfileProvider(
        ProfileObservation(ProfileObservationState.PROFILE_NOT_LOADED)
    )

    result = AccountVerifier(provider, RecordingNotifier()).execute(context)

    assert result.account_verification is AccountVerificationState.PROFILE_NOT_LOADED
    assert result.status is StartupStageStatus.FAILED


def test_new_instagram_ui_profile_header_is_supported(tmp_path):
    initial = hierarchy(
        node(
            description="Profile",
            resource_id="com.instagram.clone:id/profile_tab",
            bounds="[900,1800][1080,1920]",
        )
    )
    profile = hierarchy(
        node(
            text="new_ui_user",
            resource_id="com.instagram.clone:id/profile_header_username",
            bounds="[20,60][400,130]",
        ),
        node(bounds="[0,0][1080,1920]"),
    )
    device = FakeDevice((initial, profile))
    provider = AndroidInstagramProfileProvider(
        device_factory=lambda _: device,
        sleeper=lambda _: None,
    )

    result = provider.open_profile(make_context(tmp_path))

    assert result == ProfileObservation(
        ProfileObservationState.USERNAME_VISIBLE,
        username="new_ui_user",
    )
    assert device.clicks == [(990, 1860)]


def test_instagram_372_visible_header_is_supported(tmp_path):
    initial = hierarchy(
        node(
            resource_id="com.instagram.clone:id/tab_avatar",
            bounds="[900,1800][1080,1920]",
        )
    )
    profile = hierarchy(
        node(
            text="expected_user",
            resource_id="com.instagram.clone:id/action_bar_title",
            bounds="[20,60][400,130]",
        ),
        node(bounds="[0,0][1080,1920]"),
    )
    device = FakeDevice((initial, profile))
    provider = AndroidInstagramProfileProvider(
        device_factory=lambda _: device,
        sleeper=lambda _: None,
    )

    result = provider.open_profile(make_context(tmp_path))

    assert result.state is ProfileObservationState.USERNAME_VISIBLE
    assert result.username == "expected_user"


def test_instagram_372_truncated_header_reads_and_closes_switcher(tmp_path):
    initial = hierarchy(
        node(
            resource_id="com.instagram.clone:id/tab_avatar",
            bounds="[900,1800][1080,1920]",
        )
    )
    profile = hierarchy(
        node(
            text="very_long_expec...",
            resource_id="com.instagram.clone:id/action_bar_title",
            bounds="[20,60][400,130]",
        ),
        node(bounds="[0,0][1080,1920]"),
    )
    switcher = hierarchy(
        node(
            text="very_long_expected_user",
            resource_id="com.instagram.clone:id/account_switcher_username",
            bounds="[100,1200][700,1300]",
        ),
        node(bounds="[0,0][1080,1920]"),
    )
    device = FakeDevice((initial, profile, switcher))
    provider = AndroidInstagramProfileProvider(
        device_factory=lambda _: device,
        sleeper=lambda _: None,
    )
    context = make_context(tmp_path, username="very_long_expected_user")

    observation = provider.open_profile(context)
    complete = provider.complete_username_from_switcher(context)

    assert observation.state is ProfileObservationState.USERNAME_TRUNCATED
    assert complete == UsernameDetectionResult(username="very_long_expected_user")
    assert device.clicks == [(990, 1860), (210, 95)]
    assert device.presses == ["back"]


def test_pipeline_places_account_verifier_after_instagram(tmp_path):
    events = []
    stages = (
        RecordingStage(StartupStageName.INTERNET, events),
        RecordingStage(StartupStageName.AIRPLANE_MODE, events),
        RecordingStage(StartupStageName.INSTAGRAM_LAUNCH, events),
        RecordingStage(StartupStageName.ACCOUNT_VERIFICATION, events),
        RecordingStage(StartupStageName.FOLLOWER_SYNCHRONIZATION, events),
    )
    pipeline = StartupPipeline.with_initial_stages(
        stages[0], stages[1], stages[2], stages[3], (stages[4],)
    )

    pipeline.execute(make_context(tmp_path))

    assert events == [stage.stage for stage in stages]


def test_session_controller_preserves_waiting_for_operator_state(tmp_path):
    logger = RecordingLogger()
    session_context = make_context(tmp_path, username="john123", logger=logger).session
    verifier = AccountVerifier(
        RecordingProfileProvider(
            ProfileObservation(
                ProfileObservationState.USERNAME_VISIBLE,
                username="john_new",
            )
        ),
        RecordingNotifier(),
    )
    scheduler = RecordingScheduler()
    controller = SessionController(StartupPipeline((verifier,)), scheduler, logger)

    result = controller.start(session_context)

    assert result.scheduler_started is False
    assert result.context.session_state is SessionState.WAITING_FOR_OPERATOR
    assert scheduler.contexts == []
