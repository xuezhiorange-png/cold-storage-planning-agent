# ADR-034: Aily / 豆包工作伙伴 Five-Stage Conversation Preview

- Status: Accepted (V1.2 inbound preview)
- Date: 2026-08-29
- Context: V1.1 delivered zone-plan conversation preview over REST and MCP
  Streamable HTTP (`preview_zone_plan` only; ADR-033). Charles authorized
  extending the inbound connector so 豆包 can answer cooling, equipment,
  power, and investment questions in conversation without persistence or
  formula recut.

## Decision

### 1. Second inbound transport, not a second kernel

Expose additional REST (`concept-preview`) and MCP tools that call the
**existing** five production adapters in memory. Do not fork calculators.
Do not introduce microservices.

### 2. No persist, no recut, not Transaction B

Preview responses set `persisted: false`. Adapters run from assembler
snapshots only. Do **not** feed zone-planner area into cooling load
(`FORMULA_RECUT_AUTHORIZED=NO`, `envelope_from_zone_area: false`). Do not
open Transaction B or approved project versions.

### 3. Operator KEY and calculator identities unchanged

`OperatorProcessInputV1@1.1.0` five KEY stay frozen. Calculator identities
stay:

```text
cold_room_zone_plan@1.0.0
cooling_load@1.0.0
equipment@1.0.0
installed_power@1.0.0
investment_estimate@1.0.0
```

### 4. Conversation order

Missing KEY fail closed with `ask_operator`. When five KEY are present,
**first** reply path remains `preview_zone_plan`. Additional stage tools are
opt-in per user question.

### 5. Cooling honesty

Cooling preview continues the workbench **demo envelope catalog**. Skill,
MCP tool descriptions, and cooling table captions must state that envelope
area is demo-sourced, not auto-imported from zone planning.

### 6. V1.1 artifacts remain frozen

`docs/contracts/aily/v1.1/**`, ADR-031, ADR-032, ADR-033 stay as-is.
V1.2 adds `docs/contracts/aily/v1.2/**` and this ADR supersedes ADR-033
**scope** for five-stage preview only.

### 7. Outbound live session stays off

`AILY_OUTBOUND_LIVE_SESSION=NO` (TD-024).

## Consequences

- 豆包 can list five MCP tools; zone tool remains first.
- Application layer stays MCP-SDK-free; transport stays Streamable HTTP.
- Reports and Vue still must not recompute formulas.

## Alternatives rejected

1. Chain zone output into cooling automatically — rejected (`FORMULA_RECUT_AUTHORIZED=NO`).
2. Require Transaction B persistence before chat tables — too heavy for preview.
3. Extend `/api/v1/agent/**` — rejected by ADR-027 / ADR-031.
