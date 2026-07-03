# LESSONS — auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation — do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 — When a spec AC asks for an unconditional summary (e.g. 'how is my budget doing') alongside a conditional/filtered variant (e.g. 'what needs attention'), implement both as distinct handlers — don't assume the filtered one satisfies the unconditional one.
- signal: `ac_gap` · recurrence: 1 feature(s) · harmful: 0
- features: financial-assistant
- evidence: BUD-03 AC3
- last seen: 2026-07-03T01:52:13Z

### L-002 — A routing/threshold function being unit-tested in isolation does not mean it's reachable — verify the graph/router edge actually passes the field (e.g. confidence) the function needs, not just that the function behaves correctly when called directly.
- signal: `ac_gap` · recurrence: 1 feature(s) · harmful: 0
- features: financial-assistant
- evidence: ORCH-02 / src/financial_assistant/agents/graph.py:54-56
- last seen: 2026-07-03T01:52:13Z

### L-003 — When a spec AC requires citing a source (collection+doc) in a user-facing reply, test the final response text/metadata for that citation — testing only that retrieval happened is not sufficient evidence.
- signal: `ac_gap` · recurrence: 1 feature(s) · harmful: 0
- features: financial-assistant
- evidence: VEC-03 / src/financial_assistant/agents/specialists/atendimento.py:58-72
- last seen: 2026-07-03T01:52:13Z

### L-004 — A fallback/adapter function being fully unit-tested does not prove it's wired into the real startup path — grep for its call sites in application code (not just tests) before marking the AC done.
- signal: `ac_gap` · recurrence: 1 feature(s) · harmful: 0
- features: financial-assistant
- evidence: MCP-01 / src/financial_assistant/mcp/client.py
- last seen: 2026-07-03T01:52:13Z

### L-005 — When an edge case specifies preserving state across a redirect (e.g. return URL), assert the actual query param/header in the test, not just the redirect target path.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · harmful: 0
- features: financial-assistant
- evidence: AUTH-05 next= param
- last seen: 2026-07-03T01:52:13Z

## Quarantined (failed when applied — ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
