"""Unit tests for market.factory — provider selection from the environment."""
import pytest

from market.cache import PriceCache
from market.factory import create_provider, _poll_seconds, DEFAULT_POLL_SECONDS
from market.simulator import SimulatorProvider
from market.massive import MassiveProvider


# ---- provider selection --------------------------------------------------

def test_no_key_returns_simulator(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    assert isinstance(create_provider(PriceCache()), SimulatorProvider)


def test_blank_key_returns_simulator(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "   ")
    assert isinstance(create_provider(PriceCache()), SimulatorProvider)


@pytest.mark.asyncio
async def test_key_returns_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "secret")
    provider = create_provider(PriceCache())
    assert isinstance(provider, MassiveProvider)
    await provider.stop()  # close the httpx client


@pytest.mark.asyncio
async def test_massive_receives_poll_seconds(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "secret")
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", "3")
    provider = create_provider(PriceCache())
    assert provider._poll == pytest.approx(3.0)
    await provider.stop()


# ---- poll-seconds parsing ------------------------------------------------

def test_poll_seconds_default(monkeypatch):
    monkeypatch.delenv("MASSIVE_POLL_SECONDS", raising=False)
    assert _poll_seconds() == DEFAULT_POLL_SECONDS


def test_poll_seconds_custom(monkeypatch):
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", "2.5")
    assert _poll_seconds() == pytest.approx(2.5)


def test_poll_seconds_malformed_falls_back(monkeypatch):
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", "fast")
    assert _poll_seconds() == DEFAULT_POLL_SECONDS
