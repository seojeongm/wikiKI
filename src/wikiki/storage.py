import json
import sqlite3
import time

from .models import ArticleStats, EditEvent

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

_CREATE_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS article_stats (
    title         TEXT    PRIMARY KEY,
    editor_count  INTEGER NOT NULL,
    revert_count  INTEGER NOT NULL,
    edit_velocity REAL    NOT NULL,
    tension_score REAL    NOT NULL,
    status        TEXT    NOT NULL,
    flags         TEXT    NOT NULL DEFAULT '[]',
    last_seen_at  INTEGER NOT NULL DEFAULT 0
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
    conn.execute(_CREATE_STATS_TABLE)
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


def upsert_stats(conn: sqlite3.Connection, stats: ArticleStats, last_seen_at: int) -> None:
    conn.execute(
        "INSERT INTO article_stats "
        "(title, editor_count, revert_count, edit_velocity, tension_score, status, flags, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(title) DO UPDATE SET "
        "editor_count=excluded.editor_count, revert_count=excluded.revert_count, "
        "edit_velocity=excluded.edit_velocity, tension_score=excluded.tension_score, "
        "status=excluded.status, flags=excluded.flags, last_seen_at=excluded.last_seen_at",
        (stats.title, stats.editor_count, stats.revert_count, stats.edit_velocity,
         stats.tension_score, stats.status, json.dumps(stats.flags), last_seen_at),
    )
    conn.commit()


def get_all_stats(conn: sqlite3.Connection) -> list[ArticleStats]:
    now = int(time.time())
    rows = conn.execute(
        "SELECT title, editor_count, revert_count, edit_velocity, "
        "tension_score, status, flags, last_seen_at "
        "FROM article_stats ORDER BY last_seen_at DESC"
    ).fetchall()
    return [
        ArticleStats(
            title=row[0], editor_count=row[1], revert_count=row[2],
            edit_velocity=row[3], tension_score=row[4], status=row[5],
            flags=json.loads(row[6]),
            last_edit_min=max(0, int((now - row[7]) / 60)),
        )
        for row in rows
    ]


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
