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
    StoryRecord,
    StoryRepository,
    UsersRepository,
)


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


def test_runtime_database_creates_only_the_six_runtime_tables(tmp_path):
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
    }


def test_runtime_database_constructs_named_repositories(tmp_path):
    with RuntimeDatabase(tmp_path) as database:
        assert isinstance(database.users, UsersRepository)
        assert isinstance(database.follow, FollowRepository)
        assert isinstance(database.like, LikeRepository)
        assert isinstance(database.comment, CommentRepository)
        assert isinstance(database.story, StoryRepository)
        assert isinstance(database.dm, DMRepository)


def test_runtime_database_schema_matches_the_frozen_contract(tmp_path):
    with RuntimeDatabase(tmp_path):
        pass

    database_path = tmp_path / "runtime.db"
    expected_columns = {
        "users": ("id", "username", "first_seen", "first_discovered_by"),
        "follow": (
            "user_id",
            "source",
            "follow_date",
            "follow_back",
            "follow_back_date",
            "unfollowed",
            "unfollow_date",
            "last_session_id",
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
                source="source_account",
                follow_date="2026-09-04T12:01:00+00:00",
                follow_back=True,
                last_session_id="session-1",
            )
        )
        database.like.save(LikeRecord(user.id, source="source_account", likes_count=3))
        database.comment.save(
            CommentRecord(user.id, source="source_account", comments_count=2)
        )
        database.story.save(
            StoryRecord(user.id, source="source_account", story_views_count=4)
        )
        database.dm.save(
            DMRecord(
                user.id,
                source="new_followers",
                dm_count=1,
                last_message="Hello",
                last_reply="Hi",
            )
        )

        assert database.users.get_by_username("target.user") == user
        assert database.follow.get(user.id).follow_back is True
        assert database.like.get(user.id).likes_count == 3
        assert database.comment.get(user.id).comments_count == 2
        assert database.story.get(user.id).story_views_count == 4
        assert database.dm.get(user.id).last_reply == "Hi"


def test_runtime_database_rolls_back_context_on_error(tmp_path):
    with (
        pytest.raises(RuntimeError, match="stop unit of work"),
        RuntimeDatabase(tmp_path) as database,
    ):
        database.users.create("rolled_back", "2026-09-04T12:00:00+00:00")
        raise RuntimeError("stop unit of work")

    with RuntimeDatabase(tmp_path) as database:
        assert database.users.get_by_username("rolled_back") is None


def test_runtime_database_rejects_non_utc_timestamps(tmp_path):
    with (
        RuntimeDatabase(tmp_path) as database,
        pytest.raises(sqlite3.IntegrityError),
    ):
        database.users.create("local_time", "2026-09-04T12:00:00")
