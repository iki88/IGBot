"""Isolated orchestration of the existing InstaAddict runtime."""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import yaml

from IGBot.core.device import AssignedAccount
from IGBot.core.phone_manager import PhoneManager

logger = logging.getLogger(__name__)
_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")


class SessionState(StrEnum):
    IDLE = "Idle"
    STARTING = "Starting"
    RUNNING = "Running"
    WAITING = "Waiting"
    STOPPING = "Stopping"
    STOPPED = "Stopped"
    ERROR = "Error"


class SessionValidationError(ValueError):
    """Raised when an account cannot safely be handed to InstaAddict."""


class SessionEngine:
    """Run one account in an isolated InstaAddict subprocess."""

    def __init__(
        self,
        account: AssignedAccount,
        workspace_root: Path,
        *,
        process_factory=subprocess.Popen,
        device_validator=PhoneManager.is_connected,
    ) -> None:
        self.account = account
        self.workspace_root = workspace_root.resolve()
        self._process_factory = process_factory
        self._device_validator = device_validator
        self._process: subprocess.Popen | None = None
        self._state = SessionState.IDLE
        self._stop_requested = False

    @property
    def state(self) -> SessionState:
        return self._state

    def validate(self) -> None:
        path = self.account.config_path.resolve()
        try:
            path.relative_to(self.workspace_root)
        except ValueError as error:
            raise SessionValidationError(
                "Account configuration is outside IGBot."
            ) from error
        if not path.is_file():
            raise SessionValidationError("Account configuration does not exist.")
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise SessionValidationError(
                f"Account configuration is invalid: {error}"
            ) from error
        if not isinstance(config, dict):
            raise SessionValidationError(
                "Account configuration must be a YAML mapping."
            )
        if str(config.get("username", "")).strip() != self.account.username:
            raise SessionValidationError(
                "Account username does not match its configuration."
            )
        if str(config.get("device", "")).strip() != self.account.device_id:
            raise SessionValidationError(
                "Account device assignment is missing or ambiguous."
            )
        app_id = str(config.get("app-id") or config.get("app_id") or "").strip()
        if not app_id or not _PACKAGE_PATTERN.fullmatch(app_id):
            raise SessionValidationError("A valid Application ID is required.")
        if not self._device_validator(self.account.device_id):
            raise SessionValidationError(
                "The assigned Android device is not connected or authorized."
            )

    def start(self, state_changed: Callable[[SessionState], None]) -> None:
        if self._state in {
            SessionState.STARTING,
            SessionState.RUNNING,
            SessionState.STOPPING,
        }:
            raise RuntimeError("This account runtime is already active.")
        self._set_state(SessionState.STARTING, state_changed)
        try:
            self.validate()
            logger.info("Runtime validation succeeded for %s", self.account.username)
            command = [
                sys.executable,
                "-u",
                "-m",
                "InstaAddict",
                "run",
                "--config",
                str(self.account.config_path.resolve()),
            ]
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            logger.info("Launching InstaAddict runtime for %s", self.account.username)
            self._process = self._process_factory(
                command,
                cwd=str(self.workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
            self._set_state(SessionState.RUNNING, state_changed)
            if self._process.stdout is not None:
                for line in self._process.stdout:
                    message = line.rstrip()
                    if message:
                        logger.info("[%s] %s", self.account.username, message)
            exit_code = self._process.wait()
            if exit_code == 0 or (self._stop_requested and exit_code in {0, 2}):
                self._set_state(SessionState.STOPPED, state_changed)
                logger.info("Runtime stopped for %s", self.account.username)
            else:
                raise RuntimeError(f"InstaAddict exited with code {exit_code}.")
        except Exception:
            self._set_state(SessionState.ERROR, state_changed)
            logger.exception("Runtime failed for %s", self.account.username)
            raise
        finally:
            self._process = None
            self._stop_requested = False

    def run(self, state_changed: Callable[[SessionState], None]) -> None:
        """Compatibility entry point for worker and direct callers."""
        self.start(state_changed)

    def request_stop(self, state_changed: Callable[[SessionState], None]) -> None:
        process = self._process
        if (
            self._state not in {SessionState.STARTING, SessionState.RUNNING}
            or process is None
        ):
            raise RuntimeError("This account runtime is not running.")
        self._stop_requested = True
        self._set_state(SessionState.STOPPING, state_changed)
        logger.info("Stopping runtime for %s", self.account.username)
        process.send_signal(
            signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
        )

    def _set_state(
        self, state: SessionState, callback: Callable[[SessionState], None]
    ) -> None:
        self._state = state
        callback(state)
