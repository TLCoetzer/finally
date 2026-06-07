"""Database module stub — full implementation in a separate issue.

This stub keeps the backend importable and the app wirable while the
SQLite/schema layer is being built. Replace these functions with real
SQLite queries once the DB issue is closed."""


def init_if_needed() -> None:
    """Lazy schema + seed. No-op until the real DB layer is implemented."""


def watchlist_tickers() -> list[str]:
    """Return tickers currently on the watchlist."""
    return []


def position_tickers() -> list[str]:
    """Return tickers with an open position (quantity > 0)."""
    return []
