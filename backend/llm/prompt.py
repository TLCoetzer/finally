"""Prompt construction for the chat LLM (PLAN.md §9).

Framework- and DB-free: the route assembles a `PortfolioContext` and a list of
prior `ChatTurn`s from the DB/cache, then this module renders the LiteLLM
`messages` list (system + context + history + new user message). Keeping the
inputs as plain dataclasses lets us unit-test prompt shape without a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Cap on prior conversation turns fed back to the model (Decision #8 / §9).
MAX_HISTORY = 20

SYSTEM_PROMPT = (
    "You are FinAlly, an AI trading assistant embedded in a simulated trading "
    "workstation. The portfolio uses virtual cash; trades execute instantly at "
    "the current market price with no fees and no confirmation.\n\n"
    "Your job:\n"
    "- Analyze portfolio composition, risk concentration, and P&L.\n"
    "- Suggest trades with concise, data-driven reasoning.\n"
    "- Execute trades when the user asks or agrees, via the `trades` field.\n"
    "- Manage the watchlist proactively via `watchlist_changes`.\n"
    "- Be concise and specific; reference real numbers from the context.\n\n"
    "Trades are validated like manual orders: buys need sufficient cash, sells "
    "need sufficient shares, and watchlist adds must be a supported ticker. If "
    "an action fails it will be reported back; acknowledge failures honestly.\n\n"
    "Always respond with JSON matching the required schema: a `message` string, "
    "plus optional `trades` and `watchlist_changes` arrays. Use empty arrays "
    "when no action is needed. `side` is 'buy' or 'sell'; watchlist `action` is "
    "'add' or 'remove'. Never invent positions or prices not in the context."
)


@dataclass(frozen=True)
class PositionView:
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None  # None when no live quote yet

    @property
    def market_value(self) -> float | None:
        if self.current_price is None:
            return None
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float | None:
        if self.current_price is None:
            return None
        return (self.current_price - self.avg_cost) * self.quantity


@dataclass(frozen=True)
class WatchlistView:
    ticker: str
    price: float | None
    change_pct: float | None


@dataclass(frozen=True)
class PortfolioContext:
    cash: float
    positions: list[PositionView] = field(default_factory=list)
    watchlist: list[WatchlistView] = field(default_factory=list)

    @property
    def positions_value(self) -> float:
        return sum(p.market_value or 0.0 for p in self.positions)

    @property
    def total_value(self) -> float:
        return self.cash + self.positions_value


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" or "assistant"
    content: str


def _fmt_money(v: float | None) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.2f}%"


def render_context(ctx: PortfolioContext) -> str:
    """Render the live portfolio context as a compact text block."""
    lines = [
        "CURRENT PORTFOLIO",
        f"Cash: {_fmt_money(ctx.cash)}",
        f"Positions value: {_fmt_money(ctx.positions_value)}",
        f"Total value: {_fmt_money(ctx.total_value)}",
        "",
        "POSITIONS (ticker, qty, avg_cost, price, unrealized P&L):",
    ]
    if ctx.positions:
        for p in ctx.positions:
            lines.append(
                f"  {p.ticker}: {p.quantity:g} @ {_fmt_money(p.avg_cost)} | "
                f"price {_fmt_money(p.current_price)} | "
                f"P&L {_fmt_money(p.unrealized_pnl)}"
            )
    else:
        lines.append("  (none)")

    lines += ["", "WATCHLIST (ticker, price, change% vs session open):"]
    if ctx.watchlist:
        for w in ctx.watchlist:
            lines.append(
                f"  {w.ticker}: {_fmt_money(w.price)} ({_fmt_pct(w.change_pct)})"
            )
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def build_messages(
    ctx: PortfolioContext,
    history: list[ChatTurn],
    user_message: str,
) -> list[dict[str, str]]:
    """Assemble the LiteLLM `messages` list.

    `history` is oldest-first prior turns; only the last MAX_HISTORY are kept.
    The live portfolio context is injected as a system message right before the
    new user message so it reflects the latest prices regardless of history."""
    recent = history[-MAX_HISTORY:] if len(history) > MAX_HISTORY else history
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in recent:
        role = turn.role if turn.role in ("user", "assistant") else "user"
        messages.append({"role": role, "content": turn.content})
    messages.append({"role": "system", "content": render_context(ctx)})
    messages.append({"role": "user", "content": user_message})
    return messages
