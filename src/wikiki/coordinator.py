import sqlite3
import redis as redis_module
from typing import Protocol

from .models import ArticleStats, EditEvent
from .rules import RuleEngine
from .scorer import TensionScorer
from .storage import (
    find_by_title, is_revert, save_event, upsert_stats,
    redis_find_by_title, redis_save_event,
    flush_title_to_sqlite,
)


class Dashboard(Protocol):
    def update(self, stats: ArticleStats) -> None: ...


class Coordinator:
    def __init__(
        self,
        conn: sqlite3.Connection,
        redis_client: redis_module.Redis,
        engine: RuleEngine,
        scorer: TensionScorer,
        dashboard: Dashboard,
        window_seconds: int = 3600,
        max_size: int = 100,
    ) -> None:
        self._conn = conn
        self._redis = redis_client
        self._engine = engine
        self._scorer = scorer
        self._dashboard = dashboard
        self._window_seconds = window_seconds
        self._max_size = max_size

    def handle(self, event: EditEvent) -> ArticleStats:
        history = redis_find_by_title(self._redis, event.title, self._window_seconds,
                                      now=event.timestamp)

        flags = self._engine.evaluate(event, history)
        score = self._scorer.calculate(flags)

        all_events = history + [event]
        stats = ArticleStats(
            title=event.title,
            editor_count=len({e.user for e in all_events}),
            revert_count=sum(1 for e in all_events if is_revert(e)),
            edit_velocity=float(len(all_events)),
            tension_score=score,
            status=self._scorer.to_status(score),
            flags=[f.type for f in flags],
        )

        self._dashboard.update(stats)

        redis_save_event(self._redis, self._conn, event, self._max_size)

        count = len(all_events)
        already_in_sqlite = self._conn.execute(
            "SELECT 1 FROM article_stats WHERE title = ?", (event.title,)
        ).fetchone() is not None

        if not already_in_sqlite and count >= 3:
            flush_title_to_sqlite(self._redis, self._conn, event.title, stats, event.timestamp)
        elif already_in_sqlite:
            save_event(self._conn, event)
            upsert_stats(self._conn, stats, last_seen_at=event.timestamp)

        return stats
