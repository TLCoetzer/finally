"""Chat route + executor integration tests (PLAN.md §8, §9).

Each test gets a fresh temp SQLite DB and a real app wired with the chat router,
a StubProvider, and a PriceCache. LLM_MOCK=true so responses are deterministic
and no network/API key is needed. Verifies auto-execution through the shared
trade/watchlist path, inline failure surfacing, persistence, and the 20-message
context cap (asserted at the executor level)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from market.cache import PriceCache
from market.provider import MarketDataProvider
from api import chat
from llm import executor
from llm.prompt import MAX_HISTORY


class StubProvider(MarketDataProvider):
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
    monkeypatch.setenv("LLM_MOCK", "true")
    db.reset_for_tests()
    db.init_if_needed()

    cache = PriceCache()
    provider = StubProvider(cache, supported={"AAPL", "MSFT", "NVDA", "PYPL"})

    app = FastAPI()
    app.state.cache = cache
    app.state.provider = provider
    app.include_router(chat.router)

    with TestClient(app) as c:
        c.cache = cache
        yield c

    db.reset_for_tests()


def _price(client: TestClient, ticker: str, price: float) -> None:
    client.cache.update(ticker, price)


# ---- plain reply --------------------------------------------------------

def test_plain_reply_no_actions(client):
    r = client.post("/api/chat", json={"message": "How is my portfolio?"})
    assert r.status_code == 200
    body = r.json()
    assert body["message"]
    assert body["actions"] == []


def test_messages_persisted(client):
    client.post("/api/chat", json={"message": "hello there"})
    history = db.recent_chat(20)
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "hello there"


# ---- trade auto-execution ----------------------------------------------

def test_buy_executes_through_shared_path(client):
    _price(client, "AAPL", 190.0)
    r = client.post("/api/chat", json={"message": "buy 1 AAPL"})
    body = r.json()
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["kind"] == "trade"
    assert action["ok"] is True
    assert "AAPL" in action["summary"]
    # position actually created in the DB via the real execution path
    assert db.get_position("AAPL")["quantity"] == 1
    assert db.get_cash() == pytest.approx(10000.0 - 190.0)


def test_failed_buy_surfaced_inline_not_raised(client):
    # Mock buys 1 share, but no price is cached -> shared path raises TradeError,
    # which the executor captures as an ok=False action.
    r = client.post("/api/chat", json={"message": "buy 1 AAPL"})
    assert r.status_code == 200
    action = r.json()["actions"][0]
    assert action["ok"] is False
    assert "AAPL" in action["detail"]  # "No price available for AAPL"
    assert db.get_position("AAPL") is None


def test_failed_trade_persisted_in_actions(client):
    client.post("/api/chat", json={"message": "buy 1 AAPL"})  # unpriced -> fails
    assistant = db.recent_chat(20)[-1]
    assert assistant["role"] == "assistant"
    assert assistant["actions"][0]["ok"] is False


# ---- watchlist auto-execution ------------------------------------------

def test_watchlist_add_executes(client):
    r = client.post("/api/chat", json={"message": "add PYPL to my watchlist"})
    action = r.json()["actions"][0]
    assert action["kind"] == "watchlist"
    assert action["ok"] is True
    assert "PYPL" in db.watchlist_tickers()


def test_watchlist_add_unsupported_rejected_inline(client):
    # ZZZZ is not in the stub's supported set -> rejected, not added.
    r = client.post("/api/chat", json={"message": "add ZZZZ to my watchlist"})
    action = r.json()["actions"][0]
    assert action["ok"] is False
    assert "ZZZZ" in action["detail"]
    assert "ZZZZ" not in db.watchlist_tickers()


# ---- context cap (executor level) --------------------------------------

async def test_history_capped_at_20(client, monkeypatch):
    # Seed 25 prior messages, then capture what the LLM client receives.
    for i in range(25):
        db.append_chat("user", f"msg{i}")

    captured: dict = {}

    def fake_generate(ctx, history, user_message):
        captured["history"] = history
        from llm.schema import ChatResponse

        return ChatResponse(message="ok")

    monkeypatch.setattr(executor.client, "generate", fake_generate)

    await executor.run_chat(
        "newest",
        cache=client.cache,
        execute_trade=lambda *a, **k: None,
        trade_error=RuntimeError,
        is_supported=client.app.state.provider.is_supported,
        on_change=lambda: None,
    )

    assert len(captured["history"]) == MAX_HISTORY
    # most recent retained, oldest dropped
    assert captured["history"][-1].content == "msg24"
    assert captured["history"][0].content == "msg5"
