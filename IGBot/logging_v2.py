"""Central asynchronous logging for the IGBot desktop and native runtime."""

from __future__ import annotations

import logging
import logging.handlers
import queue
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar

_DATE_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.log$")


class _ApplicationOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not bool(getattr(record, "account_directory", None))


class LiveLogLevelFilter(logging.Filter):
    """Hide DEBUG unless the emitting runtime is in developer mode."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO or bool(
            getattr(record, "developer_mode", False)
        )


class _AccountLogLevelFilter(logging.Filter):
    """Discard account DEBUG records unless that runtime enabled debugging."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO or bool(
            getattr(record, "developer_mode", False)
        )


class AccountDailyLogHandler(logging.Handler):
    """Write account runtime records to one non-rotating UTC daily file."""

    HEADER = (
        "IGBot Native Runtime Log\n"
        "Date (UTC): {date}\n"
        "Account: {account}\n"
        + "=" * 72
        + "\n"
    )
    RETENTION_DAYS = 30

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.addFilter(_AccountLogLevelFilter())
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        formatter.converter = time.gmtime
        self.setFormatter(formatter)
        self._cleaned: set[tuple[Path, str]] = set()

    def emit(self, record: logging.LogRecord) -> None:
        directory_value = getattr(record, "account_directory", None)
        if not directory_value:
            return
        try:
            account_directory = Path(str(directory_value))
            logs_directory = account_directory / "Logs"
            logs_directory.mkdir(parents=True, exist_ok=True)
            day = datetime.fromtimestamp(record.created, timezone.utc).date()
            day_text = day.isoformat()
            cleanup_key = (logs_directory.resolve(), day_text)
            if cleanup_key not in self._cleaned:
                self._remove_expired(logs_directory, day)
                self._cleaned.add(cleanup_key)
            path = logs_directory / f"{day_text}.log"
            is_new = not path.exists() or path.stat().st_size == 0
            with path.open("a", encoding="utf-8", newline="") as stream:
                if is_new:
                    stream.write(
                        self.HEADER.format(
                            date=day_text,
                            account=getattr(record, "account_username", ""),
                        )
                    )
                stream.write(self.format(record))
                stream.write("\n")
        except Exception:  # noqa: BLE001 - logging handlers must not escape emit
            self.handleError(record)

    @classmethod
    def _remove_expired(cls, logs_directory: Path, today) -> None:
        oldest = today - timedelta(days=cls.RETENTION_DAYS - 1)
        for path in logs_directory.glob("*.log"):
            match = _DATE_FILE.fullmatch(path.name)
            if match is None:
                continue
            try:
                file_day = date.fromisoformat(match.group(1))
                if file_day < oldest:
                    path.unlink(missing_ok=True)
            except (OSError, ValueError):
                continue


class _SubscriberHandler(logging.Handler):
    """Fan records out to in-memory subscribers from the listener thread."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self._subscribers: list[logging.Handler] = []
        self._lock = threading.RLock()

    def add(self, handler: logging.Handler) -> None:
        with self._lock:
            if handler not in self._subscribers:
                self._subscribers.append(handler)

    def remove(self, handler: logging.Handler) -> None:
        with self._lock:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for handler in subscribers:
            if record.levelno < handler.level:
                continue
            if all(log_filter.filter(record) for log_filter in handler.filters):
                handler.emit(record)


class LoggingService:
    """Own the process-wide queue and all persistent logging destinations."""

    _instance: ClassVar[LoggingService | None] = None

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self._queue: queue.Queue[logging.LogRecord] = queue.Queue()
        self._queue_handler = logging.handlers.QueueHandler(self._queue)
        self._previous_root_level = logging.getLogger().level

        application_directory = self.workspace / "IGBot" / "Logs"
        application_directory.mkdir(parents=True, exist_ok=True)
        self.application_log_path = application_directory / "application.log"
        self._application_handler = logging.handlers.RotatingFileHandler(
            self.application_log_path,
            mode="a",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        self._application_handler.setLevel(logging.DEBUG)
        self._application_handler.addFilter(_ApplicationOnlyFilter())
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        formatter.converter = time.gmtime
        self._application_handler.setFormatter(formatter)

        self._account_handler = AccountDailyLogHandler()
        self._subscribers = _SubscriberHandler()
        self._listener = logging.handlers.QueueListener(
            self._queue,
            self._application_handler,
            self._account_handler,
            self._subscribers,
            respect_handler_level=True,
        )
        self._started = False

    @classmethod
    def configure(cls, workspace: Path) -> LoggingService:
        if cls._instance is not None:
            return cls._instance
        service = cls(workspace)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        root.addHandler(service._queue_handler)
        service._listener.start()
        service._started = True
        cls._instance = service
        logging.getLogger(__name__).info("Logging v2 initialized")
        return service

    @classmethod
    def current(cls) -> LoggingService | None:
        return cls._instance

    def subscribe(self, handler: logging.Handler) -> None:
        self._subscribers.add(handler)

    def unsubscribe(self, handler: logging.Handler) -> None:
        self._subscribers.remove(handler)

    def shutdown(self) -> None:
        if not self._started:
            return
        logging.getLogger(__name__).info("Logging v2 shutting down")
        self._listener.stop()
        root = logging.getLogger()
        root.removeHandler(self._queue_handler)
        root.setLevel(self._previous_root_level)
        self._queue_handler.close()
        self._application_handler.close()
        self._account_handler.close()
        self._started = False
        if type(self)._instance is self:
            type(self)._instance = None


def configure_logging(workspace: Path) -> LoggingService:
    return LoggingService.configure(workspace)


def shutdown_logging() -> None:
    service = LoggingService.current()
    if service is not None:
        service.shutdown()
