"""SSE detach: client disconnect must not cancel the agent producer."""

from __future__ import annotations

import asyncio

from agent_window.api.routes import _sse_detach_producer


def test_sse_detach_producer_survives_consumer_disconnect() -> None:
    produced: list[str] = []
    finished = asyncio.Event()

    async def slow_producer():
        for i in range(3):
            produced.append(f"line-{i}")
            yield f"line-{i}"
            await asyncio.sleep(0.05)
        finished.set()

    async def consume_one_then_disconnect() -> None:
        consumer = _sse_detach_producer(slow_producer)
        first = await consumer.__anext__()
        assert first == "line-0"
        await consumer.aclose()
        await asyncio.wait_for(finished.wait(), timeout=2.0)

    asyncio.run(consume_one_then_disconnect())
    assert produced == ["line-0", "line-1", "line-2"]
