# Aily v0.7 static contracts

Frozen static contract artifacts for the Feishu Aily integration boundary.
These files define intent only; they do not implement live MCP, connectors, or
outbound clients.

**Authority:** `docs/tasks/V0_7-P6-aily-integration-boundary-contract.md`
**ADR:** `docs/architecture/ADR-027-aily-integration-boundary.md`
**Live implementation:** `AILY_LIVE_IMPLEMENTATION=NO`

## Artifact index

| File | Direction | Purpose |
| --- | --- | --- |
| `model-visible-tools.v1.json` | Aily model context | Exactly four model-visible tools |
| `confirmation-callback.v1.json` | Human callback | Non-model confirmation channel |
| `forbidden-model-surfaces.v1.json` | Policy | Deny list for model context |
| `aily-to-system-connector.v1.json` | Aily → system | MCP/connector operation map |
| `system-to-aily-openapi.v1.yaml` | System → Aily | Skill/session/run OpenAPI stub |

## Frozen rules (summary)

1. Model-visible tools are exactly four; no aliases.
2. Confirmation callback is not a model tool.
3. `confirmation_token` must not enter model context.
4. Actor identity must come from trusted transport, not model JSON.
5. `/api/v1/agent/**` is V0.6 internal compatibility only — not extended for Aily.
6. Reports must read persisted results; no formula recalculation in tools.

## Versioning

- Contract family: `v0.7`
- Schema suffix: `v1`
- Breaking changes require a new contract directory (for example `v0.8`) and ADR
  amendment.
