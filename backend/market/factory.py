from __future__ import annotations
import logging
import os

from .cache import PriceCache
from .provider import MarketDataProvider
from .massive import MassiveProvider
from .simulator import SimulatorProvider

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 15.0


def _poll_seconds() -> float:
    """Massive poll interval from env, tolerating a malformed value."""
    raw = os.environ.get("MASSIVE_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid MASSIVE_POLL_SECONDS=%r; using default %.0fs", raw, DEFAULT_POLL_SECONDS
        )
        return DEFAULT_POLL_SECONDS


def create_provider(cache: PriceCache) -> MarketDataProvider:
    """Select provider from the environment (PLAN.md §5).

    MASSIVE_API_KEY set and non-empty  → MassiveProvider (live data)
    otherwise                          → SimulatorProvider (default)
    """
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if key:
        return MassiveProvider(cache, api_key=key, poll_seconds=_poll_seconds())
    return SimulatorProvider(cache)
