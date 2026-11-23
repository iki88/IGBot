import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from IGBot.notifications import (
    NotificationService,
    NotificationSeverity,
    NotificationType,
    ZeroInteractionsDetector,
)
from IGBot.runtime.analytics import AnalyticsDatabase


def test_notification_service_upserts_active_and_resolves(tmp_path):
    service = NotificationService(tmp_path)
    first = service.create(
        "Example_User",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
        device="phone-1",
        tag="test",
    )
    second = service.create(
        "example_user",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
        device="phone-1",
        tag="test",
    )
    assert first.id == second.id
    assert second.occurrences == 2
    assert service.count_active(badge_only=True) == 1
    assert service.resolve("EXAMPLE_USER", NotificationType.ZERO_INTERACTIONS)
    assert service.active() == ()
    assert service.resolved()[0].resolved_at is not None


def test_info_notifications_do_not_affect_badge(tmp_path):
    service = NotificationService(tmp_path)
    service.create(
        "example", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.INFO
    )
    assert service.count_active() == 1
    assert service.count_active(badge_only=True) == 0


def test_active_severity_summary_is_batched_and_prioritizes_critical(tmp_path):
    service = NotificationService(tmp_path)
    service.create(
        "Mixed_User", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.WARNING
    )
    service.create(
        "mixed_user", NotificationType.HUMAN_CAPTCHA, NotificationSeverity.CRITICAL
    )
    service.create(
        "warning_only",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
    )
    service.create(
        "info_only", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.INFO
    )
    service.create(
        "resolved_only",
        NotificationType.ACCOUNT_DISABLED,
        NotificationSeverity.CRITICAL,
    )
    service.resolve("resolved_only", NotificationType.ACCOUNT_DISABLED)

    assert service.active_severity_by_username() == {
        "mixed_user": NotificationSeverity.CRITICAL,
        "warning_only": NotificationSeverity.WARNING,
    }


def test_account_history_orders_active_before_resolved_and_preserves_details(tmp_path):
    service = NotificationService(tmp_path)
    resolved = service.create(
        "History_User",
        NotificationType.HUMAN_CAPTCHA,
        NotificationSeverity.CRITICAL,
        device="phone-1",
        tag="campaign",
        details="Verification required.",
    )
    service.resolve("history_user", NotificationType.HUMAN_CAPTCHA)
    active = service.create(
        "history_user",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.WARNING,
        details="No interactions.",
    )

    history = service.history_for_account(" HISTORY_USER ")

    assert [item.id for item in history] == [active.id, resolved.id]
    assert history[0].active is True
    assert history[1].active is False
    assert history[1].device == "phone-1"
    assert history[1].tag == "campaign"
    assert history[1].details == "Verification required."
    assert history[1].resolved_at is not None


def _identity(tmp_path):
    account_directory = tmp_path / "Accounts" / "example"
    account_directory.mkdir(parents=True, exist_ok=True)
    return {
        "account_directory": account_directory,
        "username": "example",
        "device": "phone-1",
        "tag": "",
    }


def _analytics_row(account_directory, clock, **counters):
    with AnalyticsDatabase(account_directory, clock=lambda: clock) as database:
        database.update_snapshot("example", posts=1, followers=2, following=3)
        for counter, amount in counters.items():
            if amount:
                database.increment("example", counter, amount)


def test_previous_utc_day_zero_creates_warning_once(tmp_path):
    identity = _identity(tmp_path)
    service = NotificationService(tmp_path)
    detector = ZeroInteractionsDetector(service)
    detector.register_account(**identity)
    now = datetime(2026, 11, 18, 8, tzinfo=UTC)
    _analytics_row(
        identity["account_directory"], datetime(2026, 11, 17, 20, tzinfo=UTC)
    )
    assert detector.evaluate_previous_day(**identity, now=now) == "created"
    assert detector.evaluate_previous_day(**identity, now=now) == "already_evaluated"
    notification = service.active()[0]
    assert notification.type is NotificationType.ZERO_INTERACTIONS
    assert notification.occurrences == 1


def test_positive_previous_day_resolves_warning(tmp_path):
    identity = _identity(tmp_path)
    service = NotificationService(tmp_path)
    service.create(
        "example", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.WARNING
    )
    detector = ZeroInteractionsDetector(service)
    _analytics_row(
        identity["account_directory"],
        datetime(2026, 11, 17, 20, tzinfo=UTC),
        liked=2,
        followed=1,
    )
    outcome = detector.evaluate_previous_day(
        **identity, now=datetime(2026, 11, 18, 8, tzinfo=UTC)
    )
    assert outcome == "resolved"
    assert service.active() == ()


