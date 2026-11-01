"""Optional helper: a router that already serves /manifest and /health from manifest.json.

router = make_agent_router(Path(__file__).parents[2] / "manifest.json")

@router.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse: ...
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from .conformance import load_manifest
from .models import Health, Manifest


def make_agent_router(manifest_path: Path | str) -> APIRouter:
    manifest = load_manifest(manifest_path)
    router = APIRouter()

    @router.get("/manifest", response_model=Manifest)
    def get_manifest() -> Manifest:
        return manifest

    @router.get("/health", response_model=Health)
    def health() -> Health:
        return Health(ok=True)

    return router
