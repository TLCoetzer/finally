from fastapi import FastAPI

import db


def tracked_tickers() -> set[str]:
    """watchlist ∪ open positions — the universe the cache must cover.

    Called on startup and after every trade / watchlist mutation so the cache
    always streams live P&L for held-but-unwatched tickers (Decision #3)."""
    return {t.upper() for t in db.watchlist_tickers()} \
         | {t.upper() for t in db.position_tickers()}


def recompute_tracked(app: FastAPI) -> None:
    """Re-derive the tracked set from the DB and push it to the provider.
    Idempotent — the DB is authoritative, so this can never desync."""
    app.state.provider.set_tracked(tracked_tickers())
