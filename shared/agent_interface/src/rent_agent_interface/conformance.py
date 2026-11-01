"""Checks every agent's tests should run, so a broken agent never reaches the marketplace.

Usage in an agent's tests::

    from rent_agent_interface import check_agent_app
    from my_agent import router

    def test_follows_shared_interface():
        check_agent_app(router, AGENT_DIR / "manifest.json", sample_input={})
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Health, Manifest, RunResponse


def load_manifest(path: Path | str) -> Manifest:
    """Read and validate a manifest.json. Raises pydantic.ValidationError if invalid."""
    path = Path(path)
    manifest = Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    folder = path.parent.name
    if folder != manifest.slug:
        raise ValueError(f"manifest slug '{manifest.slug}' must match its folder name '{folder}'")
    if not _is_emoji_like(manifest.icon):
        icon_path = path.parent / manifest.icon
        if icon_path.suffix not in (".svg", ".png") or not icon_path.is_file():
            raise ValueError(f"icon '{manifest.icon}' is not an emoji or an .svg/.png file")
    return manifest


def _is_emoji_like(icon: str) -> bool:
    return len(icon) <= 8 and not any(c in icon for c in "/.")


def check_agent_app(
    router_or_app: Any,
    manifest_path: Path | str,
    sample_input: dict[str, Any] | None = None,
) -> RunResponse:
    """Mount the agent on a throwaway app and call /manifest, /health and /run.

    Returns the parsed /run response so the agent's own test can assert on it.
    """
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    manifest = load_manifest(manifest_path)
    if isinstance(router_or_app, APIRouter):
        app = FastAPI()
        app.include_router(router_or_app)
    else:
        app = router_or_app

    with TestClient(app) as client:
        got = client.get("/manifest")
        assert got.status_code == 200, f"GET /manifest returned {got.status_code}"
        served = Manifest.model_validate(got.json())
        assert served == manifest, "GET /manifest must return the same data as manifest.json"

        health = client.get("/health")
        assert health.status_code == 200, f"GET /health returned {health.status_code}"
        Health.model_validate(health.json())

        run = client.post(
            "/run",
            json={
                "user": {"id": "conformance-user", "display_name": "Test User"},
                "rental_id": "conformance-rental",
                "input": sample_input or {},
            },
        )
        assert run.status_code == 200, f"POST /run returned {run.status_code}: {run.text}"
        return RunResponse.model_validate(run.json())
