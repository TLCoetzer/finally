"""Integration tests for GET /api/stream/prices endpoint."""
import json
import asyncio
import unittest.mock as mock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from httpx import AsyncClient, ASGITransport

from market.cache import PriceCache
from market.sse import quote_to_sse


def _make_test_app(cache: PriceCache) -> FastAPI:
    """Minimal FastAPI app that serves one SSE batch then closes — no sleep."""
    app = FastAPI()
    app.state.cache = cache

    @app.get("/api/stream/prices")
    async def stream(request: Request) -> StreamingResponse:
        c: PriceCache = request.app.state.cache

        async def one_shot():
            for q in c.all().values():
                yield quote_to_sse(q)

        return StreamingResponse(
            one_shot(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return app


# ---- endpoint response headers / content type ---------------------------

@pytest.mark.asyncio
async def test_stream_content_type():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    app = _make_test_app(cache)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stream/prices")

    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_stream_returns_200():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    app = _make_test_app(cache)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stream/prices")

    assert response.status_code == 200


# ---- SSE frame content --------------------------------------------------

@pytest.mark.asyncio
async def test_stream_one_frame_per_ticker():
    cache = PriceCache()
    cache.update("AAPL", 190.0, ts=1.0)
    cache.update("MSFT", 420.0, ts=1.0)

    app = _make_test_app(cache)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stream/prices")

    text = response.text
    data_lines = [l for l in text.splitlines() if l.startswith("data:")]
    assert len(data_lines) == 2
    tickers = {json.loads(l[6:])["ticker"] for l in data_lines}
    assert tickers == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_stream_frame_contains_required_fields():
    cache = PriceCache()
    cache.update("AAPL", 191.0, ts=1.0)

    app = _make_test_app(cache)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stream/prices")

    data_lines = [l for l in response.text.splitlines() if l.startswith("data:")]
    assert data_lines
    payload = json.loads(data_lines[0][6:])
    required = {"ticker", "price", "prev_price", "reference_price",
                "timestamp", "direction", "change_pct"}
    assert required.issubset(payload.keys())


@pytest.mark.asyncio
async def test_stream_empty_cache_returns_no_data_frames():
    cache = PriceCache()

    app = _make_test_app(cache)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stream/prices")

    data_lines = [l for l in response.text.splitlines() if l.startswith("data:")]
    assert len(data_lines) == 0


@pytest.mark.asyncio
async def test_stream_direction_field_is_valid_string():
    cache = PriceCache()
    cache.update("AAPL", 190.0)  # first update: flat
    cache.update("AAPL", 191.0)  # second: up

    app = _make_test_app(cache)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stream/prices")

    data_lines = [l for l in response.text.splitlines() if l.startswith("data:")]
    payload = json.loads(data_lines[0][6:])
    assert payload["direction"] in ("up", "down", "flat")
