"""Persistent, single-runtime scheduler for one managed Android phone."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from IGBot.core.device import AssignedAccount, DeviceRecord
from IGBot.core.phone_manager import PhoneManager
from IGBot.core.session_engine import SessionEngine, SessionState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class ScheduleDecision:
    selected: AssignedAccount | None
    next_session: datetime | None
    session_key: tuple[str, int, int, str] | None = None


class PhoneScheduler:
    """Own the lifecycle and sequential account selection for one phone."""

    def __init__(
        self,
        device: DeviceRecord,
        workspace_root: Path,
        *,
        runtime_factory: Callable[..., SessionEngine] = SessionEngine,
        device_validator: Callable[[str], bool] = PhoneManager.is_connected,
        clock: Callable[[], datetime] = datetime.now,
        decision_interval: float = 30.0,
    ) -> None:
        self.device = device
        self.workspace_root = workspace_root
        self._runtime_factory = runtime_factory
        self._device_validator = device_validator
        self._clock = clock
        self._decision_interval = decision_interval
        self._stop_event = threading.Event()
        self._runtime: SessionEngine | None = None
        self._state = SessionState.IDLE
        self._completed_sessions: set[tuple[str, int, int, str]] = set()
        self._schedule_date = None

    @property
    def state(self) -> SessionState:
        return self._state

    def start(
        self,
        state_changed: Callable[[SessionState], None],
        account_state_changed: Callable[[str, SessionState], None],
    ) -> None:
        if self._state in {
            SessionState.STARTING,
            SessionState.RUNNING,
            SessionState.WAITING,
            SessionState.STOPPING,
        }:
            raise RuntimeError("This phone scheduler is already active.")
        self._set_state(SessionState.STARTING, state_changed)
        try:
            if not self._device_validator(self.device.serial):
                raise ValueError("The Android phone is not connected or authorized.")
            accounts = tuple(self.device.accounts)
            logger.info("Phone Scheduler started for %s", self.device.serial)
            logger.info("Loaded %d assigned accounts", len(accounts))
            while not self._stop_event.is_set():
                now = self._clock()
                if self._schedule_date != now.date():
                    self._completed_sessions.clear()
                    self._schedule_date = now.date()
                decision = self.evaluate(accounts, now, self._completed_sessions)
                if decision.selected is None:
                    self._set_state(SessionState.WAITING, state_changed)
                    if decision.next_session is None:
                        logger.info(
                            "Scheduler waiting; no enabled sessions are configured"
                        )
                    else:
                        logger.info(
                            "Scheduler sleeping until next session at %s",
                            decision.next_session.strftime("%Y-%m-%d %H:%M"),
                        )
                    timeout = (
                        max(0.1, (decision.next_session - now).total_seconds())
                        if decision.next_session is not None
                        else self._decision_interval
                    )
                    self._stop_event.wait(timeout)
                    continue

                account = decision.selected
                logger.info("Selected account %s for execution", account.username)
                logger.info("Launching InstaAddict for %s", account.username)
                self._set_state(SessionState.RUNNING, state_changed)
                self._runtime = self._runtime_factory(account, self.workspace_root)
                try:
                    self._runtime.start(
                        lambda state, username=account.username: account_state_changed(
                            username, state
                        )
                    )
                except Exception as error:  # noqa: BLE001 - runtime isolation boundary
                    logger.error(
                        "Account session failed for %s: %s", account.username, error
                    )
                    account_state_changed(account.username, SessionState.ERROR)
                finally:
                    self._runtime = None
                if decision.session_key is not None:
                    self._completed_sessions.add(decision.session_key)
            self._set_state(SessionState.STOPPED, state_changed)
            logger.info("Phone Scheduler stopped for %s", self.device.serial)
        except Exception:
            self._set_state(SessionState.ERROR, state_changed)
            logger.exception("Phone Scheduler failed for %s", self.device.serial)
            raise

    def stop(self, state_changed: Callable[[SessionState], None]) -> None:
        if self._state not in {
            SessionState.STARTING,
            SessionState.RUNNING,
            SessionState.WAITING,
        }:
            raise RuntimeError("This phone scheduler is not running.")
        self._set_state(SessionState.STOPPING, state_changed)
        self._stop_event.set()
        runtime = self._runtime
        if runtime is not None and runtime.state in {
            SessionState.STARTING,
            SessionState.RUNNING,
        }:
            runtime.request_stop(lambda _: None)

    def evaluate(
        self,
        accounts: tuple[AssignedAccount, ...],
        now: datetime,
        completed: set[tuple[str, int, int, str]] | None = None,
    ) -> ScheduleDecision:
        completed = completed or set()
        selected = None
        selected_key = None
        next_session = None
        for account in accounts:
            windows = self._load_windows(account)
            if not windows or all(start == end == 0 for start, end in windows):
                logger.info("Skipping account %s (disabled)", account.username)
                continue
            eligible_keys = [
                (str(account.config_path.resolve()), start, end, now.date().isoformat())
                for start, end in windows
                if self._contains(start, end, now)
            ]
            available_keys = [key for key in eligible_keys if key not in completed]
            if available_keys and selected is None:
                selected = account
                selected_key = available_keys[0]
                continue
            upcoming = (
                now
                if available_keys
                else min(self._next_start(start, now) for start, _ in windows)
            )
            logger.info(
                "Skipping account %s (next session %s)",
                account.username,
                upcoming.strftime("%H:%M"),
            )
            if next_session is None or upcoming < next_session:
                next_session = upcoming
        return ScheduleDecision(selected, next_session, selected_key)

    @staticmethod
    def _load_windows(account: AssignedAccount) -> tuple[tuple[int, int], ...]:
        try:
            config = (
                yaml.safe_load(account.config_path.read_text(encoding="utf-8")) or {}
            )
        except (OSError, yaml.YAMLError) as error:
            logger.error(
                "Skipping account %s (invalid timer: %s)", account.username, error
            )
            return ()
        raw = config.get("working-hours") or []
        if isinstance(raw, str):
            raw = [raw]
        windows = []
        for value in raw:
            try:
                start, end = str(value).split("-", 1)
                windows.append(
                    (PhoneScheduler._minutes(start), PhoneScheduler._minutes(end))
                )
            except (TypeError, ValueError):
                logger.error(
                    "Ignoring invalid timer for %s: %s", account.username, value
                )
        return tuple(windows)

    @staticmethod
    def _minutes(value: str) -> int:
        hour, separator, minute = value.strip().partition(".")
        parsed_hour = int(hour)
        parsed_minute = int(minute) if separator else 0
        if not 0 <= parsed_hour <= 24 or not 0 <= parsed_minute <= 59:
            raise ValueError("invalid time")
        if parsed_hour == 24 and parsed_minute:
            raise ValueError("invalid time")
        return parsed_hour * 60 + parsed_minute

    @staticmethod
    def _contains(start: int, end: int, now: datetime) -> bool:
        current = now.hour * 60 + now.minute
        if start == end:
            return False
        if start < end:
            return start <= current < end
        return current >= start or current < end

    @staticmethod
    def _next_start(start: int, now: datetime) -> datetime:
        day = now.date() + (
            timedelta(days=1) if start <= now.hour * 60 + now.minute else timedelta()
        )
        if start == 24 * 60:
            day += timedelta(days=1)
            start = 0
        return datetime.combine(day, datetime.min.time()).replace(
            hour=start // 60, minute=start % 60
        )

    def _set_state(
        self, state: SessionState, callback: Callable[[SessionState], None]
    ) -> None:
        self._state = state
        callback(state)
