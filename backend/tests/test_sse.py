"""Unit tests for market.sse — SSE serialisation and the streaming endpoint."""
import asyncio
import json
import unittest.mock as mock

import pytest

from market.cache import PriceCache
from market.sse import quote_to_sse
from market.types import Direction, Quote


# ---- quote_to_sse — format -----------------------------------------------

def make_quote(
    ticker: str = "AAPL",
    price: float = 191.0,
    prev_price: float = 190.0,
    reference_price: float = 190.0,
    timestamp: float = 1_699_564_800.0,
) -> Quote:
    return Quote(ticker, price, prev_price, reference_price, timestamp)


def test_sse_starts_with_data_prefix():
    frame = quote_to_sse(make_quote())
    assert frame.startswith("data: ")


def test_sse_ends_with_double_newline():
    frame = quote_to_sse(make_quote())
    assert frame.endswith("\n\n")


def test_sse_payload_is_valid_json():
    frame = quote_to_sse(make_quote())
    payload_str = frame[len("data: "):].strip()
    payload = json.loads(payload_str)  # must not raise
    assert isinstance(payload, dict)


def test_sse_contains_required_fields():
    required = {"ticker", "price", "prev_price", "reference_price",
                 "timestamp", "direction", "change_pct"}
    frame = quote_to_sse(make_quote())
    payload = json.loads(frame[6:].strip())
    assert required.issubset(payload.keys())


def test_sse_ticker_value():
    frame = quote_to_sse(make_quote(ticker="MSFT"))
    payload = json.loads(frame[6:].strip())
    assert payload["ticker"] == "MSFT"


def test_sse_price_values():
    frame = quote_to_sse(make_quote(price=191.5, prev_price=190.0, reference_price=190.0))
    payload = json.loads(frame[6:].strip())
    assert payload["price"] == pytest.approx(191.5)
    assert payload["prev_price"] == pytest.approx(190.0)
    assert payload["reference_price"] == pytest.approx(190.0)


def test_sse_direction_up():
    frame = quote_to_sse(make_quote(price=191.0, prev_price=190.0))
    payload = json.loads(frame[6:].strip())
    assert payload["direction"] == "up"


def test_sse_direction_down():
    frame = quote_to_sse(make_quote(price=189.0, prev_price=190.0))
    payload = json.loads(frame[6:].strip())
    assert payload["direction"] == "down"


def test_sse_direction_flat():
    frame = quote_to_sse(make_quote(price=190.0, prev_price=190.0))
    payload = json.loads(frame[6:].strip())
    assert payload["direction"] == "flat"


def test_sse_change_pct_positive():
    # 1% above reference
    frame = quote_to_sse(make_quote(price=191.0, reference_price=190.0))
    payload = json.loads(frame[6:].strip())
    assert payload["change_pct"] == pytest.approx(
        (191.0 - 190.0) / 190.0 * 100.0, rel=1e-3
    )


def test_sse_change_pct_negative():
    frame = quote_to_sse(make_quote(price=180.0, reference_price=200.0))
    payload = json.loads(frame[6:].strip())
    assert payload["change_pct"] < 0


def test_sse_change_pct_rounded_to_4_decimals():
    """change_pct must be rounded to 4 decimal places."""
    frame = quote_to_sse(make_quote(price=190.123456789, reference_price=190.0))
    payload = json.loads(frame[6:].strip())
    # round-trip via JSON should preserve 4dp precision but no more
    change_pct_str = str(payload["change_pct"])
    decimal_part = change_pct_str.split(".")[-1] if "." in change_pct_str else ""
    assert len(decimal_part) <= 4


def test_sse_timestamp():
    frame = quote_to_sse(make_quote(timestamp=1_699_564_800.0))
    payload = json.loads(frame[6:].strip())
    assert payload["timestamp"] == pytest.approx(1_699_564_800.0)


# ---- _price_event_gen — generator logic ----------------------------------

class _OneShotRequest:
    """Returns is_disconnected=False once then True, so the generator yields
    one batch of events and exits cleanly without sleeping."""

    def __init__(self) -> None:
        self._calls = 0

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > 1  # False on first call, True thereafter


@pytest.mark.asyncio
async def test_price_event_gen_yields_one_frame_per_ticker():
    from api.stream import _price_event_gen

    cache = PriceCache()
    cache.update("AAPL", 190.0, ts=1.0)
    cache.update("MSFT", 420.0, ts=1.0)

    request = _OneShotRequest()
    frames = []

    # Patch asyncio.sleep to return immediately
    fast_sleep = mock.AsyncMock(return_value=None)
    with mock.patch.object(asyncio, "sleep", fast_sleep):
        async for chunk in _price_event_gen(request, cache):
            if chunk.startswith("data:"):
                frames.append(json.loads(chunk[6:].strip()))

    tickers_seen = {f["ticker"] for f in frames}
    assert tickers_seen == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_price_event_gen_includes_heartbeat():
    from api.stream import _price_event_gen

    cache = PriceCache()
    cache.update("AAPL", 190.0)

    request = _OneShotRequest()
    chunks: list[str] = []

    fast_sleep = mock.AsyncMock(return_value=None)
    with mock.patch.object(asyncio, "sleep", fast_sleep):
        async for chunk in _price_event_gen(request, cache):
            chunks.append(chunk)

    heartbeats = [c for c in chunks if c.startswith(": ping")]
    assert len(heartbeats) >= 1


@pytest.mark.asyncio
async def test_price_event_gen_frame_has_required_fields():
    from api.stream import _price_event_gen

    cache = PriceCache()
    cache.update("AAPL", 190.0)

    request = _OneShotRequest()
    required = {"ticker", "price", "prev_price", "reference_price",
                "timestamp", "direction", "change_pct"}

    fast_sleep = mock.AsyncMock(return_value=None)
    data_frames = []
    with mock.patch.object(asyncio, "sleep", fast_sleep):
        async for chunk in _price_event_gen(request, cache):
            if chunk.startswith("data:"):
                data_frames.append(json.loads(chunk[6:].strip()))

    assert data_frames, "no data frames yielded"
    for frame in data_frames:
        assert required.issubset(frame.keys()), f"frame missing keys: {frame}"
