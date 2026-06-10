"""Static-file serving for the Next.js export (PLAN.md §3, §11).

Mounted LAST so /api/* and /api/stream/* routers always take precedence; only
unmatched paths fall through to the SPA. Guarded: if the export dir is absent
(local backend-only runs, unit tests) this is a no-op, so nothing breaks when
the frontend hasn't been built.

Path is the STATIC_DIR env var, default backend/static (devops copies the
Next.js export there in the Docker build). html=True serves index.html for
directory paths so client-side routes resolve."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def _static_dir() -> Path:
    override = os.environ.get("STATIC_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "static"


def mount_static(app: FastAPI) -> bool:
    """Mount the frontend export at / if present. Returns True if mounted."""
    directory = _static_dir()
    if not directory.is_dir():
        return False
    app.mount("/", StaticFiles(directory=directory, html=True), name="static")
    return True
