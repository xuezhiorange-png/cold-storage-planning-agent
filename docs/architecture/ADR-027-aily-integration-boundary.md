# ADR-027: Feishu Aily Integration Boundary

- Status: Accepted (frozen 2026-08-26)
- Context: V0.7 P0 recorded `V07-GAP-008` — no Feishu Aily integration boundary
  contract existed. The repository already has an internal planning-agent module
  and a frozen `/api/v1/agent/**` V0.6 compatibility surface, but no production
  Aily boundary.
- Decision: Freeze a two-direction integration boundary without live
  implementation in V0.7 P6.

## Context

Feishu Aily is an external conversation and orchestration product. Cold Storage
Planning Agent must use Aily for dialogue and intent collection while retaining
exclusive authority over engineering validation, deterministic calculation,
persistence, confirmation, audit, and report assembly.

V0.7 P0 §7 established frozen intent. V0.7 P6 turns that intent into contract
artifacts and architecture tests without implementing connectors or clients.

## Decision

### 1. Ownership split

| Domain | Owner |
| --- | --- |
| Dialogue, intent, natural-language phrasing | Feishu Aily |
| Project/version lifecycle | This system |
| `EngineeringInputBundleV1` validation | This system |
| Five-stage deterministic execution | This system |
| Calculation persistence and hashes | This system |
| Confirmation issuance and consumption | This system |
| Review / formal-export state machine | This system |
| Audit records | This system |
| Report assembly from persisted results | This system |

Aily MUST NOT compute engineering values, access ORM/database sessions, or
become approval authority.

### 2. Two call directions (must not be confused)

```text
Aily → this system: custom MCP or Feishu connector
  Contract: docs/contracts/aily/v0.7/aily-to-system-connector.v1.json

This system → Aily: skill / session / run OpenAPI
  Contract: docs/contracts/aily/v0.7/system-to-aily-openapi.v1.yaml
```

Inbound connector operations map to the four frozen model-visible tools.
Outbound OpenAPI calls create or resume Aily sessions for assistance only.

These directions MUST NOT share a single ambiguous "agent API" namespace.

### 3. Model-visible tool surface (exactly four)

Only these tools may appear in Aily model context:

1. `planning_context.get`
2. `engineering_inputs.validate`
3. `five_stage_execution.propose`
4. `report_delivery.propose`

Schemas are frozen in `docs/contracts/aily/v0.7/model-visible-tools.v1.json`.

Write tools (`five_stage_execution.propose`, `report_delivery.propose`) require
confirmation before execution.

### 4. Confirmation is not a model tool

Human confirmation uses a separate callback channel defined in
`docs/contracts/aily/v0.7/confirmation-callback.v1.json`.

- `confirmation_token` MUST NOT enter model context.
- Actor identity MUST come from trusted transport, not model JSON.
- Confirmation executes only the previously proposed tool call after
  re-authorization.

### 5. Forbidden model surfaces

`docs/contracts/aily/v0.7/forbidden-model-surfaces.v1.json` denies:

- `mark_reviewed`, `approve`, archive actions;
- legacy direct-calculation and legacy report tools;
- model self-attested actor fields;
- confirmation tokens and trusted-operator proofs in model replay payloads.

### 6. `/api/v1/agent/**` is not the Aily production boundary

The existing `/api/v1/agent/**` routes are a V0.6 internal compatibility
surface. V0.7 P6 freezes **no further extension** of that namespace for Aily.

Aily production inbound integration MUST use the dedicated connector/MCP
contract family, not expanded agent HTTP routes.

### 7. Live implementation gate

```text
AILY_LIVE_IMPLEMENTATION=NO
```

V0.7 P6 authorizes contract artifacts only:

- `docs/tasks/V0_7-P6-aily-integration-boundary-contract.md`
- `docs/architecture/ADR-027-aily-integration-boundary.md`
- `docs/contracts/aily/v0.7/**`
- `backend/tests/architecture/test_v07_p6_aily_contract.py`

Any MCP server, connector adapter, outbound Aily client, or skill registration
requires a later package with `AILY_LIVE_IMPLEMENTATION=YES`.

## Alternatives considered

1. **Reuse `/api/v1/agent/**` as the Aily boundary** — rejected because the
   namespace is already a V0.6 compatibility surface with a broader legacy tool
   registry and disabled-route matrix; extending it would blur compatibility
   and production boundaries.
2. **Expose `mark_reviewed` / `approve` as model tools** — rejected because
   review authority must remain outside model context and tied to trusted
   operator transport.
3. **Let the model pass `actor` in tool arguments** — rejected; actor identity
   must be transport-derived for audit integrity.

## Consequences

- P6 closes the documentation gap (`V07-GAP-008` freeze) without runtime
  behavior change.
- Future Aily implementation packages must cite ADR-027 and the v0.7 contract
  artifacts; they cannot silently add tools or reuse agent routes.
- P7 controlled acceptance can require boundary evidence without live Aily
  enablement.
- Legacy planning-agent tools remain internal until explicitly migrated or
  retired under a separate authorized amendment.

## References

- `docs/tasks/V0_7-P0-trust-loop-contract.md` §7
- `docs/tasks/V0_7-P6-aily-integration-boundary-contract.md`
- `docs/tasks/V0_3-P2-production-agent-gateway-contract.md`
- `docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md`
