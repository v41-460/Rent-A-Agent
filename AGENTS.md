# AGENTS.md: rules for everyone building in this repo

Rent an Agent is a marketplace of specialized AI agents that non-technical people, and
older people new to AI, rent for everyday tasks. Four AI tools build here in parallel.
These rules keep us from breaking each other's work. Read them before every task.

## 1. Who owns what

| Folder | Owner | Branch prefix |
| --- | --- | --- |
| `/platform` | Claude Code | `claude/` |
| `/agents/bills` | Claude Code | `claude/` |
| `/agents/subscriptions` | Claude Code | `claude/` |
| `/agents/shopping` | Codex | `codex/` |
| `/agents/travel` | Codex | `codex/` |
| `/agents/scam-detector` | Codex | `codex/` |
| `/agents/paperwork` | Grok Build | `grok/` |
| `/agents/real-estate` | Hermes | `hermes/` |
| `/agents/home-services` | Hermes | `hermes/` |
| `/specs` | Grok bots (plans and specs) | `grok/` |
| `/shared` | **Vai approves every change** | any, PR must touch only `/shared` |
| `AGENTS.md`, `TASKS.md`, CI, root files | Claude Code (coordinator); `AGENTS.md` changes need Vai | `claude/` |

**Stay in your own folders.** If you need something changed elsewhere, don't change it:
add a row to `TASKS.md` with the owner set to whoever owns that folder and status `todo`.
The one exception: everyone may update **their own rows** in `TASKS.md`.

## 2. Branches, commits, pull requests

- Branch name: `<prefix>/<task-name>`, e.g. `codex/shopping-first-milestone`. Never push to `main`.
- Small commits, each with a clear message saying what and why.
- Open a pull request into `main`. Claude Code reviews every PR, then **Vai merges**.
- Before opening a PR: rebase on the latest `main`, run your tests, make sure CI is green.
- One task per PR. Put the `TASKS.md` ID in the PR title, e.g. `[T-05] Shopping: first milestone`.

## 3. Tests

- Every feature ships with tests. No tests, no merge.
- Python: `pytest`, in `agents/<slug>/backend/tests/` (or `platform/backend/tests/`).
- TypeScript: `vitest` for logic; `npm run typecheck` and `npm run build` must pass.
- Every agent's tests **must** call the shared conformance check (see "The agent interface").
- Tests never call real external services. Use fakes or recorded fixtures.
- Never skip, disable or delete someone else's test to make CI green.

## 4. Secrets and data

**This repo is public.** Anything committed is visible to the world, forever.

- No secrets in code, ever: no API keys, passwords, tokens, or connection strings.
- Secrets go in a `.env` file (never committed; `.env` is in `.gitignore`).
- Every folder that reads settings commits a `.env.example` with the variable **names**
  and fake placeholder values, so others know what to set.
- No real personal data in fixtures or tests: no real names, accounts, addresses, or bank
  exports. Make it up.
- CI runs a secret scanner (gitleaks) on every PR. A finding blocks the merge. If you leak
  a key, say so immediately in the PR so Vai can rotate it; deleting the commit is not enough.

## 5. Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2. Lint/format with `ruff`.
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind, one app in `/platform/web`.
- Agents that need their own Python dependencies list them in
  `agents/<slug>/backend/requirements.txt`. Pin versions. Flag new heavy dependencies
  in your PR description.
- Money, dates and any number shown to the user are computed in code, never by an LLM.
  LLMs may write wording, summaries and explanations. LLM keys come from `.env`.

## The agent interface

Every agent plugs into the marketplace the same way. The contract lives in
[`/shared/agent_interface`](shared/agent_interface/) (Python models, JSON Schemas,
TypeScript types). Version: **1**.

### `manifest.json` (in `agents/<slug>/`)

```json
{
  "interface_version": "1",
  "slug": "bills",
  "name": "Bills on Screen",
  "description": "See all your regular bills in one place, with amounts and due dates.",
  "long_description": "Connect your bank once ...",
  "icon": "🧾",
  "owner": "claude",
  "version": "0.1.0",
  "pricing": { "model": "monthly", "amount_cents": 499, "currency": "USD" },
  "status": "coming_soon",
  "location": "local",
  "base_url": null,
  "has_custom_page": true
}
```

