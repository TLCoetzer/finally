"""Unit tests for tracking — tracked_tickers / recompute_tracked."""
from types import SimpleNamespace

import random

import tracking
from market.cache import PriceCache
from market.simulator import SimulatorProvider


def test_tracked_tickers_is_uppercased_union(monkeypatch):
    monkeypatch.setattr(tracking.db, "watchlist_tickers", lambda: ["AAPL", "msft"])
    monkeypatch.setattr(tracking.db, "position_tickers", lambda: ["msft", "NVDA"])
    assert tracking.tracked_tickers() == {"AAPL", "MSFT", "NVDA"}


def test_tracked_tickers_empty(monkeypatch):
    monkeypatch.setattr(tracking.db, "watchlist_tickers", lambda: [])
    monkeypatch.setattr(tracking.db, "position_tickers", lambda: [])
    assert tracking.tracked_tickers() == set()


def test_recompute_tracked_pushes_union_to_provider(monkeypatch):
    monkeypatch.setattr(tracking.db, "watchlist_tickers", lambda: ["AAPL"])
    monkeypatch.setattr(tracking.db, "position_tickers", lambda: ["TSLA"])

    provider = SimulatorProvider(PriceCache(), rng=random.Random(0))
    app = SimpleNamespace(state=SimpleNamespace(provider=provider))

    tracking.recompute_tracked(app)
    assert provider.tracked == {"AAPL", "TSLA"}


def test_recompute_tracked_drops_removed_ticker(monkeypatch):
    """A held ticker dropped from both watchlist and positions is pruned."""
    monkeypatch.setattr(tracking.db, "watchlist_tickers", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(tracking.db, "position_tickers", lambda: [])

    cache = PriceCache()
    provider = SimulatorProvider(cache, rng=random.Random(0))
    app = SimpleNamespace(state=SimpleNamespace(provider=provider))
    tracking.recompute_tracked(app)
    provider._step()
    assert cache.get("MSFT") is not None

    monkeypatch.setattr(tracking.db, "watchlist_tickers", lambda: ["AAPL"])
    tracking.recompute_tracked(app)
    assert cache.get("MSFT") is None
    assert provider.tracked == {"AAPL"}
