import asyncio
import inspect
from typing import Callable, Iterable, Optional


async def async_stream_processor(
    events: Iterable[dict],
    handler: Callable,
    max_events: Optional[int] = None,
) -> None:
    """Process SSE stream events asynchronously.

    Runs the blocking iterator in a thread-pool executor so the event
    loop stays free during long HTTP waits between events.
    """
    loop = asyncio.get_running_loop()
    _DONE = object()
    event_iter = iter(events)

    def _next() -> object:
        try:
            return next(event_iter)
        except StopIteration:
            return _DONE

    count = 0
    while True:
        if max_events is not None and count >= max_events:
            break

        event = await loop.run_in_executor(None, _next)
        if event is _DONE:
            break

        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            result = await loop.run_in_executor(None, handler, event)
            if inspect.isawaitable(result):
                await result

        count += 1
