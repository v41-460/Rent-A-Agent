# Shared agent interface (v1)

**Changes here need Vai's approval.** Open a PR that touches only this folder and say why.

Every agent in the marketplace follows this contract. Full rules are in the root
[AGENTS.md](../../AGENTS.md#the-agent-interface).

- `src/rent_agent_interface/models.py`: the source of truth (Pydantic).
- `schema/*.json`: JSON Schemas generated from the models. Regenerate with
  `python -m rent_agent_interface.export_schema`; a test fails if they are stale.
- `typescript/agent-interface.ts`: the same types for the Next.js front end.
- `check_agent_app(...)`: the conformance check every agent's tests must call.
- `make_agent_router(...)`: optional helper that serves `/manifest` and `/health` for you.

```bash
cd shared/agent_interface
uv venv -p 3.12 .venv && . .venv/bin/activate
uv pip install -e '.[dev]'
pytest
python -m rent_agent_interface.validate_all ../..   # checks every agents/*/manifest.json
```
