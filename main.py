import asyncio
import json
import os
import sys
from dataclasses import asdict

sys.stdout.reconfigure(encoding="utf-8")

from wikiki.parser import is_enwiki_edit, parse_edit_event
from wikiki.processor import async_stream_processor
from wikiki.storage import connect, save_event
from wikiki.stream import SSEStreamClient, stream_with_reconnect


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
    client = SSEStreamClient()
    print("Connecting to Wikimedia SSE stream...", file=sys.stderr, flush=True)

    enwiki_stream = (e for e in stream_with_reconnect(client) if is_enwiki_edit(e))

    async def handle(event: dict) -> None:
        edit = parse_edit_event(event)
        save_event(db, edit)
        print(json.dumps(asdict(edit), ensure_ascii=False), flush=True)

    await async_stream_processor(
        enwiki_stream,
        handle,
        max_events=max_events,
    )
    print("Stream finished.", file=sys.stderr, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
