# Platform

Owner: **Claude Code**. The marketplace: accounts, the list of helpers, renting with
mock payments, and running a rented helper. See [AGENTS.md](../AGENTS.md) for the rules
and the agent interface.

```
backend/   FastAPI. Accounts, marketplace API, rentals, mock payments, agent registry.
web/       Next.js + TypeScript + Tailwind. The one web app for every agent.
```

## Running it

Backend (Python 3.12):

```bash
cd platform/backend
uv venv -p 3.12 .venv && . .venv/bin/activate     # or: python3.12 -m venv .venv
uv pip install -r requirements-dev.txt
uvicorn rent_platform.main:create_app --factory --reload --port 8000
```

Web (Node 22):

```bash
cd platform/web
npm install
npm run dev            # http://localhost:3000, forwards /api/* to the backend
```

The marketplace lists every `agents/*/manifest.json`. To try renting and running before
any real agent is ready, point the backend at the test helpers:

```bash
AGENTS_DIR=$PWD/tests/fixtures/agents uvicorn rent_platform.main:create_app --factory --port 8000
```

Settings (all optional for local use) are in the root [.env.example](../.env.example).

## Tests

```bash
cd platform/backend && pytest && ruff check . && ruff format --check .
cd platform/web && npm run typecheck && npm test && npm run build
```

## API

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/api/auth/signup` | Create account, log in (httpOnly cookie) |
| POST | `/api/auth/login` / `/api/auth/logout` | Log in / out |
| GET | `/api/auth/me` | Who is logged in (or `null`) |
| GET | `/api/agents` | All helpers, rentable first |
| GET | `/api/agents/{slug}` | One helper, with long description |
| POST | `/api/agents/{slug}/rent` | Rent; paid helpers record a **mock** payment |
| GET | `/api/rentals` | My helpers |
| POST | `/api/agents/{slug}/run` | Run a rented helper: `{"input": {...}}` -> blocks |
| GET | `/api/health` | Status, plus any agents that failed to load |

Payments are mocked: they always succeed and nothing is charged. Each one is still saved
as a payment row, so a real provider can replace the mock later.
