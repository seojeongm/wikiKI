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
