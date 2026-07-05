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
import redis as redis_module
from wikiki.storage import RedisRepository, SQLiteRepository, connect
from wikiki.stream import SSEStreamClient, stream_with_reconnect


class RedisDashboard:
    def __init__(self, repo: RedisRepository) -> None:
        self._repo = repo

    def update(self, stats: ArticleStats) -> None:
        self._repo.upsert_stats(stats, last_seen_at=int(time.time()))


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
    r = redis_module.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    sqlite_repo = SQLiteRepository(db)
    repo = RedisRepository(r, sqlite_repo)

    engine = RuleEngine()
    engine.add_strategy(ThreeRRStrategy())
    engine.add_strategy(VelocitySpikeStrategy(window_seconds=3600, threshold=3))
    engine.add_strategy(EditorConflictStrategy(window_seconds=3600, min_editors=2))

    coordinator = Coordinator(
        repo=repo,
        engine=engine,
        scorer=TensionScorer(),
        dashboard=RedisDashboard(repo),
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

    try:
        await async_stream_processor(
            enwiki_stream,
            handle,
            max_events=max_events,
        )
    finally:
        sqlite_repo.flush()
    print("Stream finished.", file=sys.stderr, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
