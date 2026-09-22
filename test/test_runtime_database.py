import sqlite3

import pytest

from IGBot.runtime.database import (
    CommentRecord,
    CommentRepository,
    DMRecord,
    DMRepository,
    FollowRecord,
    FollowRepository,
    LikeRecord,
    LikeRepository,
    RuntimeDatabase,
    SpecificInteractionRepository,
    SpecificProgress,
    SpecificProgressRepository,
    StoryRecord,
    StoryRepository,
    UsersRepository,
)
from IGBot.services.account_assignment_service import AccountAssignmentService


def table_names(database_path):
    with sqlite3.connect(database_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def table_columns(database_path, table_name):
    with sqlite3.connect(database_path) as connection:
        return tuple(
            row[1] for row in connection.execute(f'PRAGMA table_info("{table_name}")')
        )


def test_runtime_database_creates_discovery_and_specific_users_tables(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        assert database.path == tmp_path / "runtime.db"
        assert database.path.is_file()

    assert table_names(tmp_path / "runtime.db") == {
        "users",
        "follow",
        "like",
        "comment",
        "story",
        "dm",
        "specific_follow",
        "specific_unfollow",
        "specific_like",
        "specific_dm",
        "specific_comment",
        "specific_progress",
    }


def test_runtime_database_constructs_named_repositories(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        assert isinstance(database.users, UsersRepository)
        assert isinstance(database.follow, FollowRepository)
        assert isinstance(database.like, LikeRepository)
        assert isinstance(database.comment, CommentRepository)
        assert isinstance(database.story, StoryRepository)
        assert isinstance(database.dm, DMRepository)
        assert isinstance(database.specific_follow, SpecificInteractionRepository)
        assert isinstance(database.specific_unfollow, SpecificInteractionRepository)
        assert isinstance(database.specific_like, SpecificInteractionRepository)
        assert isinstance(database.specific_dm, SpecificInteractionRepository)
        assert isinstance(database.specific_comment, SpecificInteractionRepository)
        assert isinstance(database.specific_progress, SpecificProgressRepository)


def test_account_discovery_eagerly_initializes_existing_runtime_database(tmp_path):
    accounts_directory = tmp_path / "accounts"
    account_directory = accounts_directory / "existing_account"
    account_directory.mkdir(parents=True)
    (account_directory / "config.yml").write_text(
        "username: existing_account\ndevice: phone-a\n", encoding="utf-8"
    )
    with RuntimeDatabase(account_directory) as database:
        database.users.create("preserved_user", "2026-09-20T10:00:00+00:00", "FOLLOW")
    database_path = account_directory / "runtime.db"
    with sqlite3.connect(database_path) as connection:
        for table in (
            "specific_follow",
            "specific_unfollow",
            "specific_like",
            "specific_dm",
            "specific_comment",
            "specific_progress",
        ):
            connection.execute(f'DROP TABLE "{table}"')

    AccountAssignmentService(accounts_directory).load_by_device()

    assert {
        "specific_follow",
        "specific_unfollow",
        "specific_like",
        "specific_dm",
        "specific_comment",
        "specific_progress",
    }.issubset(table_names(database_path))
    with RuntimeDatabase(account_directory) as database:
        assert database.users.get_by_username("preserved_user") is not None


def test_account_discovery_does_not_create_unused_runtime_database(tmp_path):
    accounts_directory = tmp_path / "accounts"
    account_directory = accounts_directory / "unused_account"
    account_directory.mkdir(parents=True)
    (account_directory / "config.yml").write_text(
        "username: unused_account\ndevice: phone-a\n", encoding="utf-8"
    )

    AccountAssignmentService(accounts_directory).load_by_device()

    assert not (account_directory / "runtime.db").exists()


def test_runtime_database_schema_matches_the_frozen_contract(tmp_path):
    with RuntimeDatabase(tmp_path):
        pass

    database_path = tmp_path / "runtime.db"
    expected_columns = {
        "users": ("id", "username", "first_seen", "first_discovered_by"),
        "follow": (
            "user_id",
            "username",
            "source",
            "follow_date",
            "follow_back",
            "follow_back_date",
            "unfollowed",
            "unfollow_date",
            "last_session_id",
            "muted",
        ),
        "like": (
            "user_id",
            "source",
            "likes_count",
            "last_like_date",
            "follow_back",
            "follow_back_date",
        ),
        "comment": (
            "user_id",
            "source",
            "comments_count",
            "last_comment_date",
            "follow_back",
            "follow_back_date",
        ),
        "story": (
            "user_id",
            "source",
            "story_views_count",
            "last_story_date",
            "follow_back",
            "follow_back_date",
        ),
        "dm": (
            "user_id",
            "source",
            "dm_count",
            "last_dm_date",
            "last_message",
            "last_reply",
        ),
        "specific_follow": (
            "user_id",
            "username",
            "follow_date",
            "unfollow_date",
            "contact",
            "contact_scraped",
            "muted",
            "status",
        ),
        "specific_unfollow": ("user_id", "username", "unfollow_date", "status"),
        "specific_like": (
            "user_id",
            "username",
            "likes_count",
            "last_like_date",
            "status",
        ),
        "specific_dm": (
            "user_id",
            "username",
            "dm_count",
            "last_dm_date",
            "status",
        ),
        "specific_comment": (
            "user_id",
            "username",
            "comments_count",
            "last_comment_date",
            "status",
        ),
        "specific_progress": (
            "module",
            "current_position",
            "completed",
            "repeat",
        ),
    }
    for table_name, columns in expected_columns.items():
        assert table_columns(database_path, table_name) == columns


def test_repositories_persist_only_their_owned_state(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        user = database.users.create(
            "Target.User",
            "2026-09-04T12:00:00+00:00",
            first_discovered_by="FOLLOW",
        )
        database.follow.save(
            FollowRecord(
                user.id,
                username=user.username,
                source="source_account",
                follow_date="2026-09-04T12:01:00+00:00",
                follow_back=True,
                last_session_id="session-1",
            )
        )
        database.like.save(
            LikeRecord(
                user.id,
                source="source_account",
                likes_count=3,
                last_like_date="2026-09-04T12:02:00+00:00",
            )
        )
        database.comment.save(
            CommentRecord(
                user.id,
                source="source_account",
                comments_count=2,
                last_comment_date="2026-09-04T12:03:00+00:00",
            )
        )
        database.story.save(
            StoryRecord(
                user.id,
                source="source_account",
                story_views_count=4,
                last_story_date="2026-09-04T12:04:00+00:00",
            )
        )
        database.dm.save(
            DMRecord(
                user.id,
                source="new_followers",
                dm_count=1,
                last_dm_date="2026-09-04T12:05:00+00:00",
                last_message="Hello",
                last_reply="Hi",
            )
        )

        assert database.users.get_by_username("target.user") == user
        assert user.first_seen == "2026-09-04 12:00:00"
        assert database.follow.get(user.id).follow_back is True
        assert database.follow.get(user.id).follow_date == "2026-09-04 12:01:00"
        assert database.like.get(user.id).likes_count == 3
        assert database.like.get(user.id).last_like_date == "2026-09-04 12:02:00"
        assert database.comment.get(user.id).comments_count == 2
        assert database.comment.get(user.id).last_comment_date == "2026-09-04 12:03:00"
        assert database.story.get(user.id).story_views_count == 4
        assert database.story.get(user.id).last_story_date == "2026-09-04 12:04:00"
        assert database.dm.get(user.id).last_reply == "Hi"
        assert database.dm.get(user.id).last_dm_date == "2026-09-04 12:05:00"


def test_runtime_database_rolls_back_context_on_error(tmp_path):
    with (
        pytest.raises(RuntimeError, match="stop unit of work"),
        RuntimeDatabase(tmp_path) as database,
    ):
        database.users.create("rolled_back", "2026-09-04T12:00:00+00:00")
        raise RuntimeError("stop unit of work")

    with RuntimeDatabase(tmp_path) as database:
        assert database.users.get_by_username("rolled_back") is None


def test_specific_progress_persists_independent_module_cursors(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        database.specific_progress.save(
            SpecificProgress("follow", current_position=347)
        )
        database.specific_progress.save(
            SpecificProgress("like", current_position=61, repeat=True)
        )

    with RuntimeDatabase(tmp_path) as database:
        assert database.specific_progress.get("follow") == SpecificProgress(
            "follow", current_position=347
        )
        assert database.specific_progress.get("like") == SpecificProgress(
            "like", current_position=61, repeat=True
        )


def test_runtime_database_rejects_non_utc_timestamps(tmp_path):
    with (
        RuntimeDatabase(tmp_path) as database,
        pytest.raises(ValueError, match="UTC-aware"),
    ):
        database.users.create("local_time", "2026-09-04T12:00:00")


def test_legacy_runtime_database_migrates_follow_without_losing_state(tmp_path):
    path = tmp_path / "runtime.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                first_seen TEXT NOT NULL CHECK (first_seen GLOB '*+00:00'),
                first_discovered_by TEXT
            )
            """)
        connection.execute("""
            CREATE TABLE follow (
                user_id INTEGER PRIMARY KEY, source TEXT,
                follow_date TEXT CHECK (follow_date GLOB '*+00:00'),
                follow_back INTEGER NOT NULL DEFAULT 0, follow_back_date TEXT,
                unfollowed INTEGER NOT NULL DEFAULT 0, unfollow_date TEXT,
                last_session_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (7, "legacy_user", "2026-09-13T15:12:34.175068+00:00", "FOLLOW"),
        )
        connection.execute(
            "INSERT INTO follow VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                7,
                "source_account",
                "2026-09-13T15:12:35+00:00",
                1,
                "2026-09-13T16:00:00+00:00",
                1,
                "2026-09-13T17:00:00+00:00",
                "session-1",
            ),
        )

    with RuntimeDatabase(tmp_path) as database:
        user = database.users.get_by_username("legacy_user")
        record = database.follow.get(user.id)
        assert user.id == 7
        assert user.first_seen == "2026-09-13 15:12:34"
        assert record == FollowRecord(
            user_id=7,
            username="legacy_user",
            source="source_account",
            follow_date="2026-09-13 15:12:35",
            follow_back=True,
            follow_back_date="2026-09-13 16:00:00",
            unfollowed=True,
            unfollow_date="2026-09-13 17:00:00",
            last_session_id="session-1",
            muted=False,
        )

    with RuntimeDatabase(tmp_path) as database:
        database.users.update_username(7, "renamed_user")
        assert database.follow.get(7).username == "renamed_user"
    assert table_names(path) == {
        "users",
        "follow",
        "like",
        "comment",
        "story",
        "dm",
        "specific_follow",
        "specific_unfollow",
        "specific_like",
        "specific_dm",
        "specific_comment",
        "specific_progress",
    }
