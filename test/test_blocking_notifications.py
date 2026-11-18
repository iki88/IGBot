from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from IGBot.notifications import (
    AndroidBlockingScreenDetector,
    BlockingScreenMonitor,
    NotificationService,
    NotificationSeverity,
    NotificationType,
)
from IGBot.notifications.database import NotificationsDatabase
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.session import SessionContext
from IGBot.runtime.state import SessionState

SNAPSHOTS = Path("snapshots/R5CR61HA38V")


class _Logger:
    def __init__(self):
        self.records = []

    def debug(self, message, **fields):
        self.records.append(("DEBUG", message, fields))

    def info(self, message, **fields):
        self.records.append(("INFO", message, fields))

    def warning(self, message, **fields):
        self.records.append(("WARNING", message, fields))

    def error(self, message, **fields):
        self.records.append(("ERROR", message, fields))


def _context(tmp_path, package):
    return RuntimeContext(
        SessionContext(
            uuid4(),
            "blocked.account",
            "phone-1",
            package,
            tmp_path,
            datetime.now(UTC),
        ),
        _Logger(),
    )


@pytest.mark.parametrize(
    ("filename", "package", "expected"),
    (
        (
            "2026-10-02_16-56-09.xml",
            "com.instagram.androio",
            NotificationType.HUMAN_CAPTCHA,
        ),
        (
            "2026-10-13_14-07-23.xml",
            "com.instagram.androiq",
            NotificationType.ACCOUNT_DISABLED,
        ),
    ),
)
def test_production_blocking_screens_are_detected(filename, package, expected):
    hierarchy = (SNAPSHOTS / filename).read_text(encoding="utf-8")

    detection = AndroidBlockingScreenDetector.detect(hierarchy, package)

    assert detection is not None
    assert detection.notification_type is expected
    assert detection.severity is NotificationSeverity.CRITICAL


def test_detector_requires_primary_and_clickable_secondary_evidence():
    primary_only = """<hierarchy><node package="com.instagram.android"
      text="Confirm you're human to use your account, somebody" /></hierarchy>"""
    generic_continue = """<hierarchy>
      <node package="com.instagram.android" text="A normal screen" />
      <node package="com.instagram.android" class="android.widget.Button"
       clickable="true" content-desc="Continue" />
    </hierarchy>"""

    assert AndroidBlockingScreenDetector.detect(
        primary_only, "com.instagram.android"
    ) is None
    assert AndroidBlockingScreenDetector.detect(
        generic_continue, "com.instagram.android"
    ) is None


def test_detector_supports_text_variants_and_rejects_package_mismatch():
    hierarchy = """<hierarchy>
      <node package="clone.instagram" content-desc="  WE SUSPENDED YOUR ACCOUNT, Name " />
      <node package="clone.instagram" class="android.widget.Button"
       clickable="true" text=" Appeal " />
    </hierarchy>"""

    detection = AndroidBlockingScreenDetector.detect(hierarchy, "clone.instagram")

    assert detection is not None
    assert detection.notification_type is NotificationType.ACCOUNT_DISABLED
    assert AndroidBlockingScreenDetector.detect(
        hierarchy, "com.instagram.android"
    ) is None


def test_blocking_history_uses_local_date_and_includes_resolved_rows(tmp_path):
    service = NotificationService(tmp_path)
    notification = service.create(
        "blocked.account",
        NotificationType.HUMAN_CAPTCHA,
        NotificationSeverity.CRITICAL,
    )
    with NotificationsDatabase(tmp_path) as database:
        database.connection.execute(
            "UPDATE notifications SET last_detected_at = ? WHERE id = ?",
            ("2026-10-13T22:30:00+00:00", notification.id),
        )
        database.connection.commit()
    service.resolve("blocked.account", NotificationType.HUMAN_CAPTCHA)

    plus_two = timezone(timedelta(hours=2))
    assert service.blocking_detected_on_local_date(
        "blocked.account",
        datetime(2026, 10, 14, tzinfo=plus_two).date(),
        timezone=plus_two,
    )


def test_resolve_all_for_account_does_not_affect_other_accounts(tmp_path):
    service = NotificationService(tmp_path)
    service.create(
        "archived", NotificationType.ACCOUNT_DISABLED, NotificationSeverity.CRITICAL
    )
    service.create(
        "other", NotificationType.ZERO_INTERACTIONS, NotificationSeverity.WARNING
    )

    assert service.resolve_all_for_account("ARCHIVED") == 1
    assert tuple(item.username for item in service.active()) == ("other",)


def test_runtime_monitor_blocks_session_and_reports_once_per_session(tmp_path):
    hierarchy = (SNAPSHOTS / "2026-10-02_16-56-09.xml").read_text(
        encoding="utf-8"
    )
    service = NotificationService(tmp_path)
    monitor = BlockingScreenMonitor(service, tag="warmup")
    context = _context(tmp_path, "com.instagram.androio")

    assert monitor.check(context, stage="Startup", hierarchy=hierarchy)
    assert monitor.check(context, stage="Recovery", hierarchy=hierarchy)

    notification = service.active()[0]
    assert context.session_state is SessionState.WAITING_FOR_OPERATOR
    assert notification.type is NotificationType.HUMAN_CAPTCHA
    assert notification.severity is NotificationSeverity.CRITICAL
    assert notification.username == "blocked.account"
    assert notification.device == "phone-1"
    assert notification.tag == "warmup"
    assert notification.occurrences == 1


def test_persistence_failure_still_blocks_session(tmp_path, mocker):
    hierarchy = (SNAPSHOTS / "2026-10-13_14-07-23.xml").read_text(
        encoding="utf-8"
    )
    service = NotificationService(tmp_path)
    mocker.patch.object(service, "create", side_effect=OSError("database locked"))
    monitor = BlockingScreenMonitor(service)
    context = _context(tmp_path, "com.instagram.androiq")

    assert monitor.check(context, stage="Follow", hierarchy=hierarchy)

    assert context.session_state is SessionState.WAITING_FOR_OPERATOR
    assert service.active() == ()
    assert any(
        message == "Blocking notification persistence failed"
        for _level, message, _fields in context.logger.records
    )


def test_automatic_resolution_emits_one_refresh_callback(tmp_path):
    service = NotificationService(tmp_path)
    service.create(
        "blocked.account",
        NotificationType.HUMAN_CAPTCHA,
        NotificationSeverity.CRITICAL,
    )
    refreshed = []
    monitor = BlockingScreenMonitor(
        service,
        device_factory=lambda _serial: type(
            "Device", (), {"dump_hierarchy": lambda self, **_kwargs: "<hierarchy />"}
        )(),
        notifications_changed=lambda: refreshed.append(True),
    )
    context = _context(tmp_path, "com.instagram.androio")

    monitor.resolve_after_verified_startup(context)

    assert refreshed == [True]
    assert service.active() == ()
