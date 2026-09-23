import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from IGBot.runtime import RuntimeContext, SessionContext
from IGBot.runtime.database import RuntimeDatabase
from IGBot.runtime.scheduler import ModuleExecutionOutcome
from IGBot.runtime.unfollow import (
    AndroidUnfollowResult,
    AndroidUnfollowStatus,
    SpecificUnfollowModule,
    SpecificUnfollowSynchronizer,
    UnfollowSettings,
)


class Logger:
    def __init__(self):
        self.messages = []

    def info(self, message, **fields):
        self.messages.append((message, fields))


def context(tmp_path):
    return RuntimeContext(
        SessionContext(
            uuid4(),
            "account",
            "phone",
            "com.instagram.clone",
            tmp_path,
            datetime.now(timezone.utc),
        ),
        Logger(),
    )


class StubAndroid:
    def __init__(self, results):
        self.results = list(results)
        self.usernames = []

    def execute(self, _context, username):
        self.usernames.append(username)
        return self.results.pop(0)


def write_list(tmp_path, *usernames):
    directory = tmp_path / "Lists"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "unfollowspecific.txt").write_text(
        "".join(f"{username}\n" for username in usernames), encoding="utf-8"
    )


def test_txt_synchronization_adds_removes_and_preserves_execution_state(tmp_path):
    write_list(tmp_path, "first_user", "second_user")
    synchronizer = SpecificUnfollowSynchronizer()
    synchronizer.synchronize(tmp_path)
    with RuntimeDatabase(tmp_path) as database:
        database.specific_unfollow.mark_specific_unfollowed(
            "first_user", "2026-09-23 01:00:00", "session-one"
        )

    write_list(tmp_path, "first_user", "new_user")
    synchronizer.synchronize(tmp_path)

    with sqlite3.connect(tmp_path / "runtime.db") as connection:
        rows = connection.execute(
            "SELECT username, unfollowed, last_session_id FROM specific_unfollow "
            "ORDER BY user_id"
        ).fetchall()
    assert rows == [
        ("first_user", 1, "session-one"),
        ("new_user", 0, None),
    ]


def test_specific_unfollow_persists_only_verified_success(tmp_path):
    write_list(tmp_path, "target_user")
    SpecificUnfollowSynchronizer().synchronize(tmp_path)
    ctx = context(tmp_path)
    android = StubAndroid(
        [AndroidUnfollowResult(AndroidUnfollowStatus.SUCCESS, username="target_user")]
    )
    module = SpecificUnfollowModule(
        ctx, UnfollowSettings(True, True, 1, 5, 5, 0), android
    )
    module.start()

    result = module.execute(ctx, None)

    assert result.outcome is ModuleExecutionOutcome.SUCCESS
    with sqlite3.connect(tmp_path / "runtime.db") as connection:
        saved = connection.execute(
            "SELECT unfollowed, unfollow_date, last_session_id, status "
            "FROM specific_unfollow WHERE username = 'target_user'"
        ).fetchone()
    assert saved[0] == 1
    assert saved[1]
    assert saved[2] == str(ctx.session.session_id)
    assert saved[3] == "SUCCESS"


def test_failed_specific_unfollow_remains_pending(tmp_path):
    write_list(tmp_path, "target_user")
    SpecificUnfollowSynchronizer().synchronize(tmp_path)
    ctx = context(tmp_path)
    module = SpecificUnfollowModule(
        ctx,
        UnfollowSettings(True, True, 1, 5, 5, 0),
        StubAndroid(
            [
                AndroidUnfollowResult(
                    AndroidUnfollowStatus.VERIFICATION_FAILED,
                    username="target_user",
                )
            ]
        ),
    )
    module.start()

    module.execute(ctx, None)

    with RuntimeDatabase(tmp_path) as database:
        assert database.specific_unfollow.pending_unfollow_usernames() == (
            "target_user",
        )


def test_restart_resumes_with_first_unprocessed_username(tmp_path):
    write_list(tmp_path, "done_user", "remaining_user")
    synchronizer = SpecificUnfollowSynchronizer()
    synchronizer.synchronize(tmp_path)
    with RuntimeDatabase(tmp_path) as database:
        database.specific_unfollow.mark_specific_unfollowed(
            "done_user", "2026-09-23 01:00:00", "previous-session"
        )
    synchronizer.synchronize(tmp_path)
    ctx = context(tmp_path)
    android = StubAndroid(
        [
            AndroidUnfollowResult(
                AndroidUnfollowStatus.SUCCESS, username="remaining_user"
            )
        ]
    )
    module = SpecificUnfollowModule(
        ctx, UnfollowSettings(True, True, 1, 5, 5, 0), android
    )
    module.start()

    module.execute(ctx, None)

    assert android.usernames == ["remaining_user"]


def test_existing_specific_unfollow_table_is_migrated_additively(tmp_path):
    path = tmp_path / "runtime.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE specific_unfollow ("
            "user_id INTEGER PRIMARY KEY, username TEXT NOT NULL, "
            "unfollow_date TEXT, status TEXT)"
        )
        connection.execute(
            "INSERT INTO specific_unfollow VALUES (1, 'existing_user', NULL, NULL)"
        )

    with RuntimeDatabase(tmp_path):
        pass

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT username, unfollowed, last_session_id FROM specific_unfollow"
        ).fetchone()
    assert row == ("existing_user", 0, None)
