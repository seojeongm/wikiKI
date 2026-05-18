import json
import os
import sys
import time
from typing import Iterator

import requests
import sseclient

WIKIMEDIA_SSE_URL = "https://stream.wikimedia.org/v2/stream/recentchange"

# Wikimedia policy requires a descriptive User-Agent (https://meta.wikimedia.org/wiki/User-Agent_policy)
_CONTACT = os.getenv("WIKIKI_CONTACT", "https://github.com/seojeongm/wikiki")
_USER_AGENT = f"WikiKI/0.1.0 ({_CONTACT}) python-requests"


def parse_event(data: str) -> dict:
    """Parse SSE event data string as JSON, raising ValueError on failure."""
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in SSE event data: {e}") from e


class SSEStreamClient:
    def __init__(self, url: str = WIKIMEDIA_SSE_URL) -> None:
        self.url = url

    def stream_events(self, connect_timeout: int = 10) -> Iterator[dict]:
        """Connect to the SSE endpoint and yield parsed event dicts.

        connect_timeout only limits the initial TCP handshake; read has no
        timeout because SSE events arrive at unpredictable intervals.
        """
        response = requests.get(
            self.url,
            stream=True,
            timeout=(connect_timeout, None),
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        client = sseclient.SSEClient(response)
        try:
            for event in client.events():
                if event.data:
                    yield parse_event(event.data)
        finally:
            response.close()


def stream_with_reconnect(
    client: SSEStreamClient,
    retry_delay: float = 5.0,
) -> Iterator[dict]:
    """Yield SSE events, automatically reconnecting on network errors."""
    while True:
        try:
            yield from client.stream_events()
        except (requests.RequestException, OSError) as e:
            print(f"Stream disconnected ({e}), reconnecting in {retry_delay}s...",
                  file=sys.stderr, flush=True)
            time.sleep(retry_delay)
