from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.core.session_engine import SessionState
from IGBot.runtime.candidates import Candidate, CandidateProviderType
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.follow import (
    AndroidFollowResult,
    AndroidFollowStatus,
    CandidateProfile,
    FollowModuleResult,
    FollowModuleResultStatus,
)
from IGBot.runtime.follow.daily_limits import successful_follows_today
from IGBot.runtime.follower_synchronization import RuntimeFollowerComparer
from IGBot.runtime.native_integration import (
    NativeAccountRuntime,
    PythonRuntimeLogger,
    _FollowModuleProvider,
    _NativeFollowExecutor,
    _ProfilePersistence,
)
from IGBot.runtime.profile_database import GlobalDatabaseWriter
from IGBot.runtime.scheduler import ModuleExecutionResult
from IGBot.runtime.session import SessionContext
from IGBot.runtime.state import ModuleState
from IGBot.ui.widgets.live_log_panel import LiveLogPanel


def _account(tmp_path):
    config = tmp_path / "phones" / "PHONE" / "accounts" / "alice" / "config.yml"
    config.parent.mkdir(parents=True)
    config.write_text("username: alice\n", encoding="utf-8")
    return AssignedAccount("alice", "PHONE", "com.instagram.android", config)


def test_native_account_runtime_starts_and_stops_without_subprocess(tmp_path):
    started = threading.Event()
    controller_calls = []
    holder = {}

    class Controller:
        def start(self, context):
            controller_calls.append(context)
            started.set()
            holder["runtime"]._stop_event.wait(timeout=2)
            return SimpleNamespace(startup_result=SimpleNamespace(startup_failed=False))

    runtime = NativeAccountRuntime(
        _account(tmp_path), tmp_path, controller=Controller()
    )
    holder["runtime"] = runtime
    states = []
    worker = threading.Thread(target=runtime.start, args=(states.append,))

    worker.start()
    assert started.wait(timeout=2)
    runtime.request_stop(states.append)
    worker.join(timeout=2)

    assert len(controller_calls) == 1
    assert controller_calls[0].account_username == "alice"
    assert states == [
        SessionState.STARTING,
        SessionState.STOPPING,
        SessionState.STOPPED,
    ]
    assert not worker.is_alive()


def test_native_account_runtime_propagates_controller_exception(tmp_path):
    class Controller:
        def start(self, _context):
            raise RuntimeError("startup failed visibly")

    runtime = NativeAccountRuntime(
        _account(tmp_path), tmp_path, controller=Controller()
    )
    states = []

    with pytest.raises(RuntimeError, match="startup failed visibly"):
        runtime.start(states.append)

    assert states == [SessionState.STARTING, SessionState.ERROR]


def test_runtime_diagnostics_reach_existing_live_log_in_order():
    application = QApplication.instance() or QApplication([])
    panel = LiveLogPanel()
    runtime_logger = PythonRuntimeLogger()
    messages = (
        ("info", "Startup stage started", {"stage": "StartupPipeline"}),
        ("debug", "[Search] Waiting for search results", {}),
        ("info", "[Search] Source profile opened", {"source": "source_user"}),
        ("info", "[Followers] Followers list opened", {}),
        ("info", "[Candidate] Opening candidate profile", {}),
        ("info", "[Candidate] Profile verified", {"username": "candidate"}),
    )

    try:
        for level, message, fields in messages:
            getattr(runtime_logger, level)(message, **fields)
        application.processEvents()
        lines = panel.output.toPlainText().splitlines()
    finally:
        panel.detach_logging()

    expected = [message for _level, message, _fields in messages]
    positions = [
        next(i for i, line in enumerate(lines) if message in line)
        for message in expected
    ]
    assert positions == sorted(positions)
    for message in expected:
        matching = [line for line in lines if message in line]
        assert len(matching) == 1
        assert re.match(r"\d{2}:\d{2}:\d{2}\s+\w+\s+", matching[0])


@pytest.mark.parametrize(
    ("android_status", "global_status", "android_muted"),
    [
        (AndroidFollowStatus.SUCCESS, "following", False),
        (AndroidFollowStatus.SUCCESS, "following", True),
        (AndroidFollowStatus.REQUESTED, "requested", False),
    ],
)
def test_verified_follow_persists_global_and_account_history_without_duplicates(
    tmp_path, android_status, global_status, android_muted
):
    account_directory = tmp_path / "account"
    candidate = Candidate("target_user", "source_user", CandidateProviderType.FOLLOWERS)
    session = SessionContext(
        uuid4(),
        "alice",
        "PHONE",
        "com.instagram.android",
        account_directory,
        datetime.now(timezone.utc),
    )
    context = RuntimeContext(session, PythonRuntimeLogger())
    prepared = ModuleExecutionResult(
        True,
        True,
        ModuleState.READY,
        module_result=FollowModuleResult(
            FollowModuleResultStatus.READY_TO_FOLLOW, candidate
        ),
    )

    class Module:
        state = ModuleState.READY

        def execute(self, _context, _budget):
            return prepared

        def cancellation_requested(self):
            return False

        def complete_verified_follow(self):
            return None

    class Android:
        def execute_follow(self, _context):
            return AndroidFollowResult(android_status, muted=android_muted)

    writer = GlobalDatabaseWriter(tmp_path)
    persistence = _ProfilePersistence(writer)
    persistence.submit(CandidateProfile(candidate, candidate.username))
    executor = _NativeFollowExecutor(None, Android(), persistence)
    try:
        executor.execute(context, Module(), None)
        executor.execute(context, Module(), None)
        writer.flush()
    finally:
        writer.close()

    with sqlite3.connect(tmp_path / "global_profiles.db") as connection:
        assert connection.execute(
            "SELECT follow_status FROM profiles WHERE username = ?",
            (candidate.username,),
        ).fetchone() == (global_status,)

    with RuntimeDatabase(account_directory) as database:
        user = database.users.get_by_username(candidate.username)
        assert user is not None
        assert user.first_discovered_by == "FOLLOW"
        record = database.follow.get(user.id)
        assert record is not None
        assert record.source == candidate.source
        assert record.username == candidate.username
        assert record.muted is android_muted
        assert record.follow_date is not None
        assert "T" not in record.follow_date
        assert record.last_session_id == str(session.session_id)
        comparison = RuntimeFollowerComparer().compare(
            (candidate.username,),
            database.users,
            database.follow,
            datetime.now(timezone.utc),
        )
        assert len(comparison.follow_back_updates) == 1
    with sqlite3.connect(account_directory / "runtime.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM follow").fetchone()[0] == 1


