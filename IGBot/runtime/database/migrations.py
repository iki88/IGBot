"""Transactional evolution of the six per-account SQLite tables."""

from __future__ import annotations

import sqlite3

from IGBot.runtime.database.timestamps import optional_utc_timestamp

TABLES = ("users", "follow", "like", "comment", "story", "dm")
TIMESTAMPS = {
    "first_seen",
    "follow_date",
    "follow_back_date",
    "unfollow_date",
    "last_like_date",
    "last_comment_date",
    "last_story_date",
    "last_dm_date",
}


def migrate_runtime_schema(connection: sqlite3.Connection, repositories: tuple) -> None:
    """Rebuild legacy UTC-ISO tables while preserving keys and module state."""

    existing = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
        )
    }
    follow_columns = (
        {row[1] for row in connection.execute('PRAGMA table_info("follow")')}
        if "follow" in existing
        else set()
    )
    if "username" in follow_columns and not any(
        "GLOB '*Z'" in existing.get(name, "") for name in TABLES
    ):
        return
    if not any(name in existing for name in TABLES):
        return

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        with connection:
            connection.execute("DROP TRIGGER IF EXISTS follow_username_sync")
            for name in TABLES:
                if name in existing:
                    connection.execute(
                        f'ALTER TABLE "{name}" RENAME TO "_legacy_{name}"'
                    )
            for repository in repositories:
                repository.initialize_schema()

            old_users = {}
            if "users" in existing:
                for row in connection.execute('SELECT * FROM "_legacy_users"'):
                    old_users[row["id"]] = row["username"]
            for name in TABLES:
                if name not in existing:
                    continue
                for row in connection.execute(f'SELECT * FROM "_legacy_{name}"'):
                    values = dict(row)
                    if name == "follow":
                        values["username"] = old_users[values["user_id"]]
                        values.setdefault("muted", 0)
                    for column in TIMESTAMPS.intersection(values):
                        values[column] = optional_utc_timestamp(values[column])
                    columns = tuple(values)
                    names = ", ".join(f'"{column}"' for column in columns)
                    placeholders = ", ".join("?" for _ in columns)
                    connection.execute(
                        f'INSERT INTO "{name}" ({names}) VALUES ({placeholders})',
                        tuple(values.values()),
                    )
            for name in reversed(TABLES):
                if name in existing:
                    connection.execute(f'DROP TABLE "_legacy_{name}"')
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.IntegrityError(
                    "Runtime schema migration broke a foreign key"
                )
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
