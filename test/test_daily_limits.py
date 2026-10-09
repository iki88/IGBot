from datetime import datetime, timezone

from IGBot.runtime.database import DailyLimitResolver, RuntimeDatabase
from IGBot.runtime.unfollow.following_list_database import FollowingListDatabase

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def test_range_is_resolved_once_and_survives_resolver_restart(tmp_path):
    calls = []

    def choose(lower, upper):
        calls.append((lower, upper))
        return 53

    first = DailyLimitResolver(tmp_path, randint=choose).capacity(
        "follow", "50-60", now=NOW
    )
    second = DailyLimitResolver(
        tmp_path, randint=lambda *_: (_ for _ in ()).throw(AssertionError("rerolled"))
    ).capacity("follow", "50-60", now=NOW)

    assert first.resolved_target == second.resolved_target == 53
    assert calls == [(50, 60)]
    with RuntimeDatabase(tmp_path) as database:
        assert database.daily_limits.get("follow", "2026-09-29").configured_spec == "50-60"


def test_fixed_zero_is_a_hard_zero_cap(tmp_path):
    capacity = DailyLimitResolver(tmp_path).capacity("dm", 0, now=NOW)
    assert capacity.resolved_target == 0
    assert capacity.remaining == 0


def test_new_utc_day_gets_a_new_range_target(tmp_path):
    targets = iter((53, 57))
    resolver = DailyLimitResolver(tmp_path, randint=lambda _a, _b: next(targets))

    assert resolver.capacity("like", "50-60", now=NOW).resolved_target == 53
    tomorrow = datetime(2026, 9, 30, 0, 1, tzinfo=timezone.utc)
    assert resolver.capacity("like", "50-60", now=tomorrow).resolved_target == 57


def test_range_configuration_change_does_not_reroll_same_day(tmp_path):
    resolver = DailyLimitResolver(tmp_path, randint=lambda _a, _b: 45)
    assert resolver.capacity("dm", "40-50", now=NOW).resolved_target == 45
    assert resolver.capacity("dm", "50-60", now=NOW).resolved_target == 45


def test_fixed_limit_changes_apply_according_to_completed_usage(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.create("one", "2026-09-29 09:00:00", "FOLLOW")
        database._connection.execute(
            """INSERT INTO follow
            (user_id, username, source, follow_date, follow_back, unfollowed, muted)
            VALUES (?, ?, ?, ?, 0, 0, 0)""",
            (user.id, "one", "source", "2026-09-29 09:00:00"),
        )

    resolver = DailyLimitResolver(tmp_path)
    assert resolver.capacity("follow", "10", now=NOW).resolved_target == 10
    assert resolver.capacity("follow", "15", now=NOW).resolved_target == 15
    assert resolver.capacity("follow", "5", now=NOW).resolved_target == 5


def test_fixed_decrease_is_deferred_when_new_cap_is_already_consumed(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        for index in range(3):
            user = database.users.create(
                f"user{index}", "2026-09-29 09:00:00", "FOLLOW"
            )
            database._connection.execute(
                """INSERT INTO follow
                (user_id, username, source, follow_date, follow_back, unfollowed, muted)
                VALUES (?, ?, ?, ?, 0, 0, 0)""",
                (user.id, f"user{index}", "source", "2026-09-29 09:00:00"),
            )

    resolver = DailyLimitResolver(tmp_path)
    assert resolver.capacity("follow", "10", now=NOW).resolved_target == 10
    capacity = resolver.capacity("follow", "3", now=NOW)
    assert capacity.resolved_target == 10
    assert capacity.remaining == 7


def test_module_usage_aggregates_discovery_and_specific_providers(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.create("normal", "2026-09-29 08:00:00", "LIKE")
        database._connection.execute(
            """INSERT INTO like
            (user_id, username, source, likes_count, last_like_date, status, processed_date)
            VALUES (?, ?, ?, 1, ?, 'SUCCESS', ?)""",
            (user.id, "normal", "source", "2026-09-29 08:00:00", "2026-09-29 08:00:00"),
        )
        database._connection.execute(
            """INSERT INTO specific_like
            (user_id, username, liked, likes_count, last_like_date, status)
            VALUES (?, ?, 1, 1, ?, 'SUCCESS')""",
            (user.id, "normal", "2026-09-29 09:00:00"),
        )

    capacity = DailyLimitResolver(tmp_path).capacity("like", "5", now=NOW)
    assert capacity.successful_interactions == 2
    assert capacity.remaining == 3


def test_unfollow_usage_aggregates_all_runtime_stores(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.create("search.user", "2026-09-29 08:00:00", "FOLLOW")
        database._connection.execute(
            """INSERT INTO follow
            (user_id, username, source, unfollowed, unfollow_date, muted)
            VALUES (?, ?, ?, 1, ?, 0)""",
            (user.id, "search.user", "source", "2026-09-29 08:00:00"),
        )
        database._connection.execute(
            """INSERT INTO specific_unfollow
            (user_id, username, unfollowed, unfollow_date, status)
            VALUES (2, 'specific.user', 1, ?, 'SUCCESS')""",
            ("2026-09-29 09:00:00",),
        )
    with FollowingListDatabase(tmp_path) as database:
        database.mark_unfollowed(
            "following.list.user", "2026-09-29 10:00:00", "session"
        )

    capacity = DailyLimitResolver(tmp_path).capacity("unfollow", "5", now=NOW)
    assert capacity.successful_interactions == 3
    assert capacity.remaining == 2
