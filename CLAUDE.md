# CLAUDE.md

The agent guide for this repository is **`AGENTS.md`** — read it first and follow
it. It is the tool-agnostic source of truth for running this campaign: the frozen
configuration and the rules that protect it, the Phase 0→5 run order with a
VERIFY step at each boundary, which messages are harmless, which failures to
escalate, and the return contract.

Operator-facing quickstart: `README_FIRST.md`. Full step-by-step:
`cluster/INSTRUCTIONS_FOR_PARTHA.md`.

The single most important rule: this analysis configuration is frozen and
audited. Execute it faithfully; never adjust a setting to turn a failure into a
success. Escalate to Salim (vikas.chand.physics@gmail.com) instead.
