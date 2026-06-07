"""Unit tests for market.massive — MassiveProvider (mocked REST)."""
import asyncio
import unittest.mock as mock_lib
from unittest.mock import AsyncMock, Mock
import httpx
import pytest

from market.cache import PriceCache
from market.massive import MassiveProvider


# ---- helpers -------------------------------------------------------------

def make_provider(**kwargs) -> tuple[PriceCache, MassiveProvider]:
    cache = PriceCache()
    provider = MassiveProvider(cache, api_key="test-key", **kwargs)
    return cache, provider


def mock_get_response(status_code: int = 200, json_data: dict | None = None) -> Mock:
    """Create a mock httpx response for provider._client.get()."""
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=Mock(spec=httpx.Request),
            response=Mock(status_code=status_code),
        )
    else:
        response.raise_for_status.return_value = None
    return response


def patch_client(provider: MassiveProvider, responses: list) -> None:
    """Replace provider._client with a mock that returns responses in order."""
    mock_client = Mock()
    mock_client.get = AsyncMock(side_effect=responses)
    mock_client.aclose = AsyncMock()
    provider._client = mock_client


# ---- source / provider metadata ------------------------------------------

def test_source_is_massive():
    _, provider = make_provider()
    assert provider.source == "massive"


# ---- _extract_price — fallback chain -------------------------------------

class TestExtractPrice:
    def test_last_trade_wins(self):
        snap = {
            "lastTrade": {"p": 190.42},
            "min": {"c": 190.0},
            "day": {"c": 189.5},
            "prevDay": {"c": 188.0},
        }
        assert MassiveProvider._extract_price(snap) == pytest.approx(190.42)

    def test_falls_back_to_min_c(self):
        snap = {
            "lastTrade": {},
            "min": {"c": 190.0},
            "day": {"c": 189.5},
        }
        assert MassiveProvider._extract_price(snap) == pytest.approx(190.0)

    def test_falls_back_to_day_c(self):
        snap = {
            "lastTrade": {},
            "min": {},
            "day": {"c": 189.5},
            "prevDay": {"c": 188.0},
        }
        assert MassiveProvider._extract_price(snap) == pytest.approx(189.5)

    def test_falls_back_to_prevday_c(self):
        snap = {
            "lastTrade": {},
            "min": {},
            "day": {},
            "prevDay": {"c": 188.0},
        }
        assert MassiveProvider._extract_price(snap) == pytest.approx(188.0)

    def test_returns_none_when_all_missing(self):
        snap = {"lastTrade": {}, "min": {}, "day": {}, "prevDay": {}}
        assert MassiveProvider._extract_price(snap) is None

    def test_returns_none_for_empty_snap(self):
        assert MassiveProvider._extract_price({}) is None

    def test_null_objects_are_tolerated(self):
        snap = {
            "lastTrade": None,
            "min": None,
            "day": None,
            "prevDay": {"c": 188.0},
        }
        assert MassiveProvider._extract_price(snap) == pytest.approx(188.0)

    def test_zero_price_skipped(self):
        """A price of 0 (falsy) should be treated as missing."""
        snap = {
            "lastTrade": {"p": 0},
            "min": {"c": 190.0},
        }
        assert MassiveProvider._extract_price(snap) == pytest.approx(190.0)

    def test_result_is_float(self):
        snap = {"lastTrade": {"p": "190.42"}}
        result = MassiveProvider._extract_price(snap)
        assert isinstance(result, float)


# ---- _poll_once ----------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_once_updates_cache():
    cache, provider = make_provider()
    provider.set_tracked({"AAPL", "MSFT"})

    snapshot_data = {
        "tickers": [
            {"ticker": "AAPL", "lastTrade": {"p": 190.42}, "updated": 1_699_564_800_000_000_000},
            {"ticker": "MSFT", "lastTrade": {"p": 377.80}, "updated": 1_699_564_800_000_000_000},
        ]
    }
    patch_client(provider, [mock_get_response(200, snapshot_data)])
    await provider._poll_once()

    aapl = cache.get("AAPL")
    msft = cache.get("MSFT")
    assert aapl is not None
    assert aapl.price == pytest.approx(190.42)
    assert msft is not None
    assert msft.price == pytest.approx(377.80)


@pytest.mark.asyncio
async def test_poll_once_missing_ticker_does_not_raise():
    """A ticker absent from the response (halted/invalid) must not raise;
    present tickers should still be updated."""
    cache, provider = make_provider()
    provider.set_tracked({"AAPL", "MSFT"})

    snapshot_data = {
        "tickers": [
            {"ticker": "AAPL", "lastTrade": {"p": 190.0}, "updated": 0},
            # MSFT absent — simulates count < len(requested)
        ]
    }
    patch_client(provider, [mock_get_response(200, snapshot_data)])
    await provider._poll_once()  # must not raise

    assert cache.get("AAPL") is not None
    assert cache.get("MSFT") is None  # was absent, never updated


