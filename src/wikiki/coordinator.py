import sqlite3
from dataclasses import dataclass
from typing import Protocol

from .models import EditEvent
from .rules import RuleEngine
from .scorer import TensionScorer
from .storage import find_by_title, save_event


@dataclass
class ArticleStats:
    title: str
    editor_count: int
    revert_count: int
    edit_velocity: int
    tension_score: float
    status: str


class Dashboard(Protocol):
    def update(self, stats: ArticleStats) -> None: ...


def _is_revert(event: EditEvent) -> bool:
    c = event.comment.lower()
    return "revert" in c or "undid revision" in c


class Coordinator:
    def __init__(
        self,
        conn: sqlite3.Connection,
        engine: RuleEngine,
        scorer: TensionScorer,
        dashboard: Dashboard,
        window_seconds: int = 3600,
    ) -> None:
        self._conn = conn
        self._engine = engine
        self._scorer = scorer
        self._dashboard = dashboard
        self._window_seconds = window_seconds

    def handle(self, event: EditEvent) -> ArticleStats:
        history = find_by_title(self._conn, event.title, self._window_seconds,
                                now=event.timestamp)
        save_event(self._conn, event)
        flags = self._engine.evaluate(event, history)
        score = self._scorer.calculate(flags)

        all_events = history + [event]
        stats = ArticleStats(
            title=event.title,
            editor_count=len({e.user for e in all_events}),
            revert_count=sum(1 for e in all_events if _is_revert(e)),
            edit_velocity=len(all_events),
            tension_score=score,
            status=self._scorer.to_status(score),
        )
        self._dashboard.update(stats)
        return stats
