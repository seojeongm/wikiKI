"""TDD: Tests for async stream processing with asyncio."""
import pytest
from unittest.mock import Mock

from wikiki.stream import SSEStreamClient
from wikiki.processor import async_stream_processor


@pytest.mark.asyncio
async def test_handler_called_for_each_event():
    received = []

    async def handler(event):
        received.append(event)

    mock_client = Mock(spec=SSEStreamClient)
    mock_client.stream_events.return_value = iter([
        {"type": "edit", "title": "Alpha"},
        {"type": "new", "title": "Beta"},
    ])

    await async_stream_processor(mock_client, handler, max_events=2)

    assert len(received) == 2
    assert received[0]["title"] == "Alpha"
    assert received[1]["title"] == "Beta"


@pytest.mark.asyncio
async def test_max_events_limits_processing():
    received = []

    async def handler(event):
        received.append(event)

    def endless():
        i = 0
        while True:
            yield {"type": "edit", "seq": i}
            i += 1

    mock_client = Mock(spec=SSEStreamClient)
    mock_client.stream_events.return_value = endless()

    await async_stream_processor(mock_client, handler, max_events=5)

    assert len(received) == 5


@pytest.mark.asyncio
async def test_sync_handler_is_supported():
    received = []

    def sync_handler(event):
        received.append(event)

    mock_client = Mock(spec=SSEStreamClient)
    mock_client.stream_events.return_value = iter([{"type": "edit"}])

    await async_stream_processor(mock_client, sync_handler, max_events=1)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_empty_stream_completes_without_error():
    mock_client = Mock(spec=SSEStreamClient)
    mock_client.stream_events.return_value = iter([])

    await async_stream_processor(mock_client, lambda e: None)
