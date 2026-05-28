import asyncio
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from wikiki.coordinator import Coordinator
from wikiki.models import ArticleStats
from wikiki.parser import is_enwiki_edit, parse_edit_event
from wikiki.processor import async_stream_processor
from wikiki.rules import EditorConflictStrategy, RuleEngine, ThreeRRStrategy, VelocitySpikeStrategy
from wikiki.scorer import TensionScorer
from wikiki.storage import connect, upsert_stats
from wikiki.stream import SSEStreamClient, stream_with_reconnect


class DBDashboard:
    def __init__(self, conn) -> None:
        self._conn = conn

    def update(self, stats: ArticleStats) -> None:
        upsert_stats(self._conn, stats, last_seen_at=int(time.time()))


async def main() -> None:
    max_events_env = os.getenv("MAX_EVENTS")
    if max_events_env is not None:
        try:
            max_events = int(max_events_env)
        except ValueError:
            raise SystemExit(f"Invalid MAX_EVENTS={max_events_env!r}: must be a positive integer")
        if max_events <= 0:
            raise SystemExit(f"Invalid MAX_EVENTS={max_events_env!r}: must be a positive integer, got {max_events}")
    else:
        max_events = None

    db = connect(os.getenv("DB_PATH", "wikiki.db"))

    engine = RuleEngine()
    engine.add_strategy(ThreeRRStrategy())
    engine.add_strategy(VelocitySpikeStrategy())
    engine.add_strategy(EditorConflictStrategy())

    coordinator = Coordinator(
        conn=db,
        engine=engine,
        scorer=TensionScorer(),
        dashboard=DBDashboard(db),
    )

    client = SSEStreamClient()
    print("Connecting to Wikimedia SSE stream...", file=sys.stderr, flush=True)

    enwiki_stream = (e for e in stream_with_reconnect(client) if is_enwiki_edit(e))

    async def handle(event: dict) -> None:
        try:
            edit = parse_edit_event(event)
        except Exception as e:
            print(f"Failed to parse event: {e} | {event}", file=sys.stderr, flush=True)
            return
        stats = await asyncio.to_thread(coordinator.handle, edit)
        print(f"{stats.title} | score={stats.tension_score:.0f} | {stats.status}", flush=True)

    await async_stream_processor(
        enwiki_stream,
        handle,
        max_events=max_events,
    )
    print("Stream finished.", file=sys.stderr, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
