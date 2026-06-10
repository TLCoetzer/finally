"""Health check (PLAN.md §8) — used by Docker/deployment probes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from market.provider import MarketDataProvider
from api.deps import get_provider
from api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health(provider: MarketDataProvider = Depends(get_provider)) -> HealthResponse:
    return HealthResponse(status="ok", source=provider.source)