@pytest.mark.asyncio
async def test_poll_once_skips_when_no_tracked_tickers():
    """If tracked is empty, _poll_once must not make any HTTP requests."""
    cache, provider = make_provider()
    # No set_tracked call — tracked is empty

    mock_client = Mock()
    mock_client.get = AsyncMock()
    provider._client = mock_client

    await provider._poll_once()
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_poll_once_timestamp_nanoseconds_to_seconds():
    """updated nanoseconds must be stored as seconds in the cache timestamp."""
    cache, provider = make_provider()
    provider.set_tracked({"AAPL"})

    ns_ts = 1_699_564_800_000_000_000
    expected_seconds = ns_ts / 1_000_000_000

    snapshot_data = {
        "tickers": [{"ticker": "AAPL", "lastTrade": {"p": 190.0}, "updated": ns_ts}]
    }
    patch_client(provider, [mock_get_response(200, snapshot_data)])
    await provider._poll_once()

    q = cache.get("AAPL")
    assert q is not None
    assert q.timestamp == pytest.approx(expected_seconds)


# ---- is_supported --------------------------------------------------------

@pytest.mark.asyncio
async def test_is_supported_known_ticker():
    cache, provider = make_provider()
    patch_client(provider, [
        mock_get_response(200, {"results": [{"ticker": "AAPL"}], "count": 1})
    ])
    assert await provider.is_supported("AAPL") is True


@pytest.mark.asyncio
async def test_is_supported_unknown_ticker():
    cache, provider = make_provider()
    patch_client(provider, [
        mock_get_response(200, {"results": [], "count": 0})
    ])
    assert await provider.is_supported("ZZZZ") is False


@pytest.mark.asyncio
async def test_is_supported_lowercase_normalised():
    cache, provider = make_provider()
    patch_client(provider, [
        mock_get_response(200, {"results": [{"ticker": "AAPL"}], "count": 1})
    ])
    assert await provider.is_supported("aapl") is True


@pytest.mark.asyncio
async def test_is_supported_wrong_ticker_in_results():
    """If the API returns results but the ticker doesn't match, reject."""
    cache, provider = make_provider()
    patch_client(provider, [
        mock_get_response(200, {"results": [{"ticker": "AAPLX"}], "count": 1})
    ])
    assert await provider.is_supported("AAPL") is False


@pytest.mark.asyncio
async def test_is_supported_memoised():
    """Second call for the same ticker must NOT make another HTTP request."""
    cache, provider = make_provider()
    mock_client = Mock()
    mock_client.get = AsyncMock(
        return_value=mock_get_response(200, {"results": [{"ticker": "AAPL"}]})
    )
    mock_client.aclose = AsyncMock()
    provider._client = mock_client

    await provider.is_supported("AAPL")
    await provider.is_supported("AAPL")  # second call

    assert mock_client.get.call_count == 1, "should only call API once (memoised)"


@pytest.mark.asyncio
async def test_is_supported_fails_closed_on_network_error():
    """A network error must return False (fail closed) and not raise."""
    cache, provider = make_provider()
    mock_client = Mock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    mock_client.aclose = AsyncMock()
    provider._client = mock_client

    result = await provider.is_supported("AAPL")
    assert result is False


@pytest.mark.asyncio
async def test_is_supported_fails_closed_on_http_error():
    cache, provider = make_provider()
    patch_client(provider, [mock_get_response(500, {})])
    result = await provider.is_supported("AAPL")
    assert result is False


# ---- backoff logic -------------------------------------------------------

def test_backoff_math_on_429():
    """429 doubles the backoff; success resets it; cap at 60s."""
    base = 15.0
    backoff = base

    backoff = min(backoff * 2, 60.0)
    assert backoff == 30.0

    backoff = min(backoff * 2, 60.0)
    assert backoff == 60.0

    backoff = min(backoff * 2, 60.0)
    assert backoff == 60.0  # capped

    backoff = base  # recovered
    assert backoff == 15.0


@pytest.mark.asyncio
async def test_loop_429_causes_backoff_and_recovery():
    """Integration test: 429 on first cycle doubles sleep; success on second
    restores base interval.  Patches asyncio.sleep to avoid actual delays."""
    cache, provider = make_provider(poll_seconds=5.0)
    provider.set_tracked({"AAPL"})

    call_count = 0
    sleep_durations: list[float] = []

    async def mock_poll_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = Mock(status_code=429)
            raise httpx.HTTPStatusError("429", request=Mock(), response=resp)
        # second call succeeds

    async def mock_sleep(seconds: float) -> None:
        sleep_durations.append(seconds)
        if len(sleep_durations) >= 2:
            raise asyncio.CancelledError  # stop the loop after 2 sleeps

    provider._poll_once = mock_poll_once  # type: ignore[method-assign]

    with mock_lib.patch.object(asyncio, "sleep", mock_sleep):
        provider._task = asyncio.create_task(provider._loop())
        try:
            await asyncio.wait_for(provider._task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    assert sleep_durations[0] == pytest.approx(10.0)  # 5 * 2 = 10 after 429
    assert sleep_durations[1] == pytest.approx(5.0)   # recovered


# ---- lifecycle -----------------------------------------------------------

@pytest.mark.asyncio
async def test_start_and_stop():
    cache, provider = make_provider()
    await provider.start()
    assert provider._task is not None and not provider._task.done()
    await provider.stop()
    assert provider._task is None


@pytest.mark.asyncio
async def test_start_is_idempotent():
    cache, provider = make_provider()
    await provider.start()
    first_task = provider._task
    await provider.start()
    assert provider._task is first_task
    await provider.stop()
