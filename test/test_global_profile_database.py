import sqlite3

from IGBot.runtime.profile_database import GlobalDatabaseWriter, ProfileUpdate


def test_global_profile_writer_persists_complete_shared_profile(tmp_path):
    writer = GlobalDatabaseWriter(tmp_path)
    writer.submit(
        ProfileUpdate(
            username="candidate",
            full_name="Candidate Name",
            biography="Biography",
            category="Carpenter",
            website="example.com",
            phone="+43 699",
            email="candidate@example.com",
            address="Main Street",
            followers=432,
            following=199,
            posts=104,
            is_private=False,
            is_business=True,
            is_verified=True,
            follow_status="follow",
            source_account="source_account",
            discovered_at="2026-09-11T14:00:00+00:00",
        )
    )
    writer.close()

    with sqlite3.connect(tmp_path / "global_profiles.db") as connection:
        row = connection.execute("SELECT * FROM profiles").fetchone()
        columns = {
            item[1] for item in connection.execute("PRAGMA table_info(profiles)")
        }

    assert row == (
        "candidate",
        "Candidate Name",
        "Biography",
        "Carpenter",
        "example.com",
        "+43 699",
        "candidate@example.com",
        "Main Street",
        432,
        199,
        104,
        0,
        1,
        1,
        "follow",
        "source_account",
        "2026-09-11 14:00:00",
        "2026-09-11 14:00:00",
    )
    assert "business_category" in columns
    assert "category" not in columns


def test_later_partial_observation_does_not_erase_contact_details(tmp_path):
    writer = GlobalDatabaseWriter(tmp_path)
    writer.submit(
        ProfileUpdate(
            username="candidate",
            email="candidate@example.com",
            discovered_at="2026-09-11T14:00:00+00:00",
        )
    )
    writer.submit(
        ProfileUpdate(
            username="candidate",
            followers=500,
            discovered_at="2026-09-11T15:00:00+00:00",
        )
    )
    writer.close()

    with sqlite3.connect(tmp_path / "global_profiles.db") as connection:
        row = connection.execute(
            "SELECT email, followers, discovered_at, updated_at FROM profiles"
        ).fetchone()

    assert row == (
        "candidate@example.com",
        500,
        "2026-09-11 14:00:00",
        "2026-09-11 15:00:00",
    )


def test_existing_category_column_is_migrated_to_business_category(tmp_path):
    path = tmp_path / "global_profiles.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE profiles (username TEXT PRIMARY KEY, category TEXT)"
        )
        connection.execute(
            "INSERT INTO profiles (username, category) VALUES (?, ?)",
            ("candidate", "Financial service"),
        )

    writer = GlobalDatabaseWriter(tmp_path)
    writer.close()

    with sqlite3.connect(path) as connection:
        columns = {
            item[1] for item in connection.execute("PRAGMA table_info(profiles)")
        }
        category = connection.execute(
            "SELECT business_category FROM profiles WHERE username = ?",
            ("candidate",),
        ).fetchone()[0]

    assert "business_category" in columns
    assert "category" not in columns
    assert category == "Financial service"


def test_existing_global_profile_timestamps_are_reformatted_without_schema_change(
    tmp_path,
):
    writer = GlobalDatabaseWriter(tmp_path)
    writer.submit(
        ProfileUpdate(
            username="existing",
            discovered_at="2026-09-13T15:12:34.175068+00:00",
        )
    )
    writer.close()
    path = tmp_path / "global_profiles.db"
    with sqlite3.connect(path) as connection:
        columns_before = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(profiles)")
        )
        connection.execute(
            "UPDATE profiles SET discovered_at = ?, updated_at = ? WHERE username = ?",
            (
                "2026-09-13T15:12:34.175068+00:00",
                "2026-09-13T16:00:00+00:00",
                "existing",
            ),
        )

    writer = GlobalDatabaseWriter(tmp_path)
    writer.close()

    with sqlite3.connect(path) as connection:
        columns_after = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(profiles)")
        )
        timestamps = connection.execute(
            "SELECT discovered_at, updated_at FROM profiles WHERE username = ?",
            ("existing",),
        ).fetchone()
    assert columns_after == columns_before
    assert timestamps == ("2026-09-13 15:12:34", "2026-09-13 16:00:00")