def test_missing_database_or_previous_day_row_preserves_notification(tmp_path):
    identity = _identity(tmp_path)
    service = NotificationService(tmp_path)
    active = service.create(
        "example", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.WARNING
    )
    detector = ZeroInteractionsDetector(service)
    now = datetime(2026, 11, 18, 8, tzinfo=UTC)
    assert detector.evaluate_previous_day(**identity, now=now) == "no_database"
    _analytics_row(identity["account_directory"], now)
    assert detector.evaluate_previous_day(**identity, now=now) == "no_row"
    assert detector.evaluate_previous_day(**identity, now=now) == "already_evaluated"
    assert service.active()[0].id == active.id


def test_unreadable_analytics_preserves_notification_state(tmp_path):
    identity = _identity(tmp_path)
    analytics_path = identity["account_directory"] / "analytics.db"
    analytics_path.write_text("not sqlite", encoding="utf-8")
    service = NotificationService(tmp_path)
    active = service.create(
        "example", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.WARNING
    )

    with pytest.raises(sqlite3.DatabaseError):
        ZeroInteractionsDetector(service).evaluate_previous_day(
            **identity, now=datetime(2026, 11, 18, 8, tzinfo=UTC)
        )

    assert service.active()[0].id == active.id


def test_evaluated_date_survives_service_restart(tmp_path):
    identity = _identity(tmp_path)
    now = datetime(2026, 11, 18, 8, tzinfo=UTC)
    _analytics_row(identity["account_directory"], datetime(2026, 11, 17, tzinfo=UTC))
    first = ZeroInteractionsDetector(NotificationService(tmp_path))
    assert first.evaluate_previous_day(**identity, now=now) == "created"
    second = ZeroInteractionsDetector(NotificationService(tmp_path))
    assert second.evaluate_previous_day(**identity, now=now) == "already_evaluated"


def test_concurrent_startups_evaluate_date_once(tmp_path):
    identity = _identity(tmp_path)
    now = datetime(2026, 11, 18, 8, tzinfo=UTC)
    _analytics_row(identity["account_directory"], datetime(2026, 11, 17, tzinfo=UTC))

    def evaluate(_index):
        return ZeroInteractionsDetector(
            NotificationService(tmp_path)
        ).evaluate_previous_day(**identity, now=now)

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(evaluate, range(4)))
    assert outcomes.count("created") == 1
    assert outcomes.count("already_evaluated") == 3
    assert NotificationService(tmp_path).active()[0].occurrences == 1


def test_previous_day_critical_evidence_suppresses_zero_warning(tmp_path):
    identity = _identity(tmp_path)
    service = NotificationService(tmp_path)
    detector = ZeroInteractionsDetector(service)
    now = datetime.now(UTC)
    previous = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=1
    )
    _analytics_row(identity["account_directory"], previous)
    service.create(
        "example", NotificationType.HUMAN_CAPTCHA, NotificationSeverity.CRITICAL
    )
    with sqlite3.connect(tmp_path / "Notifications" / "notifications.db") as connection:
        timestamp = previous.isoformat()
        connection.execute(
            "UPDATE notifications SET detected_at = ?, last_detected_at = ?",
            (timestamp, timestamp),
        )
    assert (
        detector.evaluate_previous_day(**identity, now=now) == "suppressed_by_critical"
    )
    assert all(
        item.type is not NotificationType.ZERO_INTERACTIONS for item in service.active()
    )


def test_verified_interaction_counter_is_independent_from_analytics(tmp_path):
    from uuid import uuid4

    from IGBot.runtime.analytics import increment_analytics
    from IGBot.runtime.context import RuntimeContext
    from IGBot.runtime.ignore import IgnoreService
    from IGBot.runtime.session.models import SessionContext

    class Logger:
        def warning(self, *_args, **_kwargs):
            raise AssertionError("analytics should not be called")

    session = SessionContext(
        uuid4(), "example", "phone", "app", tmp_path, datetime.now(UTC)
    )
    context = RuntimeContext(session, Logger(), ignore_service=IgnoreService())
    increment_analytics(context, "liked", 2)
    assert context.verified_interactions == 2
