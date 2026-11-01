"""Finds agents from agents/*/manifest.json and knows how to call each one.

Local agents are loaded in-process: agents/<slug>/backend/<module>/ must expose `router`.
The platform wraps each in its own small FastAPI app and calls it over an in-memory
transport, so local and remote agents go through the same HTTP contract.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI
from pydantic import ValidationError
from rent_agent_interface import Manifest, NoticeBlock, RunRequest, RunResponse, load_manifest

log = logging.getLogger("rent_platform.registry")

SIGNATURE_HEADER = "X-Rent-Signature"
RUN_TIMEOUT_SECONDS = 60


@dataclass
class AgentEntry:
    manifest: Manifest
    folder: Path
    app: FastAPI | None = None  # local agents only
    router: APIRouter | None = None
    load_error: str | None = None
    has_extras: bool = False

    @property
    def slug(self) -> str:
        return self.manifest.slug

    @property
    def runnable(self) -> bool:
        if self.manifest.location == "remote":
            return True
        return self.app is not None

    @property
    def rentable(self) -> bool:
        return self.manifest.status == "available" and self.runnable


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class Registry:
    def __init__(self, agents_dir: Path, remote_secret: str = "") -> None:
        self.agents_dir = agents_dir
        self.remote_secret = remote_secret
        self.agents: dict[str, AgentEntry] = {}
        self.problems: list[str] = []
        self._load()

    def _load(self) -> None:
        for path in sorted(self.agents_dir.glob("*/manifest.json")):
            try:
                manifest = load_manifest(path)
            except (ValidationError, ValueError) as exc:
                # One broken manifest must never take the whole marketplace down.
                msg = f"{path.parent.name}: invalid manifest.json ({exc.__class__.__name__})"
                log.warning("%s: %s", msg, exc)
                self.problems.append(msg)
                continue
            entry = AgentEntry(manifest=manifest, folder=path.parent)
            if manifest.location == "local":
                self._load_local(entry)
            self.agents[manifest.slug] = entry

    def _load_local(self, entry: AgentEntry) -> None:
        backend = entry.folder / "backend"
        module = entry.manifest.python_module
        if not (backend / module / "__init__.py").is_file():
            return  # Listed in the marketplace, not runnable yet.
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        try:
            mod = importlib.import_module(module)
            router = mod.router
            if not isinstance(router, APIRouter):
                raise TypeError(f"{module}.router is not a FastAPI APIRouter")
        except Exception as exc:  # noqa: BLE001 - a broken agent is reported, not fatal
            entry.load_error = f"{exc.__class__.__name__}: {exc}"
            self.problems.append(f"{entry.slug}: could not load backend ({entry.load_error})")
            log.exception("could not load agent %s", entry.slug)
            return
        app = FastAPI(title=entry.manifest.name)
        app.include_router(router)
        extra = getattr(mod, "extra_router", None)
        if isinstance(extra, APIRouter):
            # Agent-specific endpoints (e.g. bank sign-in), reached only through the
            # platform's /api/agents/<slug>/x/... proxy, which checks login and rental.
            app.include_router(extra, prefix="/x")
            entry.has_extras = True
        entry.app = app
        entry.router = router

    def get(self, slug: str) -> AgentEntry | None:
        return self.agents.get(slug)

    def _client(self, entry: AgentEntry) -> httpx.AsyncClient:
        if entry.manifest.location == "remote":
            return httpx.AsyncClient(
                base_url=str(entry.manifest.base_url).rstrip("/"), timeout=RUN_TIMEOUT_SECONDS
            )
        assert entry.app is not None
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=entry.app),
            base_url="http://agent",
            timeout=RUN_TIMEOUT_SECONDS,
        )

    async def forward_extra(
        self,
        entry: AgentEntry,
        method: str,
        path: str,
        body: bytes,
        query: str,
        user_headers: dict[str, str],
        content_type: str | None,
    ) -> httpx.Response:
        """Send a browser request on to a local agent's extra endpoint as the given user."""
        headers = dict(user_headers)
        if content_type:
            headers["Content-Type"] = content_type
        url = f"/x/{path}" + (f"?{query}" if query else "")
        async with self._client(entry) as client:
            return await client.request(method, url, content=body, headers=headers)

    async def run(self, entry: AgentEntry, request: RunRequest) -> RunResponse:
        body = request.model_dump_json().encode()
        headers = {"Content-Type": "application/json"}
        if entry.manifest.location == "remote":
            if not self.remote_secret:
                return _failure("This helper isn't set up yet. Please try again later.")
            headers[SIGNATURE_HEADER] = sign(body, self.remote_secret)
        try:
            async with self._client(entry) as client:
                resp = await client.post("/run", content=body, headers=headers)
            resp.raise_for_status()
            return RunResponse.model_validate(resp.json())
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            log.warning("agent %s /run failed: %s", entry.slug, exc)
            return _failure("Something went wrong with this helper. Please try again in a minute.")


def _failure(text: str) -> RunResponse:
    return RunResponse(
        status="error", message=text, blocks=[NoticeBlock(level="danger", text=text)]
    )
