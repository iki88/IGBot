from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.follower_synchronization import (
    AndroidFollowerReader,
    FollowerReadResult,
    FollowerSynchronization,
    RuntimeFollowerComparer,
    RuntimeFollowerWriter,
)
from IGBot.runtime.startup import (
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


class StubReader:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def read(self, context, limit):
        self.calls.append((context, limit))
        return self.result


class RecordingStage:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def execute(self, context):
        self.events.append(self.name)
        return StartupStageResult(self.name, StartupStageStatus.SKIPPED)


class FakeDevice:
    def __init__(self, hierarchies):
        self.hierarchies = iter(hierarchies)
        self.clicks = []
        self.swipes = []

    def dump_hierarchy(self, **options):
        return next(self.hierarchies)

    def click(self, x, y):
        self.clicks.append((x, y))

    def swipe(self, *coordinates, **options):
        self.swipes.append((coordinates, options))


def make_context(tmp_path, limit=100):
    session = SessionContext(
        session_id=uuid4(),
        account_username="account",
        phone_id="device-1",
        application_id="com.instagram.clone",
        account_directory=tmp_path,
        created_at=datetime.now(timezone.utc),
    )
    return RuntimeContext(
        session,
        RecordingLogger(),
        runtime_settings={"follower_synchronization_limit": limit},
    )


def hierarchy(*nodes):
    body = "".join(
        (
            '<node text="{text}" resource-id="{resource_id}" '
            'bounds="{bounds}" scrollable="{scrollable}" />'
        ).format(**node)
        for node in nodes
    )
    return f'<hierarchy rotation="0">{body}</hierarchy>'


def node(
    text="",
    resource_id="",
    bounds="[0,0][100,100]",
    scrollable="false",
):
    return {
        "text": text,
        "resource_id": resource_id,
        "bounds": bounds,
        "scrollable": scrollable,
    }


def test_synchronization_updates_follow_backs_and_inserts_organic_users(tmp_path):
    observed_at = datetime(2026, 9, 4, 12, 30, tzinfo=timezone.utc)
    with RuntimeDatabase(tmp_path) as database:
        followed = database.users.create(
            "followed_user", "2026-09-01T10:00:00+00:00", "FOLLOW"
        )
        database.follow.save(
            FollowRecord(
                followed.id,
                source="source_account",
                follow_date="2026-09-01T10:01:00+00:00",
            )
        )
        database.users.create(
            "known_without_follow", "2026-09-02T10:00:00+00:00", "LIKE"
        )

    reader = StubReader(
        FollowerReadResult(
            True,
            ("followed_user", "organic_user", "known_without_follow"),
            limit_reached=False,
        )
    )
    context = make_context(tmp_path, limit=50)
    stage = FollowerSynchronization(
        reader,
        RuntimeFollowerComparer(),
        RuntimeFollowerWriter(),
        clock=lambda: observed_at,
    )

    result = stage.execute(context)

    assert result.status is StartupStageStatus.SUCCESS
    assert result.new_followers_found == 1
    assert result.follower_synchronization.synchronization_completed is True
    assert result.follower_synchronization.follow_back_updates == 1
    assert result.follower_synchronization.newly_discovered_organic_followers == (
        "organic_user",
    )
    assert reader.calls == [(context, 50)]

    with RuntimeDatabase(tmp_path) as database:
        organic = database.users.get_by_username("organic_user")
        followed_state = database.follow.get(followed.id)
        known = database.users.get_by_username("known_without_follow")

        assert organic.first_discovered_by == "ORGANIC"
        assert organic.first_seen == "2026-09-04T12:30:00+00:00"
        assert database.follow.get(organic.id) is None
        assert followed_state.follow_back is True
        assert followed_state.follow_back_date == "2026-09-04T12:30:00+00:00"
        assert database.follow.get(known.id) is None
        assert database.like.get(followed.id) is None
        assert database.comment.get(followed.id) is None
        assert database.story.get(followed.id) is None
        assert database.dm.get(followed.id) is None


def test_synchronization_requires_a_positive_configured_limit(tmp_path):
    reader = StubReader(FollowerReadResult(True))
    context = make_context(tmp_path, limit=0)
    stage = FollowerSynchronization(
        reader,
        RuntimeFollowerComparer(),
        RuntimeFollowerWriter(),
    )

    result = stage.execute(context)

    assert result.status is StartupStageStatus.FAILED
    assert "positive integer" in result.detail
    assert reader.calls == []


def test_android_reader_uses_resource_ids_and_respects_limit(tmp_path):
    device = FakeDevice(
        (
            hierarchy(
                node(
                    resource_id="com.instagram.clone:id/tab_avatar",
                    bounds="[900,1800][1080,1920]",
                )
            ),
            hierarchy(
                node(
                    resource_id=(
                        "com.instagram.clone:id/"
                        "row_profile_header_followers_container"
                    ),
                    bounds="[200,200][400,300]",
                )
            ),
            hierarchy(
                node(
                    text="first_user",
                    resource_id="com.instagram.clone:id/row_user_primary_name",
                ),
                node(
                    text="truncated...",
                    resource_id="com.instagram.clone:id/row_user_primary_name",
                ),
                node(
                    resource_id="com.instagram.clone:id/recycler_view",
                    bounds="[0,300][1080,1800]",
                    scrollable="true",
                ),
            ),
            hierarchy(
                node(
                    text="second_user",
                    resource_id="com.instagram.clone:id/follow_list_username",
                ),
                node(
                    resource_id="com.instagram.clone:id/recycler_view",
                    bounds="[0,300][1080,1800]",
                    scrollable="true",
                ),
            ),
        )
    )
    reader = AndroidFollowerReader(
        device_factory=lambda _: device,
        sleeper=lambda _: None,
    )

    result = reader.read(make_context(tmp_path), limit=2)

    assert result == FollowerReadResult(
        True,
        ("first_user", "second_user"),
        limit_reached=True,
    )
    assert len(device.clicks) == 2
    assert len(device.swipes) == 1


def test_pipeline_places_synchronization_after_account_verification(tmp_path):
    events = []
    initial = [
        RecordingStage(StartupStageName.INTERNET, events),
        RecordingStage(StartupStageName.AIRPLANE_MODE, events),
        RecordingStage(StartupStageName.INSTAGRAM_LAUNCH, events),
        RecordingStage(StartupStageName.ACCOUNT_VERIFICATION, events),
    ]
    synchronization = RecordingStage(StartupStageName.FOLLOWER_SYNCHRONIZATION, events)
    pipeline = StartupPipeline.with_initial_stages(
        *initial,
        follower_synchronization=synchronization,
    )

    pipeline.execute(make_context(tmp_path))

    assert events == [stage.name for stage in initial] + [
        StartupStageName.FOLLOWER_SYNCHRONIZATION
    ]


def test_pipeline_exposes_synchronization_in_startup_result(tmp_path):
    stage = FollowerSynchronization(
        StubReader(FollowerReadResult(True, ("organic",))),
        RuntimeFollowerComparer(),
        RuntimeFollowerWriter(),
        clock=lambda: datetime(2026, 9, 4, tzinfo=timezone.utc),
    )

    startup = StartupPipeline((stage,)).execute(make_context(tmp_path))

    assert startup.new_followers_found == 1
    assert startup.follower_synchronization.synchronization_completed is True
    assert startup.follower_synchronization.newly_discovered_organic_followers == (
        "organic",
    )
