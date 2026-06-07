import os

from .cache import PriceCache
from .provider import MarketDataProvider
from .massive import MassiveProvider
from .simulator import SimulatorProvider


def create_provider(cache: PriceCache) -> MarketDataProvider:
    """Select provider from the environment (PLAN.md §5).

    MASSIVE_API_KEY set and non-empty  → MassiveProvider (live data)
    otherwise                          → SimulatorProvider (default)
    """
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    poll = float(os.environ.get("MASSIVE_POLL_SECONDS", "15"))
    if key:
        return MassiveProvider(cache, api_key=key, poll_seconds=poll)
    return SimulatorProvider(cache)
