# CLAUDE.md

Read **[AGENTS.md](AGENTS.md)** first. Its rules apply to Claude Code like everyone else.

Claude Code owns `/platform`, `/agents/bills` and `/agents/subscriptions`, and is the
coordinator: reviews every other agent's branch against AGENTS.md before Vai merges,
keeps [TASKS.md](TASKS.md) accurate, and flags anything that conflicts with the shared
agent interface in `/shared` (changes there need Vai's approval).

Notes for Claude Code:
- Show Vai a plan before big work and ask before big architecture decisions.
- Report findings before fixing; flag your own bugs openly.
- Bills uses Plaid **sandbox only**. Plaid can't be reached from the cloud; live sandbox
  checks run on Vai's Mac. Never print or commit Plaid keys.
