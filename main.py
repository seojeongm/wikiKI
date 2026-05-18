import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from wikiki.processor import async_stream_processor
from wikiki.stream import SSEStreamClient


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

    client = SSEStreamClient()
    print("Connecting to Wikimedia SSE stream...", file=sys.stderr, flush=True)

    async def handle(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    await async_stream_processor(client, handle, max_events=max_events)
    print("Stream finished.", file=sys.stderr, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
