"""Route tests for portfolio, watchlist, and health (PLAN.md §8).

Each test gets a fresh temp SQLite DB (via FINALLY_DB_PATH) seeded by
init_if_needed, and a real FastAPI app wired with the actual routers plus a
stub provider/cache on app.state. The lifespan is bypassed so no background
provider or snapshot loop starts — state is injected directly."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from market.cache import PriceCache
from market.provider import MarketDataProvider
from api import portfolio, watchlist, health


class StubProvider(MarketDataProvider):
    """Minimal provider: a fixed supported set and a 'simulator' source.
    No background loop — tests drive the cache directly."""

    def __init__(self, cache: PriceCache, supported: set[str]) -> None:
        super().__init__(cache)
        self._supported = {t.upper() for t in supported}

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def is_supported(self, ticker: str) -> bool:
        return ticker.upper() in self._supported

    @property
    def source(self) -> str:
        return "simulator"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    db.reset_for_tests()
    db.init_if_needed()

    cache = PriceCache()
    provider = StubProvider(cache, supported={"AAPL", "MSFT", "NVDA", "AMD"})

    app = FastAPI()
    app.state.cache = cache
    app.state.provider = provider
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(health.router)

    with TestClient(app) as c:
        c.cache = cache  # expose for price setup in tests
        yield c

    db.reset_for_tests()


def _price(client: TestClient, ticker: str, price: float) -> None:
    client.cache.update(ticker, price)


# ---- health -------------------------------------------------------------

def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "source": "simulator"}


# ---- watchlist ----------------------------------------------------------

def test_get_watchlist_returns_seeded_tickers(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    tickers = [i["ticker"] for i in r.json()["tickers"]]
    assert "AAPL" in tickers and len(tickers) == 10


def test_get_watchlist_includes_price_when_cached(client):
    _price(client, "AAPL", 190.0)
    r = client.get("/api/watchlist")
    aapl = next(i for i in r.json()["tickers"] if i["ticker"] == "AAPL")
    assert aapl["price"] == 190.0
    assert aapl["reference_price"] == 190.0


def test_get_watchlist_price_none_until_first_tick(client):
    r = client.get("/api/watchlist")
    aapl = next(i for i in r.json()["tickers"] if i["ticker"] == "AAPL")
    assert aapl["price"] is None


def test_add_watchlist_supported_ticker(client):
    r = client.post("/api/watchlist", json={"ticker": "amd"})
    assert r.status_code == 201
    assert r.json()["ticker"] == "AMD"
    assert "AMD" in db.watchlist_tickers()


def test_add_watchlist_rejects_unsupported_ticker(client):
    r = client.post("/api/watchlist", json={"ticker": "ZZZZ"})
    assert r.status_code == 400
    assert "ZZZZ" in r.json()["detail"]
    assert "ZZZZ" not in db.watchlist_tickers()


def test_remove_watchlist(client):
    r = client.delete("/api/watchlist/AAPL")
    assert r.status_code == 204
    assert "AAPL" not in db.watchlist_tickers()


def test_remove_watchlist_absent_is_noop(client):
    r = client.delete("/api/watchlist/ZZZZ")
    assert r.status_code == 204


# ---- portfolio: GET -----------------------------------------------------

def test_get_portfolio_fresh(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["cash"] == 10000.0
    assert body["positions"] == []
    assert body["total_value"] == 10000.0


def test_get_portfolio_after_buy_prices_position(client):
    _price(client, "AAPL", 190.0)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    _price(client, "AAPL", 200.0)  # price moves up after the fill

    body = client.get("/api/portfolio").json()
    pos = body["positions"][0]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 190.0
    assert pos["price"] == 200.0
    assert pos["market_value"] == 2000.0
    assert pos["unrealized_pnl"] == 100.0  # (200-190)*10
    assert pos["change_pct"] == pytest.approx((200 - 190) / 190 * 100)
    # cash 10000 - 1900 = 8100; total = 8100 + 2000 = 10100
    assert body["cash"] == pytest.approx(8100.0)
    assert body["total_value"] == pytest.approx(10100.0)


# ---- portfolio: trade ---------------------------------------------------

def test_trade_buy_succeeds(client):
    _price(client, "AAPL", 190.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["side"] == "buy"
    assert body["quantity"] == 5
    assert body["price"] == 190.0
    assert body["cash"] == pytest.approx(10000.0 - 5 * 190.0)


def test_trade_sell_succeeds(client):
    _price(client, "AAPL", 190.0)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "buy"})
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "sell"})
    assert r.status_code == 200
    assert r.json()["side"] == "sell"
    assert db.get_position("AAPL")["quantity"] == 3


def test_trade_full_sell_removes_position(client):
    _price(client, "AAPL", 190.0)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "buy"})
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 5, "side": "sell"})
    assert db.get_position("AAPL") is None
    assert client.get("/api/portfolio").json()["positions"] == []


def test_trade_rejects_insufficient_cash(client):
    _price(client, "AAPL", 190.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1000, "side": "buy"})
    assert r.status_code == 400
    assert "cash" in r.json()["detail"].lower()


def test_trade_rejects_insufficient_shares(client):
    _price(client, "AAPL", 190.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"})
    assert r.status_code == 400
    assert "shares" in r.json()["detail"].lower()


def test_trade_rejects_invalid_side(client):
    _price(client, "AAPL", 190.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "hold"})
    assert r.status_code == 400


def test_trade_rejects_unpriced_ticker(client):
    # NVDA is supported but has never ticked -> no cache price
    r = client.post("/api/portfolio/trade", json={"ticker": "NVDA", "quantity": 1, "side": "buy"})
    assert r.status_code == 400
    assert "price" in r.json()["detail"].lower()


def test_trade_rejects_nonpositive_quantity(client):
    _price(client, "AAPL", 190.0)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0, "side": "buy"})
    assert r.status_code == 422  # pydantic gt=0 validation
