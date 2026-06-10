"""Tests for guarded static-file mounting (PLAN.md §3, §11)."""
from __future__ import annotations

from fastapi import FastAPI

from api.static import mount_static


def test_mount_static_noop_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "missing"))
    app = FastAPI()
    assert mount_static(app) is False


def test_mount_static_serves_index(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>FinAlly</title>")
    monkeypatch.setenv("STATIC_DIR", str(static))

    app = FastAPI()
    assert mount_static(app) is True

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "FinAlly" in r.text
