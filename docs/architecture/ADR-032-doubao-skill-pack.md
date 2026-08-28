# ADR-032: Static 豆包工作伙伴 Skill Pack (V1.1 P2)

- Status: Accepted (V1.1 P2 static skill pack)
- Date: 2026-08-28
- Context: V1.1 P0/P1 (`#237`) delivered the inbound
  `POST /api/v1/aily/v1/zone-plan` connector on `main`. Charles authorized
  parallel follow-ups. Operators need a **paste-ready** conversation policy
  for Feishu 豆包工作伙伴 without turning on outbound live session control
  from this repository.

## Context

V0.7 P6 froze Aily boundary paper with `AILY_LIVE_IMPLEMENTATION=NO`.
ADR-031 added the inbound zone-plan preview with `AILY_OUTBOUND_LIVE_SESSION=NO`.

Operators configuring 豆包工作伙伴 need explicit instructions:

- 吨 always means per day; 豆包 owns NLP;
- collect five operator KEY with Chinese `ask_operator` labels;
- convert 吨/天 → `daily_inbound_mass_kg` before POST;
- render `markdown_table` from the connector;
- never compute engineering values in the skill prompt.

This is analogous to V0.7 P6 static contracts — documentation and tests,
not runtime Feishu API calls from this app.

## Decision

### 1. Ship a static skill pack under `docs/contracts/aily/v1.1/`

- `doubao-skill.v1.md` — paste-ready Chinese skill for operators
- `doubao-skill.v1.json` — structured companion for architecture tests

### 2. Static skill pack ≠ live outbound session

`AILY_OUTBOUND_LIVE_SESSION=NO` remains frozen. P2 does **not**:

- create Feishu skills or sessions from this application;
- add outbound HTTP clients to Aily/Feishu APIs;
- register MCP connectors at runtime.

Operators manually paste the skill into 豆包工作伙伴 and wire the inbound
OpenAPI connector separately (P0/P1 artifact).

### 3. Conversation policy boundaries

| Topic | 豆包 (skill) | This system |
| --- | --- | --- |
| Natural language | Understand, ask, convert 吨/天 | Does not parse chat |
| Five KEY | Collect and POST JSON | Validate; fail closed |
| Zone table | Display `markdown_table` | `cold_room_zone_plan@1.0.0` |
| Review / approve | Must not call | Not exposed to 豆包 |

`DO_NOT_BUMP_ZONE_PLAN_VERSION=YES`. `OperatorProcessInputV1@1.1.0` unchanged.

### 4. P2 scope is docs + architecture tests only

No `backend/src/**` changes. P3 (auth) and P4 (runbook/OpenAPI examples) are
parallel sibling packages.

## Consequences

- Operators can paste one markdown file into 豆包工作伙伴 today.
- Architecture tests guard five KEY names, per-day tonne semantics, endpoint
  path, governance flags, and absence of invented engineering formulas in skill
  text.
- Live Feishu tenant skill wiring remains a later package when Charles
  authorizes `AILY_OUTBOUND_LIVE_SESSION=YES`.

## Alternatives rejected

1. **Auto-create Feishu skill from this app** — rejected; outbound live
   session is explicitly `NO` for V1.1 P2.
2. **Embed engineering formulas in the skill** — rejected
   (`AGENT_TO_ENGINEERING_VALUE=NO`).
3. **Let 豆包 call `/api/v1/agent/**` or `mark_reviewed`** — rejected by
   ADR-027 and V1.1 non-goals.
