# V1.1 P3 Aily Connector Transport Auth Contract

**Status:** Implementation — inbound connector shared secret  
**Authority:** Charles 2026-08-28 parallel V1.1 follow-ups  
**Base `main` SHA:** `938002546090ac0ca0932c65c48e83cd107a6702`  
**Target branch:** `cursor/v11-p3-aily-connector-auth-742e`

Companion: `docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`,
`docs/contracts/aily/v1.1/aily-connector-auth.v1.md`.

## 0. Governance

```text
TASK=V11_P3_AILY_CONNECTOR_TRANSPORT_AUTH_R1
GOVERNANCE_OWNER=V1.1
PREVIOUS_RELEASE=v1.0.0
BASE_MAIN_SHA=938002546090ac0ca0932c65c48e83cd107a6702
TARGET_BRANCH=cursor/v11-p3-aily-connector-auth-742e
TARGET_FILE=docs/tasks/V1_1-P3-aily-connector-auth-contract.md

V11_P3_IMPLEMENTATION_AUTHORIZED=YES
AILY_INBOUND_ZONE_PLAN_PREVIEW=YES
AILY_OUTBOUND_LIVE_SESSION=NO
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
PRODUCTION_RBAC_CLAIM=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

## 1. Objective

Protect `POST /api/v1/aily/v1/zone-plan` with an optional shared secret so
豆包's custom connector can authenticate at the transport layer.

This is **not** production RBAC, not `mark_reviewed`, not user roles.

## 2. Configuration

Canonical environment key:

```text
AILY_CONNECTOR_SHARED_SECRET → COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET
```

Registered in `environment_model.CANONICAL_KEYS` and `_SENSITIVE_KEYS`.
Settings field: `aily_connector_shared_secret` (optional `str | None`).

| Secret state | Behavior |
|--------------|----------|
| unset or blank | Open — existing tests POST without header still pass |
| set (non-blank) | Fail closed — header required and must match |

## 3. HTTP

Route: `POST /api/v1/aily/v1/zone-plan`

Header: `X-Aily-Connector-Key`

When secret is configured:

- missing or wrong header → HTTP 401
- JSON body: `{ "error": { "code": "AILY_CONNECTOR_UNAUTHORIZED", ... } }`
- zone kernel must not run

When secret is unset/blank:

- header optional; route behaves as P0/P1

Comparison uses `hmac.compare_digest` on UTF-8 bytes. Secret must not be logged.

## 4. Layering

- Auth check lives in `cold_storage.modules.aily.application.connector_auth`
- API route is thin: calls application auth before `preview_zone_plan`
- API routes must not import `cold_storage.modules.calculations`
- Actor remains transport `aily-connector`, never model JSON

## 5. Non-goals

- Production RBAC / user roles
- `mark_reviewed` exposure
- Extending `/api/v1/agent/**`
- Feishu outbound live session
- Editing `aily-to-system-zone-plan.openapi.yaml` (see separate auth doc)

## 6. Tests

- Unset secret: five-KEY POST on `create_app()` → 200
- Set secret: no header → 401; wrong key → 401; correct header → 200
- Chat utterance with secret set → 400 `MISSING_ENGINEERING_PARAMETER` (auth first)
- Architecture: API does not import calculations module
