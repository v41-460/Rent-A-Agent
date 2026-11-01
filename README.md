# Rent an Agent

A marketplace of specialized AI agents that everyday people, including older people new
to AI, can rent for everyday tasks: seeing their bills, cancelling forgotten
subscriptions, spotting scams, handling paperwork and more.

**Building here?** Start with [AGENTS.md](AGENTS.md) (rules, folder ownership, the agent
interface) and [TASKS.md](TASKS.md) (who is doing what).

```
platform/            Marketplace: FastAPI backend + Next.js web app      (Claude Code)
agents/<slug>/       One folder per agent, each with a manifest.json      (see AGENTS.md)
shared/              Common code, incl. the agent interface (Vai approves changes)
specs/               Plans for each agent                                 (Grok bots)
```

## Agents

| Agent | Owner | Status |
| --- | --- | --- |
| Bills on Screen | Claude Code | planned |
| Subscription killer | Claude Code | planned |
| Shopping, Travel, Scam detector | Codex | planned |
| Paperwork | Grok Build | planned |
| Real estate, Home services | Hermes | planned |

## Checking the shared interface locally

```bash
cd shared/agent_interface
uv venv -p 3.12 .venv && . .venv/bin/activate
uv pip install -e '.[dev]'
pytest
python -m rent_agent_interface.validate_all ../..
```

How to run the marketplace: see [platform/README.md](platform/README.md).

This repository is public. Never commit secrets or real personal data (see AGENTS.md).
