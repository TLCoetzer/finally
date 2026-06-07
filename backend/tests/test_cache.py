"""Unit tests for market.cache — PriceCache invariants."""
import threading
import time
import pytest

from market.cache import PriceCache
from market.types import Direction


# ---- First update semantics ----------------------------------------------

def test_first_update_sets_all_equal():
    """On first sight, price == prev_price == reference_price."""
    cache = PriceCache()
    q = cache.update("AAPL", 190.0, ts=1000.0)
    assert q.price == 190.0
    assert q.prev_price == 190.0
    assert q.reference_price == 190.0
    assert q.timestamp == 1000.0
    assert q.ticker == "AAPL"


def test_first_update_direction_is_flat():
    cache = PriceCache()
    q = cache.update("AAPL", 190.0)
    assert q.direction == Direction.FLAT


# ---- Subsequent update semantics -----------------------------------------

def test_second_update_rolls_prev_price():
    """After a second update, prev_price becomes the prior current price."""
    cache = PriceCache()
    cache.update("AAPL", 190.0, ts=1.0)
    q = cache.update("AAPL", 191.0, ts=2.0)
    assert q.price == 191.0
    assert q.prev_price == 190.0


def test_reference_price_never_changes():
    """reference_price stays fixed across many updates (Decision #1)."""
    cache = PriceCache()
    cache.update("AAPL", 190.0, ts=1.0)
    for price in [185.0, 195.0, 200.0, 180.0, 205.0]:
        q = cache.update("AAPL", price)
        assert q.reference_price == 190.0


def test_direction_after_multiple_updates():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    q = cache.update("AAPL", 191.0)
    assert q.direction == Direction.UP
    q = cache.update("AAPL", 189.0)
    assert q.direction == Direction.DOWN
    q = cache.update("AAPL", 189.0)
    assert q.direction == Direction.FLAT


# ---- Ticker normalisation ------------------------------------------------

def test_ticker_uppercased_on_update():
    cache = PriceCache()
    q = cache.update("aapl", 190.0)
    assert q.ticker == "AAPL"
    assert cache.get("AAPL") is not None


def test_get_is_case_insensitive():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    assert cache.get("aapl") is not None
    assert cache.get("AAPL") is not None


# ---- get ----------------------------------------------------------------

def test_get_returns_none_for_unknown_ticker():
    cache = PriceCache()
    assert cache.get("ZZZZ") is None


def test_get_returns_latest_quote():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("AAPL", 195.0)
    q = cache.get("AAPL")
    assert q is not None
    assert q.price == 195.0


# ---- all ----------------------------------------------------------------

def test_all_returns_copy():
    """all() must return an independent shallow copy — mutations must not
    affect the internal store."""
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    snapshot = cache.all()
    snapshot["EXTRA"] = None  # type: ignore[assignment]
    assert "EXTRA" not in cache.known_tickers()


def test_all_contains_all_tickers():
    cache = PriceCache()
    for ticker, price in [("AAPL", 190.0), ("MSFT", 420.0), ("GOOGL", 175.0)]:
        cache.update(ticker, price)
    result = cache.all()
    assert set(result) == {"AAPL", "MSFT", "GOOGL"}


# ---- known_tickers -------------------------------------------------------

def test_known_tickers():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    assert cache.known_tickers() == {"AAPL", "MSFT"}


# ---- drop ----------------------------------------------------------------

def test_drop_removes_specified_tickers():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    cache.update("GOOGL", 175.0)
    cache.drop(["MSFT"])
    remaining = cache.known_tickers()
    assert "MSFT" not in remaining
    assert "AAPL" in remaining
    assert "GOOGL" in remaining


def test_drop_is_case_insensitive():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.drop(["aapl"])
    assert cache.get("AAPL") is None


def test_drop_nonexistent_is_harmless():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.drop(["ZZZZ"])  # should not raise
    assert cache.get("AAPL") is not None


def test_drop_multiple():
    cache = PriceCache()
    for t in ["AAPL", "MSFT", "GOOGL", "TSLA"]:
        cache.update(t, 100.0)
    cache.drop(["AAPL", "GOOGL"])
    assert "AAPL" not in cache.known_tickers()
    assert "GOOGL" not in cache.known_tickers()
    assert "MSFT" in cache.known_tickers()
    assert "TSLA" in cache.known_tickers()


# ---- timestamp defaults --------------------------------------------------

def test_default_timestamp_is_recent():
    before = time.time()
    cache = PriceCache()
    q = cache.update("AAPL", 190.0)
    after = time.time()
    assert before <= q.timestamp <= after


# ---- thread safety -------------------------------------------------------

def test_concurrent_updates_do_not_raise():
    """Multiple threads writing to the cache simultaneously must not corrupt
    the internal state or raise exceptions."""
    cache = PriceCache()
    errors: list[Exception] = []

    def writer(ticker: str, base_price: float):
        try:
            for i in range(50):
                cache.update(ticker, base_price + i)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(f"T{i}", float(i * 10)))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(cache.known_tickers()) == 5