| Field | Rules |
| --- | --- |
| `slug` | Lowercase, letters/digits/hyphens. **Must equal the folder name.** |
| `name` | 2 to 40 characters. Friendly, not technical. |
| `description` | One plain sentence, 10 to 140 characters. No jargon. |
| `icon` | An emoji, or a path to an `.svg`/`.png` inside the agent folder. |
| `owner` | `claude`, `codex`, `grok` or `hermes`. |
| `pricing` | `model` is `free`, `monthly` or `one_time`; `amount_cents` is 0 only for free. Payments are mocked for now. |
| `status` | `coming_soon` until the agent actually works; then `available`. |
| `location` | `local` (runs inside the platform) or `remote` (runs elsewhere; set `base_url`). |
| `has_custom_page` | `true` only if the agent ships its own page in `agents/<slug>/web/`. |

### Endpoints

Every agent serves:

- `GET /manifest`: returns the same data as `manifest.json`.
- `GET /health`: `{"ok": true, "detail": ""}`.
- `POST /run`: request `{"user": {"id", "display_name"}, "rental_id", "input": {...}}`,
  response `{"status": "ok" | "needs_input" | "error", "message", "blocks": [...]}`.

An agent may add its own extra endpoints (e.g. bills needs one for bank sign-in). They are
served under the same prefix and get the same rental check.

### Blocks

`/run` answers with a list of blocks. The platform draws them in one consistent,
large-text style, so agents don't write UI for normal screens:

`heading`, `text`, `notice` (info/success/warning/danger), `items` (a list of things with
title, subtitle, value), `table`, `link`, `actions` (buttons; pressing one calls `/run`
again with its `input`; set `confirm` for anything involving money), and `form`
(fields; submitting calls `/run` with the values as `input`).

Unknown block types are rejected. Need a new one? Ask in `TASKS.md`; it's a `/shared` change.

### Local agents (run inside the platform)

```
agents/<slug>/
  manifest.json
  README.md
  .env.example            (if the agent reads settings)
  backend/
    requirements.txt      (only extra deps beyond the platform's)
    <slug_with_underscores>_agent/__init__.py   -> exposes `router` (a FastAPI APIRouter)
    tests/
  web/                    (optional; only if has_custom_page is true)
```

- The Python package name is the slug with `-` replaced by `_`, plus `_agent`
  (`real-estate` -> `real_estate_agent`). This keeps agents from clashing.
- The platform mounts `router` at `/api/agents/<slug>` and checks the user has rented the
  agent before any request reaches it. Agents never see passwords or emails.
- Agents store their own data in their own place (own tables prefixed `<slug>_`, or own
  SQLite file under `AGENT_DATA_DIR`). Never read or write platform tables or another
  agent's data. Declared exception: `subscriptions` reads from `bills`.
- `make_agent_router(manifest_path)` from the shared package gives you `/manifest` and
  `/health` for free.

### Remote agents (e.g. Hermes on AWS)

Set `"location": "remote"` and `"base_url"`. The platform calls `{base_url}/run` etc. with
the same JSON, plus an `X-Rent-Signature` header (HMAC-SHA256 of the request body with a
shared secret from `.env`). Remote agents must reject requests without a valid signature.
The manifest still lives in this repo so the marketplace can list the agent.

### Conformance check (required in every agent's tests)

```python
from pathlib import Path
from rent_agent_interface import check_agent_app
from shopping_agent import router

AGENT_DIR = Path(__file__).resolve().parents[2]

def test_follows_shared_interface():
    result = check_agent_app(router, AGENT_DIR / "manifest.json", sample_input={})
    assert result.status in ("ok", "needs_input")
```

Remote agents run the same check against their own app.

## 6. Writing for our users

Our users are not technical, and many are older and new to AI. Every screen and message:

- Plain words. "Your bank", not "your financial institution". No acronyms without explaining.
- Big, readable text; one main action per screen; nothing that only works on hover.
- Say what will happen before it happens. Anything involving money asks for confirmation.
- Never pretend: if the agent isn't sure, say so. Never invent facts (phone numbers, prices,
  cancel steps) and present them as real.
- Errors say what went wrong and what to do next, without blaming the user.

## 7. Task board

[`TASKS.md`](TASKS.md) is the shared board. Update your own rows when you start, open a PR,
or get blocked. Claude Code keeps the rest accurate and reviews branches against these rules.
