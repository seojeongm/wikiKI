import sqlite3
import time

from .models import EditEvent

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS edit_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    user         TEXT    NOT NULL,
    bot          INTEGER NOT NULL,
    timestamp    INTEGER NOT NULL,
    comment      TEXT    NOT NULL DEFAULT '',
    length_old   INTEGER NOT NULL,
    length_new   INTEGER NOT NULL,
    revision_old INTEGER NOT NULL,
    revision_new INTEGER NOT NULL
)
"""

_INSERT = """
INSERT INTO edit_events
    (title, user, bot, timestamp, comment, length_old, length_new, revision_old, revision_new)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def connect(db_path: str = "wikiki.db") -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the schema exists."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def save_event(conn: sqlite3.Connection, event: EditEvent) -> None:
    """Persist a single EditEvent to the database."""
    conn.execute(_INSERT, (
        event.title, event.user, int(event.bot), event.timestamp,
        event.comment, event.length_old, event.length_new,
        event.revision_old, event.revision_new,
    ))
    conn.commit()


def _row_to_event(row: tuple) -> EditEvent:
    return EditEvent(
        title=row[0], user=row[1], bot=bool(row[2]), timestamp=row[3],
        comment=row[4], length_old=row[5], length_new=row[6],
        revision_old=row[7], revision_new=row[8],
    )


def find_by_title(
    conn: sqlite3.Connection,
    title: str,
    window_seconds: int,
    now: int | None = None,
) -> list[EditEvent]:
    cutoff = (now if now is not None else int(time.time())) - window_seconds
    rows = conn.execute(
        "SELECT title, user, bot, timestamp, comment, "
        "length_old, length_new, revision_old, revision_new "
        "FROM edit_events WHERE title = ? AND timestamp >= ? "
        "ORDER BY timestamp ASC",
        (title, cutoff),
    ).fetchall()
    return [_row_to_event(r) for r in rows]


def find_recent(conn: sqlite3.Connection, limit: int) -> list[EditEvent]:
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit}")
    rows = conn.execute(
        "SELECT title, user, bot, timestamp, comment, "
        "length_old, length_new, revision_old, revision_new "
        "FROM edit_events ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_event(r) for r in rows]
