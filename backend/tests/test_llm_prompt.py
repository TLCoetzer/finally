"""Prompt construction tests: shape, context rendering, 20-message cap."""
from __future__ import annotations

from llm.prompt import (
    MAX_HISTORY,
    SYSTEM_PROMPT,
    ChatTurn,
    PortfolioContext,
    PositionView,
    WatchlistView,
    build_messages,
    render_context,
)


def _ctx() -> PortfolioContext:
    return PortfolioContext(
        cash=5000.0,
        positions=[PositionView("AAPL", 10, 190.0, 200.0)],
        watchlist=[WatchlistView("GOOGL", 175.0, 1.5)],
    )


def test_context_totals_and_pnl():
    ctx = _ctx()
    assert ctx.positions_value == 2000.0
    assert ctx.total_value == 7000.0
    assert ctx.positions[0].unrealized_pnl == 100.0  # (200-190)*10


def test_render_context_includes_numbers():
    text = render_context(_ctx())
    assert "Cash: $5,000.00" in text
    assert "AAPL" in text
    assert "GOOGL" in text


def test_render_context_handles_missing_price():
    ctx = PortfolioContext(
        cash=100.0,
        positions=[PositionView("TSLA", 1, 250.0, None)],
        watchlist=[WatchlistView("NVDA", None, None)],
    )
    text = render_context(ctx)
    assert "n/a" in text  # price + pnl unknown
    assert ctx.total_value == 100.0  # missing price contributes 0


def test_build_messages_structure():
    msgs = build_messages(_ctx(), [], "What should I do?")
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SYSTEM_PROMPT
    # context system message sits right before the new user message
    assert msgs[-2]["role"] == "system"
    assert "CURRENT PORTFOLIO" in msgs[-2]["content"]
    assert msgs[-1] == {"role": "user", "content": "What should I do?"}


def test_history_included_in_order():
    history = [ChatTurn("user", "hi"), ChatTurn("assistant", "hello")]
    msgs = build_messages(_ctx(), history, "next")
    # system, user, assistant, context-system, user
    assert [m["content"] for m in msgs[1:3]] == ["hi", "hello"]


def test_history_capped_at_max():
    history = [ChatTurn("user", f"m{i}") for i in range(50)]
    msgs = build_messages(_ctx(), history, "new")
    conversation = [m for m in msgs if m["content"].startswith("m")]
    assert len(conversation) == MAX_HISTORY
    # keeps the most recent ones (m30..m49)
    assert conversation[0]["content"] == "m30"
    assert conversation[-1]["content"] == "m49"


def test_unknown_role_coerced_to_user():
    msgs = build_messages(_ctx(), [ChatTurn("system", "sneaky")], "x")
    sneaky = next(m for m in msgs if m["content"] == "sneaky")
    assert sneaky["role"] == "user"
