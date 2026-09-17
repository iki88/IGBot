"""Persistent, single-runtime scheduler for one managed Android phone."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
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


class RuntimeMode(StrEnum):
    """Explicit account-runtime selection; native execution is authoritative."""

    NATIVE = "native"
    LEGACY = "legacy"


class PhoneScheduler:
    """Own the lifecycle and sequential account selection for one phone."""

    _APPLICATION_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")

    def __init__(
        self,
        device: DeviceRecord,
        workspace_root: Path,
        *,
        runtime_factory: Callable[..., object] | None = None,
        runtime_mode: RuntimeMode = RuntimeMode.NATIVE,
        device_validator: Callable[[str], bool] = PhoneManager.is_connected,
        clock: Callable[[], datetime] = datetime.now,
        decision_interval: float = 30.0,
    ) -> None:
        self.device = device
        self.workspace_root = workspace_root
        self._runtime_mode = runtime_mode
        if runtime_factory is not None:
            self._runtime_factory = runtime_factory
        elif runtime_mode is RuntimeMode.LEGACY:
            self._runtime_factory = SessionEngine
        else:
            from IGBot.runtime.native_integration import create_native_runtime

            self._runtime_factory = create_native_runtime
        self._device_validator = device_validator
        self._clock = clock
        self._decision_interval = decision_interval
        self._stop_event = threading.Event()
        self._runtime: object | None = None
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
        runtime_failed: Callable[[str], None] | None = None,
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
            scheduling_cycle = 0
            while not self._stop_event.is_set():
                scheduling_cycle += 1
                now = self._clock()
                logger.info(
                    "Scheduling cycle %d evaluating accounts at %s",
                    scheduling_cycle,
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                )
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
                logger.info(
                    "%s for %s",
                    (
                        "Launching legacy InstaAddict compatibility runtime"
                        if self._runtime_mode is RuntimeMode.LEGACY
                        else "Starting Native Runtime"
                    ),
                    account.username,
                )
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
                    if runtime_failed is not None:
                        runtime_failed(f"{account.username}: {error}")
                finally:
                    self._runtime = None
                if decision.session_key is not None:
                    self._completed_sessions.add(decision.session_key)
                if not self._stop_event.is_set():
                    logger.info(
                        "Scheduling cycle %d completed; waiting %.1f seconds",
                        scheduling_cycle,
                        self._decision_interval,
                    )
                    self._set_state(SessionState.WAITING, state_changed)
                    self._stop_event.wait(self._decision_interval)
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
            configuration, readiness_failure = self._runtime_configuration(account)
            if readiness_failure is not None:
                logger.info(
                    "Skipping account %s (not runtime-ready: %s)",
                    account.username,
                    readiness_failure,
                )
                continue
            windows = self._load_windows(account, configuration)
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
            if available_keys:
                logger.info(
                    "Deferring eligible account %s to the next scheduling cycle",
                    account.username,
                )
                if next_session is None or now < next_session:
                    next_session = now
                continue
            upcoming = min(self._next_start(start, now) for start, _ in windows)
            logger.info(
                "Skipping account %s (next session %s)",
                account.username,
                upcoming.strftime("%H:%M"),
            )
            if next_session is None or upcoming < next_session:
                next_session = upcoming
        return ScheduleDecision(selected, next_session, selected_key)

    @classmethod
    def _valid_application_id(cls, value: object) -> bool:
        return bool(cls._APPLICATION_ID.fullmatch(str(value or "").strip()))

    def _runtime_configuration(
        self, account: AssignedAccount
    ) -> tuple[dict | None, str | None]:
        if account.device_id != self.device.serial:
            return None, "phone assignment does not match"
        if not self._valid_application_id(account.app_id):
            return None, "no valid Application ID configured"
        try:
            configuration = yaml.safe_load(
                account.config_path.read_text(encoding="utf-8")
            )
            metadata = json.loads(
                (account.config_path.parent / "account.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, yaml.YAMLError, json.JSONDecodeError) as error:
            return None, f"account configuration is unavailable: {error}"
        if not isinstance(configuration, dict) or not isinstance(metadata, dict):
            return None, "account configuration is incomplete"
        if str(configuration.get("username") or "").strip() != account.username:
            return None, "configured username does not match account identity"
        configured_device = str(configuration.get("device") or "").strip()
        assigned_device = str(metadata.get("assigned_device_id") or "").strip()
        if (
            configured_device != self.device.serial
            or assigned_device != self.device.serial
        ):
            return None, "persisted phone assignment does not match"
        if not str(metadata.get("password") or ""):
            return None, "credentials are incomplete"
        configured_app = str(
            configuration.get("app-id") or configuration.get("app_id") or ""
        ).strip()
        if configured_app != account.app_id:
            return None, "persisted Application ID does not match inventory"
        if not self._native_configuration_ready(configuration):
            return None, "no enabled native module has complete configuration"
        directory = account.config_path.parent
        if not any(
            (directory / name).is_file() for name in ("runtime.db", "sessions.json")
        ):
            return None, "no completed onboarding/session history is available"
        return configuration, None

    @staticmethod
    def _native_configuration_ready(configuration: dict) -> bool:
        enabled = configuration.get("follow-percentage") not in (
            None,
            False,
            0,
            "",
            "0",
        )
        sources = configuration.get("blogger-followers")
        if isinstance(sources, str):
            configured = bool(sources.strip())
        elif isinstance(sources, list):
            configured = any(str(source).strip() for source in sources)
        else:
            configured = False
        return enabled and configured

    @staticmethod
    def _load_windows(
        account: AssignedAccount, config: dict | None = None
    ) -> tuple[tuple[int, int], ...]:
        if config is None:
            try:
                config = (
                    yaml.safe_load(account.config_path.read_text(encoding="utf-8"))
                    or {}
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
