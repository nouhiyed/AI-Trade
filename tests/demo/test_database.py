import sqlite3
import pytest

from core.demo.database import DemoDatabase


def test_outer_transaction_commits_nested_transaction(tmp_path):
    db = DemoDatabase(tmp_path / "demo.db")
    db.connection.execute(
        "CREATE TABLE entries (value TEXT)"
    )

    with db.transaction():
        db.connection.execute(
            "INSERT INTO entries VALUES ('outer')"
        )
        with db.transaction():
            db.connection.execute(
                "INSERT INTO entries VALUES ('inner')"
            )

    rows = db.connection.execute(
        "SELECT value FROM entries ORDER BY rowid"
    ).fetchall()

    assert [row["value"] for row in rows] == ["outer", "inner"]
    db.close()


def test_outer_rollback_reverts_all_nested_changes(tmp_path):
    db = DemoDatabase(tmp_path / "demo.db")
    db.connection.execute(
        "CREATE TABLE entries (value TEXT)"
    )

    with pytest.raises(RuntimeError):
        with db.transaction():
            db.connection.execute(
                "INSERT INTO entries VALUES ('outer')"
            )
            with db.transaction():
                db.connection.execute(
                    "INSERT INTO entries VALUES ('inner')"
                )
            raise RuntimeError("force rollback")

    count = db.connection.execute(
        "SELECT COUNT(*) FROM entries"
    ).fetchone()[0]

    assert count == 0
    db.close()


def test_nested_rollback_does_not_abort_outer_transaction(tmp_path):
    db = DemoDatabase(tmp_path / "demo.db")
    db.connection.execute(
        "CREATE TABLE entries (value TEXT)"
    )

    with db.transaction():
        db.connection.execute(
            "INSERT INTO entries VALUES ('before')"
        )

        with pytest.raises(ValueError):
            with db.transaction():
                db.connection.execute(
                    "INSERT INTO entries VALUES ('inner')"
                )
                raise ValueError("rollback inner only")

        db.connection.execute(
            "INSERT INTO entries VALUES ('after')"
        )

    rows = db.connection.execute(
        "SELECT value FROM entries ORDER BY rowid"
    ).fetchall()

    assert [row["value"] for row in rows] == ["before", "after"]
    db.close()


def test_database_cannot_close_during_transaction(tmp_path):
    db = DemoDatabase(tmp_path / "demo.db")

    with db.transaction():
        with pytest.raises(RuntimeError):
            db.close()

    db.close()

    with pytest.raises(RuntimeError):
        with db.transaction():
            pass



def test_shared_connection_serializes_concurrent_reads_and_writes(tmp_path):
    import threading

    db = DemoDatabase(tmp_path / "concurrent.db")
    db.connection.execute("CREATE TABLE events (value INTEGER NOT NULL)")
    failures = []

    def writer():
        try:
            for value in range(100):
                with db.transaction():
                    db.connection.execute(
                        "INSERT INTO events(value) VALUES (?)", (value,)
                    )
        except Exception as error:
            failures.append(error)

    def reader():
        try:
            for _ in range(150):
                row = db.connection.execute(
                    "SELECT COUNT(*) AS total FROM events"
                ).fetchone()
                assert row["total"] >= 0
        except Exception as error:
            failures.append(error)

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert failures == []
    assert db.connection.execute(
        "SELECT COUNT(*) FROM events"
    ).fetchone()[0] == 100
    db.close()
