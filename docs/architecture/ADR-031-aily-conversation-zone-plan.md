# ADR-031: Aily / 豆包工作伙伴 Conversation Zone-Plan Connector

- Status: Accepted (V1.1 inbound preview)
- Date: 2026-08-28
- Context: V0.7 P6 froze an Aily boundary (`AILY_LIVE_IMPLEMENTATION=NO`)
  without HTTP. Charles authorized implementing the Feishu interface.
  Product name in Feishu is 豆包工作伙伴. Spoken「吨」always means per day;
  utterances like「要建一个多少吨的加工厂」are examples for 豆包. 豆包
  understands language; this system runs the existing zone kernel and
  returns a table. It does not parse chat.

## Decision

### 1. Inbound connector is a new namespace

Expose `POST /api/v1/aily/v1/zone-plan`. Do not extend `/api/v1/agent/**`.

### 2. 豆包 owns semantics; this system owns numbers

Operator KEY stay the V0.9 five leaves. Missing KEY fail closed.
Engineering values come only from `cold_room_zone_plan@1.0.0`.
Do not bump that `VERSION`.

### 3. Preview is not persistence and not review

The connector returns a table for chat. It does not create an approved
project version, does not expose `mark_reviewed` / `approve`, and does
not claim production RBAC.

### 4. Outbound live session stays off

`AILY_OUTBOUND_LIVE_SESSION=NO`. Creating Feishu skills/sessions from
this repository waits for a later package.

### 5. V0.7 P6 artifacts remain

`docs/contracts/aily/v0.7/**` stay the frozen four-tool write-proposal
family. V1.1 adds a conversation preview family under
`docs/contracts/aily/v1.1/**`.

## Consequences

- 豆包 can import the v1.1 OpenAPI as a custom connector operation.
- Cooling/equipment/power/investment formula recut remains out of scope.
- Reports and Vue still must not recompute formulas.

## Alternatives rejected

1. Reuse `/api/v1/agent/**` — rejected by ADR-027.
2. Let 豆包 calculate area in the prompt — forbidden
   (`AGENT_TO_ENGINEERING_VALUE=NO`).
3. Require full five-stage persistence before answering chat — too heavy
   for the first conversation reply Charles described.
