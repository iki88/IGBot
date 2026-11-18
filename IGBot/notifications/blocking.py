"""Pure Android blocking-screen detection and native runtime coordination."""

from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from IGBot.notifications.models import NotificationSeverity, NotificationType
from IGBot.notifications.service import NotificationService
from IGBot.runtime.state import SessionState

if TYPE_CHECKING:
    from IGBot.runtime.context import RuntimeContext


@dataclass(frozen=True, slots=True)
class BlockingScreenDetection:
    notification_type: NotificationType
    severity: NotificationSeverity
    primary_evidence: str
    secondary_evidence: str


class BlockingScreenActive(RuntimeError):
    """Abort the current Android operation after a confirmed blocker."""


class BlockingAwareDevice:
    """Delegate a UIAutomator device while guarding captured hierarchies."""

    def __init__(self, device: object, context: RuntimeContext) -> None:
        self._device = device
        self._context = context

    def dump_hierarchy(self, *args, **kwargs):
        hierarchy = self._device.dump_hierarchy(*args, **kwargs)
        checkpoint = getattr(self._context, "blocking_screen_checkpoint", None)
        if checkpoint is not None and checkpoint(
            "Android hierarchy inspection", hierarchy=hierarchy
        ):
            raise BlockingScreenActive("Instagram requires operator action.")
        return hierarchy

    def __getattr__(self, name: str):
        return getattr(self._device, name)


class AndroidBlockingScreenDetector:
    """Recognize confirmed native Instagram blockers without side effects."""

    _RULES = (
        (
            NotificationType.HUMAN_CAPTCHA,
            "confirm you're human to use your account",
            "continue",
        ),
        (
            NotificationType.ACCOUNT_DISABLED,
            "we suspended your account",
            "appeal",
        ),
    )

    @classmethod
    def detect(
        cls, hierarchy: str, expected_package: str
    ) -> BlockingScreenDetection | None:
        expected_package = expected_package.strip().casefold()
        if not hierarchy.strip() or not expected_package:
            return None
        try:
            root = ET.fromstring(hierarchy)
        except ET.ParseError:
            return None
        nodes = tuple(
            node
            for node in root.iter("node")
            if cls._normalize(node.get("package", "")) == expected_package
        )
        if not nodes:
            return None
        for notification_type, primary, action in cls._RULES:
            primary_node = next(
                (
                    node
                    for node in nodes
                    if any(
                        primary in cls._normalize(node.get(attribute, ""))
                        for attribute in ("text", "content-desc")
                    )
                ),
                None,
            )
            action_node = next(
                (
                    node
                    for node in nodes
                    if node.get("clickable", "").casefold() == "true"
                    and node.get("class", "").rsplit(".", 1)[-1] == "Button"
                    and any(
                        cls._normalize(node.get(attribute, "")) == action
                        for attribute in ("text", "content-desc")
                    )
                ),
                None,
            )
            if primary_node is not None and action_node is not None:
                return BlockingScreenDetection(
                    notification_type,
                    NotificationSeverity.CRITICAL,
                    primary,
                    action,
                )
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()


class InProcessBlockingRetryRegistry:
    """Process-local safety fallback when notification persistence is unavailable."""

    _lock = threading.Lock()
    _dates: ClassVar[dict[str, object]] = {}

    @classmethod
    def record_today(cls, username: str) -> None:
        with cls._lock:
            cls._dates[username.strip().casefold()] = (
                datetime.now().astimezone().date()
            )

    @classmethod
    def blocked_on(cls, username: str, local_date) -> bool:
        with cls._lock:
            return cls._dates.get(username.strip().casefold()) == local_date

    @classmethod
    def discard(cls, username: str) -> None:
        """Forget process-local retry state for exactly one account username."""

        with cls._lock:
            cls._dates.pop(username.strip().casefold(), None)


class BlockingScreenMonitor:
    """Coordinate detection, persistence, logging, and account-session blocking."""

    def __init__(
        self,
        service: NotificationService | None,
        *,
        tag: str = "",
        device_factory: Callable[[str], object] | None = None,
        notifications_changed: Callable[[], None] | None = None,
    ) -> None:
        self._service = service
        self._tag = tag
        self._device_factory = device_factory or self._connect
        self._notifications_changed = notifications_changed or (lambda: None)
        self._reported: set[NotificationType] = set()

    def set_notifications_changed_callback(
        self, callback: Callable[[], None] | None
    ) -> None:
        self._notifications_changed = callback or (lambda: None)

    def check(
        self,
        context: RuntimeContext,
        *,
        stage: str,
        hierarchy: str | None = None,
    ) -> bool:
        try:
            if hierarchy is None:
                device = self._device_factory(context.session.phone_id)
                hierarchy = device.dump_hierarchy(compressed=False)
            detection = AndroidBlockingScreenDetector.detect(
                hierarchy, context.session.application_id
            )
        except Exception as error:  # noqa: BLE001 - diagnostic guard boundary
            context.logger.debug(
                "Blocking-screen inspection unavailable", stage=stage, detail=str(error)
            )
            return False
        if detection is None:
            return False

        InProcessBlockingRetryRegistry.record_today(
            context.session.account_username
        )
        context.session_state = SessionState.WAITING_FOR_OPERATOR
        context.logger.error(
            "Blocking Instagram screen detected",
            notification_type=detection.notification_type.value,
            stage=stage,
        )
        if detection.notification_type not in self._reported:
            try:
                if self._service is None:
                    raise RuntimeError("Notification persistence is unavailable")
                self._service.create(
                    context.session.account_username,
                    detection.notification_type,
                    detection.severity,
                    device=context.session.phone_id,
                    tag=self._tag,
                    details=(
                        f"Detected during {stage}. Operator action is required; "
                        "IGBot did not interact with the blocking screen."
                    ),
                )
                self._reported.add(detection.notification_type)
            except Exception as error:  # noqa: BLE001 - safety survives persistence
                context.logger.error(
                    "Blocking notification persistence failed",
                    notification_type=detection.notification_type.value,
                    detail=f"{type(error).__name__}: {error}",
                )
        return True

    def resolve_after_verified_startup(self, context: RuntimeContext) -> None:
        """Resolve blockers only after the complete startup pipeline succeeds."""

        if self.check(context, stage="Verified startup resolution"):
            return
        if self._service is None:
            context.logger.warning("Blocking notification resolution unavailable")
            return
        try:
            resolved = self._service.resolve_blocking_for_account(
                context.session.account_username
            )
        except Exception as error:  # noqa: BLE001 - notification isolation boundary
            context.logger.warning(
                "Blocking notification resolution failed", detail=str(error)
            )
            return
        if resolved:
            context.logger.info("Resolved blocking account notification", count=resolved)
            try:
                self._notifications_changed()
            except Exception as error:  # noqa: BLE001 - UI notification isolation
                context.logger.warning(
                    "Notification UI refresh request failed", detail=str(error)
                )
        username = context.session.account_username
        today = datetime.now().astimezone().date()
        if not InProcessBlockingRetryRegistry.blocked_on(username, today):
            InProcessBlockingRetryRegistry.discard(username)

    @staticmethod
    def _connect(serial: str) -> object:
        import uiautomator2 as u2

        return u2.connect(serial)
