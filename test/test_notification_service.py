import sqlite3

from IGBot.notifications import (
    NotificationService,
    NotificationSeverity,
    NotificationType,
    ZeroInteractionsDetector,
)


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
        "example",
        NotificationType.ZERO_INTERACTIONS,
        NotificationSeverity.INFO,
    )

    assert service.count_active() == 1
    assert service.count_active(badge_only=True) == 0


def test_zero_interactions_requires_two_completed_sessions_and_resolves(tmp_path):
    account_directory = tmp_path / "Accounts" / "example"
    account_directory.mkdir(parents=True)
    service = NotificationService(tmp_path)
    detector = ZeroInteractionsDetector(service)
    identity = {
        "account_directory": account_directory,
        "username": "example",
        "device": "phone-1",
        "tag": "",
    }
    detector.register_account(**identity)

    database_path = tmp_path / "Notifications" / "notifications.db"
    with sqlite3.connect(database_path) as connection:
        first_success = connection.execute(
            "SELECT first_successful_session_at FROM account_lifecycle"
        ).fetchone()[0]
    assert first_success is None

    detector.record_completed_session(**identity, verified_interactions=0)
    assert service.active() == ()
    with sqlite3.connect(database_path) as connection:
        first_success = connection.execute(
            "SELECT first_successful_session_at FROM account_lifecycle"
        ).fetchone()[0]
    assert first_success is not None

    detector.record_completed_session(**identity, verified_interactions=0)
    assert service.active()[0].type is NotificationType.ZERO_INTERACTIONS

    detector.record_completed_session(**identity, verified_interactions=0)
    assert service.active()[0].occurrences == 2

    detector.record_completed_session(**identity, verified_interactions=1)
    assert service.active() == ()
    assert len(service.resolved()) == 1


def test_verified_interaction_counter_is_independent_from_analytics(tmp_path):
    from datetime import UTC, datetime
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
