"""
TDD: Tests for SSE stream reception and JSON validation.
Completion criteria 1 & 2.
"""
import pytest
import requests
from unittest.mock import Mock, patch

from wikiki.stream import parse_event, SSEStreamClient, WIKIMEDIA_SSE_URL


class TestParseEvent:
    def test_valid_json_returns_dict(self):
        data = '{"server_name": "en.wikipedia.org", "type": "edit", "title": "Python"}'
        result = parse_event(data)
        assert result["server_name"] == "en.wikipedia.org"
        assert result["type"] == "edit"

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_event("not valid json {{{")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_event("")

    def test_nested_json_is_parsed(self):
        data = '{"title": "Test", "meta": {"dt": "2026-01-01", "id": "abc123"}}'
        result = parse_event(data)
        assert result["meta"]["id"] == "abc123"

    def test_wikimedia_recentchange_shape(self):
        data = (
            '{"$schema":"/mediawiki/recentchange/1.0.0",'
            '"type":"edit","title":"Edit war","server_name":"en.wikipedia.org",'
            '"user":"Alice","bot":false,"revision":{"old":100,"new":101}}'
        )
        result = parse_event(data)
        assert result["type"] == "edit"
        assert result["revision"]["new"] == 101


class TestSSEStreamClient:
    def test_default_url_is_wikimedia(self):
        client = SSEStreamClient()
        assert client.url == WIKIMEDIA_SSE_URL

    def test_custom_url_is_accepted(self):
        client = SSEStreamClient(url="https://example.com/stream")
        assert client.url == "https://example.com/stream"

    def test_stream_events_yields_parsed_dicts(self):
        mock_event = Mock()
        mock_event.data = '{"type": "edit", "title": "Test"}'

        with patch("wikiki.stream.requests.get") as mock_get, \
             patch("wikiki.stream.sseclient.SSEClient") as mock_sse:
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            mock_sse.return_value.events.return_value = [mock_event]

            events = list(SSEStreamClient().stream_events())

        assert len(events) == 1
        assert events[0]["type"] == "edit"
        assert events[0]["title"] == "Test"

    def test_stream_events_skips_empty_data(self):
        mock_empty = Mock()
        mock_empty.data = ""
        mock_valid = Mock()
        mock_valid.data = '{"type": "new"}'

        with patch("wikiki.stream.requests.get") as mock_get, \
             patch("wikiki.stream.sseclient.SSEClient") as mock_sse:
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            mock_sse.return_value.events.return_value = [mock_empty, mock_valid]

            events = list(SSEStreamClient().stream_events())

        assert len(events) == 1
        assert events[0]["type"] == "new"

    def test_stream_raises_on_http_error(self):
        with patch("wikiki.stream.requests.get") as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.HTTPError("403")
            mock_get.return_value = mock_response

            with pytest.raises(requests.HTTPError):
                list(SSEStreamClient().stream_events())

    def test_multiple_events_all_yielded(self):
        raw = [
            '{"type":"edit","title":"A"}',
            '{"type":"new","title":"B"}',
            '{"type":"edit","title":"C"}',
        ]
        mock_events = [Mock(data=d) for d in raw]

        with patch("wikiki.stream.requests.get") as mock_get, \
             patch("wikiki.stream.sseclient.SSEClient") as mock_sse:
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            mock_sse.return_value.events.return_value = mock_events

            events = list(SSEStreamClient().stream_events())

        assert len(events) == 3
        assert [e["title"] for e in events] == ["A", "B", "C"]
