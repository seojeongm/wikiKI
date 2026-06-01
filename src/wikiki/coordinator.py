from typing import Protocol

from .models import ArticleStats, EditEvent
from .rules import RuleEngine
from .scorer import TensionScorer
from .storage import RedisRepository, is_revert


class Dashboard(Protocol):
    def update(self, stats: ArticleStats) -> None: ...


class Coordinator:
    def __init__(
        self,
        repo: RedisRepository,
        engine: RuleEngine,
        scorer: TensionScorer,
        dashboard: Dashboard,
        window_seconds: int = 3600,
        max_size: int = 100,
    ) -> None:
        self._repo = repo
        self._engine = engine
        self._scorer = scorer
        self._dashboard = dashboard
        self._window_seconds = window_seconds
        self._max_size = max_size

    def handle(self, event: EditEvent) -> ArticleStats:
        history = self._repo.find_by_title(event.title, self._window_seconds,
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

        self._repo.save_event(event, self._max_size, self._window_seconds)

        return stats
