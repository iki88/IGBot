import logging
from datetime import datetime, timedelta, timezone

from IGBot.logging_v2 import (
    AccountDailyLogHandler,
    LiveLogLevelFilter,
    configure_logging,
    shutdown_logging,
)
from IGBot.runtime.native_integration import PythonRuntimeLogger


def test_queue_pipeline_separates_application_and_account_runtime_logs(tmp_path):
    account_directory = tmp_path / "Accounts" / "example"
    account_directory.mkdir(parents=True)
    service = configure_logging(tmp_path)
    try:
        logging.getLogger("IGBot.test.application").info("Application event")
        logging.getLogger("IGBot.test.application").debug("Application diagnostic")
        runtime = PythonRuntimeLogger(
            account_directory=account_directory,
            account_username="example",
            phone_id="PHONE-1",
            session_id="session-1",
            developer_mode=False,
        )
        runtime.session_started()
        runtime.debug("Suppressed runtime diagnostic")
        runtime.info("Runtime event")
        runtime.warning("Runtime warning")
        runtime.error("Runtime error")
        runtime.session_finished("Stopped")
        developer_runtime = PythonRuntimeLogger(
            account_directory=account_directory,
            account_username="example",
            phone_id="PHONE-1",
            session_id="session-debug",
            developer_mode=True,
        )
        developer_runtime.debug("Developer diagnostic detail")
        second_session = PythonRuntimeLogger(
            account_directory=account_directory,
            account_username="example",
            phone_id="PHONE-1",
            session_id="session-2",
        )
        second_session.session_started()
        second_session.session_finished("Stopped")
    finally:
        shutdown_logging()

    application = service.application_log_path.read_text(encoding="utf-8")
    assert "Application event" in application
    assert "Application diagnostic" in application
    assert "Runtime event" not in application
    assert service._application_handler.maxBytes == 10 * 1024 * 1024
    assert service._application_handler.backupCount == 5

    day = datetime.now(timezone.utc).date().isoformat()
    account_log = (account_directory / "Logs" / f"{day}.log").read_text(
        encoding="utf-8"
    )
    assert account_log.count("IGBot Native Runtime Log") == 1
    assert "Session Started" in account_log
    assert "Session Finished" in account_log
    assert account_log.count("Session Started") == 2
    assert account_log.count("Session Finished") == 2
    assert "Suppressed runtime diagnostic" not in account_log
    assert "Developer diagnostic detail" in account_log
    assert "Runtime event" in account_log
    assert "Runtime warning" in account_log
    assert "Runtime error" in account_log
    assert not list((account_directory / "Logs").glob("*.log.1"))


def test_account_daily_log_retention_keeps_thirty_utc_days(tmp_path):
    account_directory = tmp_path / "Accounts" / "example"
    logs = account_directory / "Logs"
    logs.mkdir(parents=True)
    today = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    expired = logs / f"{(today.date() - timedelta(days=30)).isoformat()}.log"
    retained = logs / f"{(today.date() - timedelta(days=29)).isoformat()}.log"
    expired.write_text("old", encoding="utf-8")
    retained.write_text("keep", encoding="utf-8")
    handler = AccountDailyLogHandler()
    record = logging.LogRecord(
        "IGBot.runtime",
        logging.INFO,
        __file__,
        1,
        "Current event",
        (),
        None,
    )
    record.created = today.timestamp()
    record.account_directory = str(account_directory)
    record.account_username = "example"

    handler.emit(record)

    assert not expired.exists()
    assert retained.exists()
    assert (logs / "2026-10-02.log").exists()


def test_live_log_debug_filter_uses_runtime_developer_mode():
    log_filter = LiveLogLevelFilter()
    info = logging.makeLogRecord({"levelno": logging.INFO})
    normal_debug = logging.makeLogRecord(
        {"levelno": logging.DEBUG, "developer_mode": False}
    )
    developer_debug = logging.makeLogRecord(
        {"levelno": logging.DEBUG, "developer_mode": True}
    )

    assert log_filter.filter(info)
    assert not log_filter.filter(normal_debug)
    assert log_filter.filter(developer_debug)
