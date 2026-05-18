"""TDD: Tests for automatic stream reconnection."""
import requests
import pytest
from unittest.mock import patch

from wikiki.stream import SSEStreamClient, stream_with_reconnect


class TestStreamWithReconnect:
    def test_yields_events_from_healthy_stream(self):
        client = SSEStreamClient()
        with patch.object(client, "stream_events", return_value=iter([
            {"type": "edit", "title": "A"},
            {"type": "edit", "title": "B"},
        ])):
            events = []
            for event in stream_with_reconnect(client, retry_delay=0):
                events.append(event)
                if len(events) == 2:
                    break
        assert [e["title"] for e in events] == ["A", "B"]

    def test_reconnects_after_connection_error(self):
        call_count = 0

        def stream_mock():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.ConnectionError("connection lost")
            yield {"type": "edit", "title": "After reconnect"}

        client = SSEStreamClient()
        with patch.object(client, "stream_events", side_effect=stream_mock):
            events = []
            for event in stream_with_reconnect(client, retry_delay=0):
                events.append(event)
                break

        assert call_count == 2
        assert events[0]["title"] == "After reconnect"

    def test_reconnects_after_os_error(self):
        call_count = 0

        def stream_mock():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("socket closed")
            yield {"type": "edit", "title": "Recovered"}

        client = SSEStreamClient()
        with patch.object(client, "stream_events", side_effect=stream_mock):
            events = []
            for event in stream_with_reconnect(client, retry_delay=0):
                events.append(event)
                break

        assert call_count == 2
        assert events[0]["title"] == "Recovered"

    def test_reconnects_multiple_times(self):
        call_count = 0

        def stream_mock():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.ConnectionError("drop")
            yield {"type": "edit", "title": "Final"}

        client = SSEStreamClient()
        with patch.object(client, "stream_events", side_effect=stream_mock):
            events = []
            for event in stream_with_reconnect(client, retry_delay=0):
                events.append(event)
                break

        assert call_count == 3
        assert events[0]["title"] == "Final"
