import json
from typing import Iterator

import requests
import sseclient

WIKIMEDIA_SSE_URL = "https://stream.wikimedia.org/v2/stream/recentchange"

# Wikimedia policy requires a descriptive User-Agent (https://meta.wikimedia.org/wiki/User-Agent_policy)
_USER_AGENT = "WikiKI/0.1.0 (https://github.com/seojeongm/wikiki; aboutime.seojeong@gmail.com) python-requests"


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
