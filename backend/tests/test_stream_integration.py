"""Integration test for the real GET /api/stream/prices endpoint.

Unlike test_stream.py (which builds a stand-in endpoint), this drives the
actual api.stream.stream_prices handler and the real _price_event_gen body,
exercising the response media type, headers, and the heartbeat. The handler
is invoked directly with a one-shot request so the otherwise-infinite stream
terminates deterministically (ASGITransport would block on it forever)."""
import asyncio
import json
import unittest.mock as mock

import pytest

from market.cache import PriceCache
from api.stream import stream_prices


class _OneShotRequest:
    """is_disconnected() returns False once, then True — one batch, then exit."""

    def __init__(self) -> None:
        self._calls = 0

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > 1


@pytest.mark.asyncio
async def test_real_endpoint_headers_and_streamed_body():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)

    response = await stream_prices(_OneShotRequest(), cache)  # real handler

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    required = {"ticker", "price", "prev_price", "reference_price",
                "timestamp", "direction", "change_pct"}
    chunks: list[str] = []
    with mock.patch.object(asyncio, "sleep", mock.AsyncMock()):
        async for chunk in response.body_iterator:
            chunks.append(chunk)

    data = [json.loads(c[len("data:"):].strip()) for c in chunks if c.startswith("data:")]
    assert {d["ticker"] for d in data} == {"AAPL", "MSFT"}
    for frame in data:
        assert required.issubset(frame.keys())
    assert any(c.startswith(": ping") for c in chunks), "expected a heartbeat"
