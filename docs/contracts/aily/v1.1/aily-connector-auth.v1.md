# Aily Connector Transport Auth (v1)

Supplement for inbound zone-plan connector authentication. Does not replace
`docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml`.

## Scope

Transport shared-secret gate for `POST /api/v1/aily/v1/zone-plan`. This is not production RBAC.

## Configuration

| Canonical suffix | Full env var |
|------------------|--------------|
| `AILY_CONNECTOR_SHARED_SECRET` | `COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET` |

Optional. When unset or blank, the route is open (local/test default).

## Request header

| Header | Required when secret set | Description |
|--------|--------------------------|-------------|
| `X-Aily-Connector-Key` | Yes | Must match configured secret (UTF-8, `hmac.compare_digest`) |

## Security scheme (documentation only)

```yaml
components:
  securitySchemes:
    AilyConnectorKey:
      type: apiKey
      in: header
      name: X-Aily-Connector-Key
      description: >
        Optional transport secret. Required only when
        COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET is set.
```

Apply to `POST /api/v1/aily/v1/zone-plan` when secret is configured.

## Error response (401)

When secret is configured and header is missing or wrong:

```json
{
  "error": {
    "code": "AILY_CONNECTOR_UNAUTHORIZED",
    "message": "Invalid or missing Aily connector authentication",
    "field_path": "headers.X-Aily-Connector-Key",
    "missing_keys": [],
    "ask_operator": "",
    "details": {}
  }
}
```

## Non-goals

- User roles, JWT, OAuth, or production RBAC
- `mark_reviewed` or engineering review workflows
- Outbound Feishu session clients
