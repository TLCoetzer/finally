"""Cross-provider conformance suite (MARKET_INTERFACE.md §9, DESIGN §13.2).

Both SimulatorProvider and MassiveProvider must satisfy the same
MarketDataProvider contract and write the same Quote shape into the cache.
The suite is parametrised so every assertion runs against both providers."""
import random
from unittest.mock import AsyncMock, Mock

import pytest

from market.cache import PriceCache
from market.provider import MarketDataProvider
from market.simulator import SimulatorProvider
from market.massive import MassiveProvider
from market.types import Quote

KNOWN = ("AAPL", "MSFT")  # supported in both the sim universe and the mock


async def _make_simulator() -> tuple[PriceCache, SimulatorProvider]:
    cache = PriceCache()
    provider = SimulatorProvider(cache, rng=random.Random(0))
    provider.set_tracked(set(KNOWN))
    provider._step()  # populate the cache
    return cache, provider


async def _make_massive() -> tuple[PriceCache, MassiveProvider]:
    cache = PriceCache()
    provider = MassiveProvider(cache, api_key="test-key")
    provider.set_tracked(set(KNOWN))

    snapshot = {"tickers": [
        {"ticker": "AAPL", "lastTrade": {"p": 190.0}, "updated": 0},
        {"ticker": "MSFT", "lastTrade": {"p": 420.0}, "updated": 0},
    ]}

    async def fake_get(url, params=None):
        resp = Mock()
        resp.raise_for_status.return_value = None
        if "snapshot" in url:
            resp.json.return_value = snapshot
        else:  # /v3/reference/tickers
            t = (params or {}).get("ticker", "")
            results = [{"ticker": t}] if t in KNOWN else []
            resp.json.return_value = {"results": results}
        return resp

    client = Mock()
    client.get = AsyncMock(side_effect=fake_get)
    client.aclose = AsyncMock()
    provider._client = client
    await provider._poll_once()  # populate the cache
    return cache, provider


@pytest.fixture(params=["simulator", "massive"])
async def populated(request):
    cache, provider = await (
        _make_simulator() if request.param == "simulator" else _make_massive()
    )
    yield cache, provider
    await provider.stop()


@pytest.mark.asyncio
async def test_is_a_market_data_provider(populated):
    _, provider = populated
    assert isinstance(provider, MarketDataProvider)


@pytest.mark.asyncio
async def test_source_is_known_string(populated):
    _, provider = populated
    assert provider.source in ("simulator", "massive")


@pytest.mark.asyncio
async def test_cache_holds_quote_shape_for_tracked(populated):
    _, provider = populated
    quotes = provider.get_all_quotes()
    assert set(quotes) == set(KNOWN)
    for q in quotes.values():
        assert isinstance(q, Quote)
        assert q.price > 0
        assert q.reference_price > 0


@pytest.mark.asyncio
async def test_get_quote_is_case_insensitive(populated):
    _, provider = populated
    assert provider.get_quote("AAPL") is not None
    assert provider.get_quote("aapl") is not None
    assert provider.get_quote("ZZZZ") is None


@pytest.mark.asyncio
async def test_is_supported_known_and_unknown(populated):
    _, provider = populated
    assert await provider.is_supported("AAPL") is True
    assert await provider.is_supported("ZZZZ") is False


@pytest.mark.asyncio
async def test_set_tracked_drops_untracked(populated):
    _, provider = populated
    provider.set_tracked({"AAPL"})
    assert provider.tracked == {"AAPL"}
    assert provider.get_quote("MSFT") is None
