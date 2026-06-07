from __future__ import annotations
from fastapi import Request

from market.provider import MarketDataProvider
from market.cache import PriceCache


def get_provider(request: Request) -> MarketDataProvider:
    return request.app.state.provider


def get_cache(request: Request) -> PriceCache:
    return request.app.state.cache
