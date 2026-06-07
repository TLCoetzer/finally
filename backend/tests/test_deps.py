"""Unit tests for api.deps — request-scoped accessors."""
from types import SimpleNamespace

from api.deps import get_provider, get_cache


def _request(cache, provider):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(cache=cache, provider=provider))
    )


def test_get_cache_returns_app_state_cache():
    cache, provider = object(), object()
    assert get_cache(_request(cache, provider)) is cache


def test_get_provider_returns_app_state_provider():
    cache, provider = object(), object()
    assert get_provider(_request(cache, provider)) is provider
