"""TDD: Tests for async stream processing with asyncio."""
import pytest
from wikiki.processor import async_stream_processor


@pytest.mark.asyncio
async def test_handler_called_for_each_event():
    received = []

    async def handler(event):
        received.append(event)

    await async_stream_processor(
        iter([{"type": "edit", "title": "Alpha"}, {"type": "new", "title": "Beta"}]),
        handler,
        max_events=2,
    )

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

    await async_stream_processor(endless(), handler, max_events=5)

    assert len(received) == 5


@pytest.mark.asyncio
async def test_sync_handler_is_supported():
    received = []

    def sync_handler(event):
        received.append(event)

    await async_stream_processor(iter([{"type": "edit"}]), sync_handler, max_events=1)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_empty_stream_completes_without_error():
    await async_stream_processor(iter([]), lambda e: None)


@pytest.mark.asyncio
async def test_max_events_zero_processes_nothing():
    received = []

    async def handler(event):
        received.append(event)

    await async_stream_processor(
        iter([{"type": "edit"}, {"type": "edit"}]),
        handler,
        max_events=0,
    )

    assert len(received) == 0
