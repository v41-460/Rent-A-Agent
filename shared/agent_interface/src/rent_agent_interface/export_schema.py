"""Write JSON Schemas for the interface: python -m rent_agent_interface.export_schema"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Manifest, RunRequest, RunResponse

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"


def schemas() -> dict[str, dict]:
    return {
        "manifest.schema.json": Manifest.model_json_schema(),
        "run-request.schema.json": RunRequest.model_json_schema(),
        "run-response.schema.json": RunResponse.model_json_schema(),
    }


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    SCHEMA_DIR.mkdir(exist_ok=True)
    for name, schema in schemas().items():
        (SCHEMA_DIR / name).write_text(render(schema), encoding="utf-8")
        print(f"wrote schema/{name}")
