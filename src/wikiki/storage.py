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


def _row_to_event(row: tuple) -> EditEvent:
    return EditEvent(
        title=row[0], user=row[1], bot=bool(row[2]), timestamp=row[3],
        comment=row[4], length_old=row[5], length_new=row[6],
        revision_old=row[7], revision_new=row[8],
    )


class SQLiteRepository:
    """Long-term storage of edit events and accumulated article stats.

    Acts as the cold tier behind the Redis hot buffer. Evicted ring-buffer
    events are folded into ``article_stats`` via :meth:`accumulate_stats`.

    ``accumulate_stats`` batches commits: the dominant per-evict cost is the
    fsync in ``commit()``, not the SQL itself (see meeting-notes/2026-06-21-1).
    A crash loses at most ``commit_batch`` pending evictions (or up to
    ``max_commit_delay_seconds`` worth), which the cold tier tolerates.
    Call :meth:`flush` on shutdown to persist the remainder.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        commit_batch: int = 32,
        max_commit_delay_seconds: float = 5.0,
    ) -> None:
        self._conn = conn
        self._commit_batch = commit_batch
        self._max_commit_delay_seconds = max_commit_delay_seconds
        self._pending_writes = 0
        self._first_pending_at: float | None = None

    def flush(self) -> None:
        """Commit the current transaction, including batched eviction writes."""
        self._conn.commit()
        self._pending_writes = 0
        self._first_pending_at = None

    def save_event(self, event: EditEvent) -> None:
        """Persist a single EditEvent to the database."""
        self._conn.execute(_INSERT, (
            event.title, event.user, int(event.bot), event.timestamp,
            event.comment, event.length_old, event.length_new,
            event.revision_old, event.revision_new,
        ))
        self.flush()

    def find_by_title(
        self,
        title: str,
        window_seconds: int,
        now: int | None = None,
    ) -> list[EditEvent]:
        cutoff = (now if now is not None else int(time.time())) - window_seconds
        rows = self._conn.execute(
            "SELECT title, user, bot, timestamp, comment, "
            "length_old, length_new, revision_old, revision_new "
            "FROM edit_events WHERE title = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (title, cutoff),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def find_recent(self, limit: int) -> list[EditEvent]:
        if limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit}")
        rows = self._conn.execute(
            "SELECT title, user, bot, timestamp, comment, "
            "length_old, length_new, revision_old, revision_new "
            "FROM edit_events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def upsert_stats(self, stats: ArticleStats, last_seen_at: int) -> None:
        self._conn.execute(
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
        self.flush()

    def get_all_stats(self) -> list[ArticleStats]:
        now = int(time.time())
        rows = self._conn.execute(
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

    def accumulate_stats(
        self,
        evicted_event: EditEvent,
        redis_stats: dict,
        count: int,
    ) -> None:
        """Fold an evicted ring-buffer event into ``article_stats``.

        ``redis_stats`` holds the already-decoded hash values (this class
        never touches Redis itself). Accumulates into an existing row, or
        inserts a new row only when ``count >= 3``.
        """
        is_rev = 1 if is_revert(evicted_event) else 0
        editor_count = redis_stats["editor_count"]
        tension_score = redis_stats["tension_score"]
        status = redis_stats["status"]
        flags = json.dumps(redis_stats["flags"])
        last_seen_at = redis_stats["last_seen_at"]

        row = self._conn.execute(
            "SELECT 1 FROM article_stats WHERE title = ?",
            (evicted_event.title,),
        ).fetchone()

        if row is None:
            if count < 3:
                return
            self._conn.execute(
                "INSERT INTO article_stats "
                "(title, editor_count, revert_count, edit_velocity, tension_score, status, flags, last_seen_at) "
                "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
                (evicted_event.title, editor_count, is_rev, tension_score, status, flags, last_seen_at),
            )
        else:
            self._conn.execute(
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

        self._pending_writes += 1
        now = time.monotonic()
        if self._first_pending_at is None:
            self._first_pending_at = now
        if (
            self._pending_writes >= self._commit_batch
            or now - self._first_pending_at >= self._max_commit_delay_seconds
        ):
            self.flush()


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


class RedisRepository:
    """Hot-tier ring buffer of recent edits plus live article stats.

    Recent events live in a per-title sorted set keyed by timestamp; events
    that fall outside the window or overflow ``max_size`` are evicted and
    folded into the cold tier via the injected :class:`SQLiteRepository`.

    ``sqlite_repo`` is only consulted when an event is evicted, so read-only
    consumers (e.g. the dashboard) may construct this with ``sqlite_repo=None``.
    """

    def __init__(
        self,
        r: redis.Redis,
        sqlite_repo: SQLiteRepository | None = None,
    ) -> None:
        self._redis = r
        self._sqlite_repo = sqlite_repo

    def save_event(
        self,
        event: EditEvent,
        max_size: int = 100,
        window_seconds: int = 3600,
    ) -> None:
        """Add an EditEvent to the ring buffer, evicting the oldest if needed."""
        key = f"edits:{event.title}"
        cutoff = event.timestamp - window_seconds

        expired = self._redis.zrangebyscore(key, "-inf", cutoff)
        count = self._redis.zcard(key) if expired else 0
        self._redis.zremrangebyscore(key, "-inf", cutoff)
        for member in expired:
            self._evict_to_sqlite(_decode_event(member), count=count)

        self._redis.zadd(key, {_encode_event(event): event.timestamp})

        size = self._redis.zcard(key)
        if size > max_size:
            oldest = self._redis.zrange(key, 0, 0)
            self._redis.zremrangebyrank(key, 0, 0)
            if oldest:
                self._evict_to_sqlite(_decode_event(oldest[0]), count=size)

    def find_by_title(
        self,
        title: str,
        window_seconds: int,
        now: int | None = None,
    ) -> list[EditEvent]:
        """Return EditEvents for *title* within the given time window."""
        cutoff = (now if now is not None else int(time.time())) - window_seconds
        members = self._redis.zrangebyscore(f"edits:{title}", cutoff, "+inf")
        return [_decode_event(m) for m in members]

    def upsert_stats(self, stats: ArticleStats, last_seen_at: int) -> None:
        """Write ArticleStats to the hash and update the stats:index set."""
        self._redis.hset(f"stats:{stats.title}", mapping={
            "editor_count": str(stats.editor_count),
            "revert_count": str(stats.revert_count),
            "edit_velocity": str(stats.edit_velocity),
            "tension_score": str(stats.tension_score),
            "status": str(stats.status),
            "flags": json.dumps(stats.flags),
            "last_seen_at": str(last_seen_at),
        })
        self._redis.zadd("stats:index", {stats.title: last_seen_at})

    def get_all_stats(self) -> list[ArticleStats]:
        """Return all ArticleStats, ordered by most recently seen."""
        titles = self._redis.zrevrangebyscore("stats:index", "+inf", "-inf")
        now = int(time.time())
        result: list[ArticleStats] = []
        for title_raw in titles:
            title = title_raw.decode() if isinstance(title_raw, bytes) else title_raw
            raw = self._redis.hgetall(f"stats:{title}")
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

    def _read_stats_hash(self, title: str) -> dict | None:
        """Read and decode the stats hash for *title*, or None if absent."""
        raw = self._redis.hgetall(f"stats:{title}")
        if not raw:
            return None
        return {
            "editor_count": int(raw[b"editor_count"].decode()),
            "tension_score": float(raw[b"tension_score"].decode()),
            "status": raw[b"status"].decode(),
            "flags": json.loads(raw[b"flags"].decode()),
            "last_seen_at": int(raw[b"last_seen_at"].decode()),
        }

    def _evict_to_sqlite(self, evicted_event: EditEvent, count: int) -> None:
        """Fold an evicted event's stats into the cold tier."""
        if self._sqlite_repo is None:
            raise RuntimeError(
                "RedisRepository requires a SQLiteRepository to evict events; "
                "this instance was constructed without one (read-only)."
            )
        redis_stats = self._read_stats_hash(evicted_event.title)
        if redis_stats is None:
            return
        self._sqlite_repo.accumulate_stats(evicted_event, redis_stats, count)



