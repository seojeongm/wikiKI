from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .models import EditEvent


@dataclass
class Flag:
    type: str
    title: str
    weight: float
    detected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Strategy(Protocol):
    def evaluate(self, event: EditEvent, history: list[EditEvent]) -> Flag | None: ...


def _is_revert(event: EditEvent) -> bool:
    comment = event.comment.lower()
    return "revert" in comment or "undid revision" in comment


class ThreeRRStrategy:
    def __init__(self, window_seconds: int = 86400, min_reverts: int = 3) -> None:
        self.window_seconds = window_seconds
        self.min_reverts = min_reverts

    def evaluate(self, event: EditEvent, history: list[EditEvent]) -> Flag | None:
        if not _is_revert(event):
            return None

        cutoff = event.timestamp - self.window_seconds
        prior_reverts = sum(
            1 for e in history
            if e.user == event.user
            and e.title == event.title
            and e.timestamp >= cutoff
            and _is_revert(e)
        )

        if prior_reverts + 1 >= self.min_reverts:
            return Flag(type="3RR", title=event.title, weight=0.8)
        return None


class VelocitySpikeStrategy:
    def __init__(self, window_seconds: int = 3600, threshold: int = 10) -> None:
        self.window_seconds = window_seconds
        self.threshold = threshold

    def evaluate(self, event: EditEvent, history: list[EditEvent]) -> Flag | None:
        cutoff = event.timestamp - self.window_seconds
        prior = sum(
            1 for e in history
            if e.title == event.title and e.timestamp >= cutoff
        )

        if prior + 1 >= self.threshold:
            return Flag(type="VELOCITY_SPIKE", title=event.title, weight=0.6)
        return None


class EditorConflictStrategy:
    def __init__(self, window_seconds: int = 3600, min_editors: int = 3) -> None:
        self.window_seconds = window_seconds
        self.min_editors = min_editors

    def evaluate(self, event: EditEvent, history: list[EditEvent]) -> Flag | None:
        cutoff = event.timestamp - self.window_seconds
        editors = {
            e.user for e in history
            if e.title == event.title and e.timestamp >= cutoff
        }
        editors.add(event.user)

        if len(editors) >= self.min_editors:
            return Flag(type="EDITOR_CONFLICT", title=event.title, weight=0.5)
        return None


class RuleEngine:
    def __init__(self) -> None:
        self.strategies: list[Strategy] = []

    def add_strategy(self, strategy: Strategy) -> None:
        self.strategies.append(strategy)

    def evaluate(self, event: EditEvent, history: list[EditEvent]) -> list[Flag]:
        return [
            flag for strategy in self.strategies
            if (flag := strategy.evaluate(event, history)) is not None
        ]
