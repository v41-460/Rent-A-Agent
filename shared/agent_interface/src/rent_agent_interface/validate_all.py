"""Validate every agents/*/manifest.json. Used by CI: python -m rent_agent_interface.validate_all"""

from __future__ import annotations

import sys
from pathlib import Path

from .conformance import load_manifest


def main(repo_root: Path) -> int:
    failures = 0
    found = sorted((repo_root / "agents").glob("*/manifest.json"))
    for path in found:
        try:
            m = load_manifest(path)
            print(f"ok   {m.slug}")
        except Exception as exc:  # noqa: BLE001 - report every failure, then exit non-zero
            failures += 1
            print(f"FAIL {path.relative_to(repo_root)}: {exc}")
    print(f"{len(found)} manifest(s), {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    raise SystemExit(main(root))
