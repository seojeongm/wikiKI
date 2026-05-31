import json
import sqlite3
import time

import redis

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
    conn.execute("PRAGMA journal_mode=WAL")
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


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _encode_event(event: EditEvent) -> str:
    """Serialize an EditEvent to a JSON string."""
    return json.dumps({
        "title": event.title,
        "user": event.user,
        "bot": event.bot,
        "timestamp": event.timestamp,
        "comment": event.comment,
        "length_old": event.length_old,
        "length_new": event.length_new,
        "revision_old": event.revision_old,
        "revision_new": event.revision_new,
    })


def _decode_event(data: bytes | str) -> EditEvent:
    """Deserialize a JSON string/bytes to an EditEvent."""
    if isinstance(data, bytes):
        data = data.decode()
    d = json.loads(data)
    return EditEvent(
        title=d["title"],
        user=d["user"],
        bot=d["bot"],
        timestamp=d["timestamp"],
        comment=d["comment"],
        length_old=d["length_old"],
        length_new=d["length_new"],
        revision_old=d["revision_old"],
        revision_new=d["revision_new"],
    )


def is_revert(event: EditEvent) -> bool:
    """Return True if the event comment indicates a revert."""
    comment_lower = event.comment.lower()
    return "revert" in comment_lower or "undid revision" in comment_lower


def accumulate_stats_to_sqlite(
    conn: sqlite3.Connection,
    r: redis.Redis,
    evicted_event: EditEvent,
) -> None:
    """Accumulate an evicted ring-buffer event into the SQLite article_stats table."""
    row = conn.execute(
        "SELECT 1 FROM article_stats WHERE title = ?",
        (evicted_event.title,),
    ).fetchone()
    if row is None:
        return

    raw = r.hgetall(f"stats:{evicted_event.title}")
    if not raw:
        return

    is_rev = 1 if is_revert(evicted_event) else 0
    editor_count = int(raw[b"editor_count"].decode())
    tension_score = float(raw[b"tension_score"].decode())
    status = raw[b"status"].decode()
    flags = json.dumps(json.loads(raw[b"flags"].decode()))
    last_seen_at = int(raw[b"last_seen_at"].decode())

    conn.execute(
        "UPDATE article_stats SET "
        "edit_velocity = edit_velocity + 1, "
        "editor_count = ?, "
        "revert_count = revert_count + ?, "
        "tension_score = ?, "
        "status = ?, "
        "flags = ?, "
        "last_seen_at = ? "
        "WHERE title = ?",
        (editor_count, is_rev, tension_score, status, flags, last_seen_at, evicted_event.title),
    )
    conn.commit()


def redis_save_event(
    r: redis.Redis,
    conn: sqlite3.Connection,
    event: EditEvent,
    max_size: int = 100,
) -> None:
    """Add an EditEvent to the Redis ring buffer, evicting the oldest if needed."""
    key = f"edits:{event.title}"
    r.zadd(key, {_encode_event(event): event.timestamp})

    size = r.zcard(key)
    if size > max_size:
        oldest = r.zrange(key, 0, 0)
        r.zremrangebyrank(key, 0, 0)
        if oldest:
            evicted_event = _decode_event(oldest[0])
            accumulate_stats_to_sqlite(conn, r, evicted_event)


def redis_find_by_title(
    r: redis.Redis,
    title: str,
    window_seconds: int,
    now: int | None = None,
) -> list[EditEvent]:
    """Return EditEvents for *title* within the given time window from Redis."""
    cutoff = (now if now is not None else int(time.time())) - window_seconds
    members = r.zrangebyscore(f"edits:{title}", cutoff, "+inf")
    return [_decode_event(m) for m in members]


def redis_upsert_stats(
    r: redis.Redis,
    stats: ArticleStats,
    last_seen_at: int,
) -> None:
    """Write ArticleStats to the Redis hash and update the stats:index sorted set."""
    r.hset(f"stats:{stats.title}", mapping={
        "editor_count": str(stats.editor_count),
        "revert_count": str(stats.revert_count),
        "edit_velocity": str(stats.edit_velocity),
        "tension_score": str(stats.tension_score),
        "status": str(stats.status),
        "flags": json.dumps(stats.flags),
        "last_seen_at": str(last_seen_at),
    })
    r.zadd("stats:index", {stats.title: last_seen_at})


def redis_get_all_stats(r: redis.Redis) -> list[ArticleStats]:
    """Return all ArticleStats from Redis, ordered by most recently seen."""
    titles = r.zrevrangebyscore("stats:index", "+inf", "-inf")
    now = int(time.time())
    result: list[ArticleStats] = []
    for title_raw in titles:
        title = title_raw.decode() if isinstance(title_raw, bytes) else title_raw
        raw = r.hgetall(f"stats:{title}")
        if not raw:
            continue
        last_seen_at = int(raw[b"last_seen_at"].decode())
        flags_str = raw[b"flags"].decode()
        result.append(ArticleStats(
            title=title,
            editor_count=int(raw[b"editor_count"].decode()),
            revert_count=int(raw[b"revert_count"].decode()),
            edit_velocity=float(raw[b"edit_velocity"].decode()),
            tension_score=float(raw[b"tension_score"].decode()),
            status=raw[b"status"].decode(),
            flags=json.loads(flags_str),
            last_edit_min=max(0, int((now - last_seen_at) / 60)),
        ))
    return result


def flush_title_to_sqlite(
    r: redis.Redis,
    conn: sqlite3.Connection,
    title: str,
    stats: ArticleStats,
    last_seen_at: int,
) -> None:
    """Flush the Redis ring buffer for *title* and its stats into SQLite."""
    members = r.zrange(f"edits:{title}", 0, -1)
    for member in members:
        event = _decode_event(member)
        save_event(conn, event)
    upsert_stats(conn, stats, last_seen_at)
