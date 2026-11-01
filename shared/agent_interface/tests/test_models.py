import json
from pathlib import Path

import pytest
from fastapi import APIRouter
from pydantic import ValidationError

from rent_agent_interface import (
    Manifest,
    RunRequest,
    RunResponse,
    check_agent_app,
    load_manifest,
    make_agent_router,
)
from rent_agent_interface.export_schema import SCHEMA_DIR, render, schemas

GOOD = {
    "slug": "demo",
    "name": "Demo Agent",
    "description": "Says hello so you can see how agents work.",
    "icon": "👋",
    "owner": "claude",
    "pricing": {"model": "free", "amount_cents": 0},
}


def write_manifest(tmp_path: Path, data: dict, folder: str = "demo") -> Path:
    d = tmp_path / folder
    d.mkdir()
    p = d / "manifest.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_good_manifest_loads(tmp_path):
    m = load_manifest(write_manifest(tmp_path, GOOD))
    assert m.slug == "demo"
    assert m.status == "coming_soon"
    assert m.python_module == "demo_agent"


def test_hyphenated_slug_module_name():
    m = Manifest.model_validate({**GOOD, "slug": "real-estate"})
    assert m.python_module == "real_estate_agent"


@pytest.mark.parametrize(
    "change",
    [
        {"slug": "Bad Slug"},
        {"owner": "someone-else"},
        {"pricing": {"model": "free", "amount_cents": 500}},
        {"pricing": {"model": "monthly", "amount_cents": 0}},
        {"location": "remote"},
        {"base_url": "https://example.com"},
        {"unknown_field": 1},
        {"description": "short"},
    ],
)
def test_bad_manifests_rejected(change):
    with pytest.raises(ValidationError):
        Manifest.model_validate({**GOOD, **change})


def test_slug_must_match_folder(tmp_path):
    with pytest.raises(ValueError, match="folder"):
        load_manifest(write_manifest(tmp_path, GOOD, folder="other"))


def test_icon_file_must_exist(tmp_path):
    with pytest.raises(ValueError, match="icon"):
        load_manifest(write_manifest(tmp_path, {**GOOD, "icon": "icon.svg"}))


def test_icon_file_ok(tmp_path):
    p = write_manifest(tmp_path, {**GOOD, "icon": "icon.svg"})
    (p.parent / "icon.svg").write_text("<svg/>")
    assert load_manifest(p).icon == "icon.svg"


def test_blocks_round_trip():
    resp = RunResponse.model_validate(
        {
            "status": "ok",
            "blocks": [
                {"type": "heading", "text": "Your bills"},
                {"type": "items", "items": [{"title": "Netflix", "value": "$15.49"}]},
                {"type": "table", "columns": ["a", "b"], "rows": [["1", "2"]]},
                {"type": "actions", "actions": [{"label": "Refresh", "input": {"x": 1}}]},
                {"type": "form", "fields": [{"name": "zip", "label": "ZIP code"}]},
            ],
        }
    )
    assert resp.blocks[1].items[0].title == "Netflix"


def test_unknown_block_rejected():
    with pytest.raises(ValidationError):
        RunResponse.model_validate({"status": "ok", "blocks": [{"type": "video"}]})


def test_table_row_width_checked():
    with pytest.raises(ValidationError):
        RunResponse.model_validate(
            {"status": "ok", "blocks": [{"type": "table", "columns": ["a"], "rows": [["1", "2"]]}]}
        )


def test_run_request_needs_user():
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"rental_id": "r1"})


def test_conformance_passes_for_minimal_agent(tmp_path):
    path = write_manifest(tmp_path, GOOD)
    router = make_agent_router(path)

    @router.post("/run", response_model=RunResponse)
    def run(req: RunRequest) -> RunResponse:
        text = f"Hi {req.user.display_name}"
        return RunResponse(status="ok", blocks=[{"type": "text", "text": text}])

    out = check_agent_app(router, path)
    assert out.blocks[0].text == "Hi Test User"


def test_conformance_catches_missing_run(tmp_path):
    path = write_manifest(tmp_path, GOOD)
    with pytest.raises(AssertionError, match="/run"):
        check_agent_app(make_agent_router(path), path)


def test_conformance_catches_manifest_mismatch(tmp_path):
    path = write_manifest(tmp_path, GOOD)
    router = APIRouter()

    @router.get("/manifest")
    def m():
        return {**GOOD, "name": "Different"}

    with pytest.raises(AssertionError, match="manifest"):
        check_agent_app(router, path)


def test_committed_json_schemas_are_current():
    """If this fails, run: python -m rent_agent_interface.export_schema"""
    for name, schema in schemas().items():
        assert (SCHEMA_DIR / name).read_text(encoding="utf-8") == render(schema), name
