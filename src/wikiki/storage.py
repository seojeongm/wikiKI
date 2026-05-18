import sqlite3

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
