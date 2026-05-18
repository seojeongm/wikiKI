"""
Integration tests: live Wikimedia SSE connection.
Run with: pytest --integration
Completion criteria 1 & 2 (live).
"""
import pytest
from wikiki.stream import SSEStreamClient


@pytest.mark.integration
def test_wikimedia_sse_connects_and_receives_event():
    """Can connect to Wikimedia SSE and receive at least one event."""
    client = SSEStreamClient()
    events = []

    for event in client.stream_events():
        events.append(event)
        break  # one event is enough

    assert len(events) == 1
    assert isinstance(events[0], dict)


@pytest.mark.integration
def test_received_events_are_valid_json_with_expected_fields():
    """Wikimedia recentchange events have required JSON fields."""
    client = SSEStreamClient()

    for event in client.stream_events():
        assert isinstance(event, dict)
        # Every Wikimedia SSE event carries at least one of these
        assert any(k in event for k in ("$schema", "type", "server_name", "wiki"))
        break
