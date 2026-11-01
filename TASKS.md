# TASKS.md: shared task board

Statuses: `todo` · `in progress` · `in review` (PR open) · `done` (merged) · `blocked`.
Update your own rows when you start, open a PR, finish, or get blocked. Need something
from another owner's folder? Add a row with their name as owner. Rules: [AGENTS.md](AGENTS.md).

Every agent milestone also requires: a valid `manifest.json`, the shared conformance test
passing, its own tests passing in CI, no secrets, and changes only inside its own folder.

| ID | Task | Owner | Status | Branch / PR | Acceptance criteria |
| --- | --- | --- | --- | --- | --- |
| T-00 | Repo setup: folders, AGENTS.md, TASKS.md, shared interface v1, CI | Claude Code | done | main | Folders exist; rules and interface documented; CI runs interface tests, manifest check and secret scan. |
| T-01 | Platform: sign-up and login | Claude Code | todo | `claude/platform-marketplace` | Email + password sign-up, log in, log out; passwords hashed; session cookie is httpOnly; wrong password gives a plain message; tests. |
| T-02 | Platform: marketplace page | Claude Code | todo | `claude/platform-marketplace` | Lists every agent from `agents/*/manifest.json` with icon, name, description, price; "Coming soon" agents shown but not rentable; works on a phone; tests. |
| T-03 | Platform: agent detail page + Rent (mock payment) | Claude Code | todo | `claude/platform-marketplace` | Detail page shows long description and price; "Rent" runs a mock checkout clearly marked "test mode, no real charge"; rental recorded; only renters can run the agent; blocks from `/run` are drawn; tests. |
| T-04 | Bills: "Bills on screen" (Plaid sandbox) | Claude Code | todo | `claude/bills-on-screen` | Rented user connects a Plaid **sandbox** bank and sees recurring bills with name, amount, next due date and frequency; production Plaid impossible by config; tests run without Plaid (fake bank); verified live on Vai's Mac. |
| T-05 | Subscriptions: subscription killer | Claude Code | blocked (needs T-04) | `claude/subscription-killer` | Uses bills' data; flags subscriptions; shows monthly and yearly cost each and in total; cancel steps for each (curated for common services, clearly marked general advice otherwise); tests. |
| T-06 | Shopping: first milestone | Codex | todo | `codex/shopping-first-milestone` | Valid manifest; `/run` returns a working first result (e.g. ask what to buy, return blocks); conformance test passes. Feature scope: see `/specs` when available. |
| T-07 | Travel: first milestone | Codex | todo | `codex/travel-first-milestone` | Valid manifest; `/run` returns a working first result; conformance test passes. Feature scope: see `/specs`. |
| T-08 | Scam detector: first milestone | Codex | todo | `codex/scam-detector-first-milestone` | Valid manifest; `/run` takes a pasted message and returns a plain-language risk notice; conformance test passes; tests include obvious-scam and obvious-safe examples. |
| T-09 | Paperwork: first milestone | Grok Build | todo | `grok/paperwork-first-milestone` | Valid manifest; `/run` returns a working first result; conformance test passes. Feature scope: see `/specs`. |
| T-10 | Real estate: first milestone | Hermes | todo | `hermes/real-estate-first-milestone` | Valid manifest (local, or remote with `base_url`); `/run` returns a working first result; conformance test passes; if remote, rejects unsigned requests. |
| T-11 | Home services: first milestone | Hermes | todo | `hermes/home-services-first-milestone` | Valid manifest (local, or remote with `base_url`); `/run` returns a working first result; conformance test passes; if remote, rejects unsigned requests. |
| T-12 | Specs: plan for each agent | Grok bots | todo | `grok/specs-*` | One file per agent in `/specs` with goal, user, first features, and what "done" means. |
