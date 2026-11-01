# agents/bills: Bills on Screen

Owner: **Claude Code**. Connect a bank (Plaid **sandbox only**) and see your regular bills:
name, amount, next due date and how often. It only looks; it never moves money.

Ported from the Bills Agent proof of concept. The detection code (`backend/bills_agent/detection/`)
and its fixtures are unchanged from that POC; what's new is multi-user storage, a practice
bank (made-up household, no bank needed), and the platform wiring.

```
manifest.json
backend/bills_agent/        router (/manifest, /health, /run) + extra_router (bank sign-in, sync, bills)
backend/bills_agent/detection/   deterministic bill detection, no LLM
backend/bills_fixtures/     made-up households used by tests and the practice bank
backend/scripts/sandbox_smoke.py live Plaid sandbox check from the command line
web/                        the Bills page (shown at /agents/bills/use)
```

## Setup

```bash
cd agents/bills/backend
cp .env.example .env        # Plaid SANDBOX keys + an encryption key. Never commit .env.
```

Without Plaid keys, Bills still works with the practice bank.

## Tests

```bash
cd agents/bills/backend
uv venv -p 3.12 .venv && . .venv/bin/activate && uv pip install -r requirements-dev.txt
pytest                      # ~90 tests, no network
ruff check . && ruff format --check .
BILLS_NOISE_SEEDS=1000 pytest tests/test_noise_robustness.py   # long version
python -m scripts.sandbox_smoke   # live Plaid sandbox (needs keys and network access to Plaid)
```

## Rules

- `PLAID_ENV` must be `sandbox`; anything else is refused at startup. Don't relax this
  without Vai's explicit approval.
- Plaid access tokens are encrypted at rest and never sent to the browser or logged.
- Every row is tied to a user; one person can never see another's bank or bills.
- Every detection and every user choice is written to `bills_audit_events`.