def test_specific_follow_persists_only_specific_history(tmp_path):
    account_directory = tmp_path / "account"
    candidate = Candidate(
        "specific_user",
        "specific_users",
        CandidateProviderType.SPECIFIC_ACCOUNTS,
    )
    context = RuntimeContext(
        SessionContext(
            uuid4(),
            "alice",
            "PHONE",
            "com.instagram.android",
            account_directory,
            datetime.now(timezone.utc),
        ),
        PythonRuntimeLogger(),
    )
    prepared = ModuleExecutionResult(
        True,
        True,
        ModuleState.READY,
        module_result=FollowModuleResult(
            FollowModuleResultStatus.READY_TO_FOLLOW, candidate
        ),
    )

    class Module:
        state = ModuleState.READY

        def __init__(self):
            self.processed = []

        def execute(self, _context, _budget):
            return prepared

        def cancellation_requested(self):
            return False

        def complete_verified_follow(self):
            return None

        def mark_candidate_processed(self, _context, processed_candidate):
            self.processed.append(processed_candidate)

    class Android:
        def execute_follow(self, _context):
            return AndroidFollowResult(AndroidFollowStatus.SUCCESS, muted=True)

    writer = GlobalDatabaseWriter(tmp_path)
    persistence = _ProfilePersistence(writer)
    persistence.submit(CandidateProfile(candidate, candidate.username))
    module = Module()
    try:
        _NativeFollowExecutor(None, Android(), persistence).execute(
            context, module, None
        )
    finally:
        writer.close()

    assert module.processed == [candidate]
    with sqlite3.connect(account_directory / "runtime.db") as connection:
        connection.row_factory = sqlite3.Row
        assert connection.execute("SELECT COUNT(*) FROM follow").fetchone()[0] == 0
        row = connection.execute("SELECT * FROM specific_follow").fetchone()
        assert row["username"] == "specific_user"
        assert row["status"] == "SUCCESS"
        assert row["muted"] == 1
        assert row["follow_date"]


def test_follow_daily_remaining_uses_persisted_successes_after_limit_change(tmp_path):
    account_directory = tmp_path / "account"
    now = datetime.now(timezone.utc)
    context = RuntimeContext(
        SessionContext(
            uuid4(),
            "alice",
            "PHONE",
            "com.instagram.android",
            account_directory,
            now,
        ),
        PythonRuntimeLogger(),
    )
    with RuntimeDatabase(account_directory) as database:
        first = database.users.create("first_target", now, "FOLLOW")
        second = database.users.create("second_target", now, "FOLLOW")
        database.follow.save(
            FollowRecord(
                first.id,
                first.username,
                source="source",
                follow_date=now.isoformat(),
            )
        )
        database.follow.save(
            FollowRecord(
                second.id,
                second.username,
                source="source",
                follow_date=now.isoformat(),
            )
        )

    def module_for(daily_limit):
        provider = _FollowModuleProvider(
            {
                "follow-percentage": 100,
                "follow-limit": 1,
                "total-follows-limit": daily_limit,
                "blogger-followers": ["source"],
            },
            {},
            {},
            SimpleNamespace(),
            SimpleNamespace(),
        )
        return next(iter(provider.modules_for(context)))

    assert module_for(3).daily_remaining == 1
    assert module_for(5).daily_remaining == 3


def test_daily_follow_count_includes_successful_specific_follows_only(tmp_path):
    account_directory = tmp_path / "account"
    now = datetime.now(timezone.utc)
    context = RuntimeContext(
        SessionContext(
            uuid4(),
            "alice",
            "PHONE",
            "com.instagram.android",
            account_directory,
            now,
        ),
        PythonRuntimeLogger(),
    )
    with RuntimeDatabase(account_directory) as database:
        database.specific_follow.upsert_username(
            "successful", {"follow_date": now.isoformat(), "status": "SUCCESS"}
        )
        database.specific_follow.upsert_username(
            "failed", {"follow_date": now.isoformat(), "status": "FOLLOW_FAILED"}
        )

    assert successful_follows_today(context.session.account_directory) == 1
