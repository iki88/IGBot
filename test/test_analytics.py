import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from IGBot.runtime.analytics import AnalyticsDatabase, DailySummaryDisplay

DAY_ONE = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
DAY_TWO = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def test_analytics_database_creates_one_daily_summary_row_and_updates_live(tmp_path):
    with AnalyticsDatabase(tmp_path, clock=lambda: DAY_ONE) as database:
        database.update_snapshot(
            "account", posts=115, followers=3129, following=97
        )
        database.increment("account", "followed")
        database.increment("account", "liked", 2)
        database.update_snapshot(
            "account", posts=116, followers=3131, following=96
        )

    assert (tmp_path / "analytics.db").is_file()
    with sqlite3.connect(tmp_path / "analytics.db") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM daily_summary"
        ).fetchone()[0] == 1
    with AnalyticsDatabase(tmp_path, clock=lambda: DAY_ONE) as database:
        summary = database.get("2026-09-29")
    assert summary.username == "account"
    assert (summary.posts, summary.followers, summary.following) == (116, 3131, 96)
    assert summary.followed == 1
    assert summary.liked == 2


def test_new_day_does_not_modify_previous_summary(tmp_path):
    with AnalyticsDatabase(tmp_path, clock=lambda: DAY_ONE) as database:
        database.update_snapshot("old_name", posts=10, followers=100, following=20)
        database.increment("old_name", "dm")
    with AnalyticsDatabase(tmp_path, clock=lambda: DAY_TWO) as database:
        database.update_snapshot("new_name", posts=11, followers=108, following=18)
        database.increment("new_name", "unfollowed")
        display = database.today_display()

    assert display.previous.username == "old_name"
    assert display.previous.followers == 100
    assert display.previous.dm == 1
    assert display.today.username == "new_name"
    assert display.today.unfollowed == 1
    assert DailySummaryDisplay.absolute_with_change(108, 100) == "108 ▲8"
    assert DailySummaryDisplay.absolute_with_change(18, 20) == "18 ▼2"
    assert DailySummaryDisplay.absolute_with_change(11, 11) == "11"
    assert DailySummaryDisplay.absolute_with_change(11, None) == "11"


def test_statistics_windows_read_analytics_history(tmp_path):
    for offset in range(31):
        current = DAY_TWO - timedelta(days=offset)
        with AnalyticsDatabase(tmp_path, clock=lambda current=current: current) as database:
            database.increment("account", "story")

    with AnalyticsDatabase(tmp_path, clock=lambda: DAY_TWO) as database:
        assert len(database.history()) == 30
        assert len(database.history(30)) == 30
        assert len(database.history(90)) == 31
        assert len(database.history(180)) == 31
        assert len(database.history(None)) == 31


def test_analytics_rejects_unknown_counters_and_non_positive_increments(tmp_path):
    with AnalyticsDatabase(tmp_path, clock=lambda: DAY_ONE) as database:
        with pytest.raises(ValueError, match="Unsupported"):
            database.increment("account", "unknown")
        with pytest.raises(ValueError, match="positive"):
            database.increment("account", "liked", 0)
