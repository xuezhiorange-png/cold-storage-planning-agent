# V0.3 P2 Production Agent Gateway Contract

**Status:** Definition freeze only
**Authority:** Issue #108, tracked by Issue #110
**Contract source SHA:** `8de42a7490d9e6c5cc3519b139e9daf154fd33cb`
**Contract source tree SHA:** `be70aa7b8a504fd350233ac3cb1983a73bee7930`

This document freezes the authority and implementation boundaries for the
V0.3 P2 production agent gateway. It does not implement a provider, add a
dependency, add credentials, enable the agent in staging or production, or
change runtime behavior. The contract round is documentation-only.

## 1. Scope and authority

P2 adds a provider boundary to the existing planning-agent application. The
model may return an orchestration decision, but it is never an engineering,
approval, persistence, or authorization authority.

The following remain authoritative outside the model gateway:

- deterministic calculation and validation services;
- coefficient and unit authorities;
- scheme generation and scoring;
- report lifecycle and formal approval;
- project/version authorization;
- tool registration, argument validation, output validation, and confirmation;
- persisted session, turn, tool-call, confirmation, and idempotency records.

This contract does not authorize P2 implementation. A later implementation
authorization must cite this exact contract and use only the frozen future
allowlists in this document.

## 2. Audited current main

The following current-main paths were read at the source SHA above:

- `backend/src/cold_storage/modules/planning_agent/domain/gateways.py`
- `backend/src/cold_storage/modules/planning_agent/infrastructure/fake_gateways.py`
- `backend/src/cold_storage/modules/planning_agent/application/orchestrator.py`
- `backend/src/cold_storage/modules/planning_agent/application/service.py`
- `backend/src/cold_storage/bootstrap/app.py`
- `backend/src/cold_storage/bootstrap/dependencies.py`
- `backend/src/cold_storage/bootstrap/runtime_readiness.py`
- `backend/src/cold_storage/bootstrap/settings.py`
- `backend/src/cold_storage/modules/planning_agent/application/tool_registry.py`
- `backend/src/cold_storage/modules/planning_agent/domain/models.py`
- `backend/src/cold_storage/modules/planning_agent/domain/errors.py`
- `backend/src/cold_storage/modules/planning_agent/domain/authorization.py`
- `backend/tests/unit/test_planning_agent_gateway.py`
- `backend/tests/unit/test_planning_agent_service.py`
- `backend/tests/unit/test_planning_agent_api.py`
- `backend/tests/unit/test_planning_agent_comprehensive.py`
- `backend/tests/unit/test_runtime_readiness.py`
- `docs/architecture/ADR-005-model-gateway.md`

The audit records the following facts. These are current behavior, not an
authorization to preserve an unsafe behavior in a future strict provider
implementation.

### 2.1 Current gateway port

`AgentModelRequest` is a frozen dataclass with:

- `system_prompt: str`;
- ordered `messages: list[dict[str, Any]]`;
- ordered `tools: list[dict[str, Any]]`;
- `temperature: float`;
- `max_tokens: int`.

`AgentModelGateway` exposes only:

```text
generate_decision(request: AgentModelRequest) -> AgentDecision
```

`GatewayMetadata` currently carries `provider`, `model_name`,
`gateway_version`, `production_ready`, and `requires_review`.

`AgentDecision` currently carries the decision type, assistant message,
missing parameters, tool requests, citations, `requires_review`, and
warnings. The current decision enum is exactly:

```text
answer
ask_clarification
propose_tools
```

### 2.2 Current fake and strict behavior

`FakeAgentModelGateway` is deterministic, has no network access, and routes
fixed test/local inputs to fixed structured decisions. It asks for missing
throughput or scheme inputs instead of silently inventing them.

`DefaultAgentModelGateway` currently falls back to the fake gateway when its
production-ready flag is false. That behavior is covered by legacy local/test
tests and is not a valid strict production selection mechanism. The future
contract below forbids using that fallback in staging or production.

In local and test modes, the active agent composition uses the fake-backed
service. In staging and production:

- the active model-backed agent service is not constructed;
- the agent HTTP surface is a frozen disabled-route matrix returning the
  stable out-of-scope response;
- the strict composition manifest binds `model_backed_agent` to `disabled`;
- the strict runtime audit rejects reachable fake composition and unexpected
  agent routes;
- startup/readiness remains fail-closed when the strict audit or mandatory
  probes fail.

There is no real provider adapter and no provider call path in the audited
source. No provider SDK is present in the runtime dependency list. The only
audited HTTP client is `httpx`, currently declared in the development group
of `backend/pyproject.toml` and locked in `backend/uv.lock`.

`COLD_STORAGE_OPENAI_API_KEY` exists as a redacted settings field, but it is
not provider selection, provider readiness, or evidence that a provider
adapter is configured.

### 2.3 Current application boundaries

The orchestrator:

1. builds ordered prior/user messages and the registered tool definitions;
2. calls the injected gateway;
3. rejects unknown decision types;
4. rejects unregistered tools;
5. validates tool arguments against the registered JSON Schema;
6. creates persisted tool-call and confirmation records;
7. auto-executes only tools registered without confirmation;
8. validates deterministic tool output against the registered output schema;
9. persists messages, turn state, request SHA-256, metadata, and CAS updates.

Gateway exceptions are currently wrapped as `ModelGatewayError`. The future
provider error taxonomy in this contract must preserve the application
boundary while making those failures classifiable and fail-closed.

The service already provides session ownership checks, project/version
binding checks, idempotency claim/replay handling, concurrent-turn handling,
confirmation token validation, atomic confirmation claiming, tool-call state
transitions, and failed-turn persistence. P2 must reuse these boundaries.

The current authorization rules require an owner or administrator for
calculate/write operations, forbid writes to approved versions, and require
confirmation for write/calculate levels when the registered tool says so.

### 2.4 Current persistence and logging facts

The current planning-agent persistence surface includes:

- `AgentMessage.content` and optional structured content;
- `AgentTurn.model_provider`, `model_name`, `prompt_version`, request SHA-256,
  decision snapshot, warnings, review flag, and errors;
- `AgentToolCall` arguments, argument SHA-256, result, warnings, review flag,
  and errors;
- `AgentConfirmation` token hash, argument hash, session/tool binding, actor,
  expiry, and one-time status;
- idempotency records and CAS/version state.

The raw confirmation token is not persisted; only its hash is persisted. The
application SHA helper is canonical JSON plus SHA-256.

The existing configuration redactor covers database URLs, passwords, API
keys, tokens, authorization values, signed URLs, cookies, secret environment
variables, and credential-bearing exception text. Structured HTTP logging
emits bounded request metadata and redacted exception text rather than request
bodies. P2 must retain and extend this fail-closed posture without logging
model credentials or full provider payloads.

ADR-005 remains a read-only historical authority. It establishes a fake
default for the earlier V1/V1.1 testable boundary; it is not rewritten by this
contract and does not authorize a strict production fake fallback.

## 3. Canonical production gateway contract

The application/domain boundary remains provider-neutral. A provider adapter
must accept the existing request port and return one canonical `AgentDecision`
or a typed gateway failure. Provider-native response objects must not cross
the infrastructure boundary.

The canonical decision object is a closed structured object with these
semantic fields:

```text
decision_type: answer | ask_clarification | propose_tools
assistant_message: string
missing_parameters: ordered list of structured parameter descriptions
tool_requests: ordered list of {tool_name, arguments, reason}
citations: ordered list of structured citations
requires_review: boolean
warnings: ordered list of strings
```

The adapter must reject, rather than coerce or guess, an unknown decision type,
wrong field type, malformed nested object, unbounded response, or provider
response that cannot be mapped losslessly to this closed structure. Unknown
fields at the provider-to-application mapping boundary are a contract error
unless an explicitly versioned adapter schema declares them as ignorable
transport metadata. They must never change engineering or approval behavior.

`requires_review` is carried as provider/application evidence only. It does
not grant approval and does not override deterministic result flags,
calculation warnings, scheme scoring, report quality, or lifecycle state.

`ANSWER` may return explanatory text only. `ASK_CLARIFICATION` must identify
the missing or ambiguous inputs without inventing values. `PROPOSE_TOOLS` may
contain only registered tool names and schema-valid arguments after the
application revalidates the proposal.

The gateway must not expose a direct `execute_tool` or `approve_report` model
authority. The model can propose; the application decides whether a proposal
is valid and executable.

## 4. Explicit provider selection and readiness

Provider selection is an explicit runtime decision. In staging and production,
the Agent may be intentionally disabled without provider-specific
configuration. Once enablement intent exists, the application must require a
provider identifier from an allow-listed configuration value and a model
identifier. Availability of a package, environment variable, network route,
or API key must never infer the provider.

The effective future configuration contract is:

```text
COLD_STORAGE_AGENT_PROVIDER
  optional when Agent intentionally disabled
  required when Agent enablement intent exists
  allow-listed provider id
COLD_STORAGE_AGENT_MODEL
  optional when Agent intentionally disabled
  required when Agent enablement intent exists
COLD_STORAGE_AGENT_TIMEOUT_SECONDS
  optional when Agent intentionally disabled
  required when Agent enablement intent exists
  integer 1..30
COLD_STORAGE_AGENT_MAX_RETRIES
  optional when Agent intentionally disabled
  required when Agent enablement intent exists
  integer 0..1
COLD_STORAGE_OPENAI_API_KEY
  optional when Agent intentionally disabled
  required only for enabled/openai provider readiness
```

The enablement-intent authority is exact:

```text
AGENT_ENABLEMENT_INTENT_PRESENT=
COLD_STORAGE_AGENT_PROVIDER is supplied OR COLD_STORAGE_AGENT_MODEL is supplied
```

Neither timeout configuration, retry configuration, credential presence,
package installation, network availability, nor any other environmental fact
creates enablement intent.

The first concrete provider authority is frozen by Issue #110 record
`5323439225`. The existing `COLD_STORAGE_OPENAI_API_KEY` field alone still
does not enable an agent; the complete explicit provider and readiness
contract below is required.

Rules for strict environments:

1. if both provider id and model id are absent, enablement intent is absent and
   the capability is intentionally `AGENT_CAPABILITY_DISABLED`; timeout,
   retry, model, provider credential, and provider readiness evidence are not
   required;
2. if provider id or model id is supplied, enablement intent is present and
   the complete Agent/provider configuration is mandatory;
3. a provider id or model id supplied without the complete explicit selection
   is `AGENT_CAPABILITY_ENABLED_NOT_READY` and fails closed;
4. an unknown provider id fails closed and does not try another provider;
5. invalid or missing credentials fail closed and do not construct a fake;
6. a real adapter is constructed only for the explicit provider id;
7. a readiness probe must validate configuration, credentials, bounded
   timeout, response schema, and strict composition before routes are enabled;
8. startup must bind the adapter/provider identity to the strict capability
   manifest and rerun the existing unsafe-capability audit;
9. no configuration-only flag may bypass readiness or the strict route audit;
10. if readiness is not verified, strict routes remain disabled.

`FakeAgentModelGateway`, `DefaultAgentModelGateway` fake fallback, demo keyword
routing, and test adapters remain permitted only when explicitly injected in
local/demo/test composition. They are forbidden on a reachable staging or
production model-backed route.

There is no autonomous multi-provider routing. A provider change requires a
new explicit configuration and readiness decision; it must not silently fall
back to a second provider.

### 4.1 Frozen first concrete provider authority

The first production provider is explicitly frozen as follows. This freezes
the provider contract only; it does not authorize implementation, dependency
mutation, credential mutation, provider calls, or production enablement.

```text
FIRST_PROVIDER_ID=openai
PROVIDER_API_SURFACE=OpenAI Responses API
PROVIDER_TRANSPORT=official openai Python SDK
PROVIDER_BASE_URL_POLICY=official OpenAI API endpoint only; custom base URL forbidden unless separately authorized
PROVIDER_CREDENTIAL_SOURCE=COLD_STORAGE_OPENAI_API_KEY
PROVIDER_MODEL_AUTHORITY=COLD_STORAGE_AGENT_MODEL; explicit configuration required; no production default model; no automatic model selection
PROVIDER_TIMEOUT_AUTHORITY=COLD_STORAGE_AGENT_TIMEOUT_SECONDS
PROVIDER_RETRY_AUTHORITY=application gateway policy
OPENAI_SDK_MAX_RETRIES=0
MAX_PROVIDER_ATTEMPTS=2
MAX_PROVIDER_RETRIES=1
OPENAI_STORE=false
OPENAI_BACKGROUND_MODE=FORBIDDEN
OPENAI_CONVERSATION_STATE=FORBIDDEN
PROVIDER_TEST_TRANSPORT=mocked/injected OpenAI client transport; no live network in ordinary CI
PROVIDER_DEPENDENCY_STRATEGY=official openai Python package as direct runtime dependency; exact resolved version locked in backend/uv.lock only during separately authorized implementation
```

The selected provider is `openai` only when
`COLD_STORAGE_AGENT_PROVIDER=openai` and
`COLD_STORAGE_AGENT_MODEL` is explicitly present. No other provider id is
implicitly supported by this contract. The official endpoint policy forbids a
custom base URL unless a later contract amendment explicitly authorizes it.
The SDK's own retries are disabled; only the application gateway retry policy
in Section 9 applies. The provider must not retain server-side state through
store, background, or conversation-state features.

## 5. Provider adapter architecture

The future implementation must place provider SDK or HTTP handling in an
infrastructure adapter. `PlanningAgentService`, `AgentOrchestrator`, tool
adapters, and domain models must remain provider-neutral.

The exact future adapter seam is:

```text
AgentModelGateway port
    -> infrastructure real-provider gateway adapter
    -> provider transport/client
    -> strict canonical AgentDecision decoder
```

The first concrete provider adapter authority is frozen in Section 4.1. A
later P2 implementation authorization may implement that exact adapter, but
this definition freeze does not install the SDK, call OpenAI, or enable an
adapter. The current dependency audit found no provider SDK, so the frozen
runtime dependency strategy is prospective only and does not change the
current dependency graph.

No provider-specific business rules, prompt routing, engineering formulas,
scheme scoring, or approval decisions may be placed in the adapter.

## 6. Structured output and input authority

The adapter and orchestrator must enforce the following order:

1. decode provider output as a bounded structured object;
2. validate the closed decision type and fields;
3. map to `AgentDecision` without stringifying nested objects;
4. validate every proposed tool name against `ToolRegistry`;
5. validate every argument object against the registered input schema;
6. apply project/version authorization and lifecycle checks;
7. create a confirmation boundary when required;
8. execute deterministic application tools only after all applicable checks;
9. validate deterministic output against the registered output schema;
10. persist the application result and audit identity.

Missing, ambiguous, contradictory, or unit-incomplete critical inputs must
produce `ASK_CLARIFICATION` or an application validation error. The model may
ask for clarification, but the application and deterministic calculators must
repeat the authoritative validation. Model prose cannot bypass input,
authorization, schema, or lifecycle validation.

## 7. Tool authority and confirmation matrix

The following matrix freezes the audited 13-tool registry. Names and versions
are the current explicit allow-list; a new tool requires a separate contract
amendment and implementation authorization.

| Tool | Class | Current auto-execution | Confirmation | Boundary |
| --- | --- | --- | --- | --- |
| `knowledge.search` | READ | yes | no | read-only knowledge lookup |
| `project.get` | READ | yes | no | read-only project lookup |
| `project_version.get` | READ | yes | no | read-only version lookup |
| `planning.calculate_throughput_inventory_area` | DETERMINISTIC_CALCULATE | yes | no | deterministic calculation with existing version authorization |
| `planning.calculate_cooling_load_and_equipment` | DETERMINISTIC_CALCULATE | yes | no | deterministic calculation with existing version authorization |
| `scheme.generate_and_compare` | MUTATING | no | yes | project/version-bound scheme write |
| `report.create` | MUTATING | no | yes | report creation |
| `report.generate` | MUTATING | no | yes | report generation |
| `report.get` | READ | yes | no | read-only report lookup |
| `report.compare_revisions` | READ | yes | no | read-only revision comparison |
| `report.render` | MUTATING | no | yes | formal/export side effect |
| `report.list_exports` | READ | yes | no | read-only export listing |
| `report.get_export` | READ | yes | no | read-only export retrieval |

The current calculation entries may auto-execute only because they are
deterministic and the application already applies authorization, version
status, argument, and output validation. This does not make the model the
calculation authority. Any future calculation side effect outside the
audited application boundary requires a new confirmation decision.

All project, project-version, scheme, report, workflow, or formal-export
mutations require the existing application authorization and explicit
confirmation rules. The model cannot mark its own proposal as confirmed.

Confirmation remains:

- one-time and atomically claimed;
- bound to the exact session, tool call, and argument SHA-256;
- bound to the authorized actor;
- expiring with the current bounded TTL behavior;
- rejected when expired, already used, stale, replayed, or argument-mismatched;
- persisted as a token hash, never as the plaintext token.

`AUTONOMOUS_PROJECT_MUTATION_AUTHORIZED=NO` is frozen.

## 8. Provider failure semantics

The future adapter must classify failures without exposing provider secrets or
raw credentials. The following exact machine-readable codes are the complete
provider failure authority. `RETRYABLE=YES` means that the code is eligible
for at most one application-gateway retry before any side effect; it does not
authorize an unbounded client retry or a retry after a mutation.

| Code | Retryable | Turn outcome | Session outcome | Readiness impact | Safe external projection |
| --- | --- | --- | --- | --- | --- |
| `AGENT_PROVIDER_CONFIGURATION_MISSING` | NO | `FAIL_CLOSED` | `REUSABLE` | `NOT_READY` | `error.code` exact code; fixed message `agent provider configuration is missing`; `details.retryable=false` |
| `AGENT_PROVIDER_CONFIGURATION_INVALID` | NO | `FAIL_CLOSED` | `REUSABLE` | `NOT_READY` | `error.code` exact code; fixed message `agent provider configuration is invalid`; `details.retryable=false` |
| `AGENT_PROVIDER_CREDENTIAL_INVALID` | NO | `FAIL_CLOSED` | `REUSABLE` | `NOT_READY` | `error.code` exact code; fixed message `agent provider credentials are invalid`; `details.retryable=false` |
| `AGENT_PROVIDER_TIMEOUT` | YES | `FAIL_CLOSED_AFTER_RETRY_EXHAUSTION` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider request timed out`; `details.retryable=true` |
| `AGENT_PROVIDER_CONNECTION_FAILED` | YES | `FAIL_CLOSED_AFTER_RETRY_EXHAUSTION` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider connection failed`; `details.retryable=true` |
| `AGENT_PROVIDER_RATE_LIMITED` | YES | `FAIL_CLOSED_AFTER_RETRY_EXHAUSTION` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider rate limited`; `details.retryable=true` |
| `AGENT_PROVIDER_UPSTREAM_5XX` | YES | `FAIL_CLOSED_AFTER_RETRY_EXHAUSTION` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider upstream failure`; `details.retryable=true` |
| `AGENT_PROVIDER_RESPONSE_MALFORMED` | NO | `FAIL_CLOSED` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider response is malformed`; `details.retryable=false` |
| `AGENT_PROVIDER_RESPONSE_TOO_LARGE` | NO | `FAIL_CLOSED` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider response is too large`; `details.retryable=false` |
| `AGENT_PROVIDER_UNAVAILABLE` | YES | `FAIL_CLOSED_AFTER_RETRY_EXHAUSTION` | `REUSABLE` | `PROBE_FAILS` | `error.code` exact code; fixed message `agent provider is unavailable`; `details.retryable=true` |

The safe projection is the complete external error shape for these failures:
`{"error":{"code":"<frozen code>","message":"<frozen safe message>","details":{"retryable":<frozen boolean>}}}`.
Provider response bodies, headers, credentials, endpoint details, raw
exception text, and provider-native status payloads are never included. No
other stable provider failure code may be invented by implementation without
a contract amendment. Every failed turn retains the frozen classification and
must not execute a tool as compensation.

No provider error may instantiate or invoke `FakeAgentModelGateway`,
`DefaultAgentModelGateway` fallback behavior, a demo adapter, or another
provider. Provider failures are not user confirmation.

Provider configuration and credential failures are operational readiness
failures. A transient ordinary turn failure must not silently change the
strict capability binding. A readiness probe failure places an explicitly
enabled capability in `AGENT_CAPABILITY_ENABLED_NOT_READY` until a fresh
verified readiness phase succeeds.

## 9. Timeout and retry boundary

The provider request timeout is frozen as an integer configuration contract:

```text
COLD_STORAGE_AGENT_TIMEOUT_SECONDS
TYPE=integer
MIN=1
MAX=30
STAGING_PRODUCTION_EXPLICIT_REQUIRED_WHEN_AGENT_ENABLEMENT_INTENT_PRESENT=YES
STAGING_PRODUCTION_REQUIRED_WHEN_AGENT_DISABLED=NO
STAGING_PRODUCTION_DEFAULT_ALLOWED=NO
ZERO_ALLOWED=NO
NEGATIVE_ALLOWED=NO
NON_INTEGER_ALLOWED=NO
NAN_INF_ALLOWED=NO
OUT_OF_RANGE_ALLOWED=NO
```

Staging and production must receive an explicit integer value; neither mode
may supply an implicit default. Values outside the closed inclusive range
`1..30` are configuration-invalid and map to
`AGENT_PROVIDER_CONFIGURATION_INVALID`. Implementation may consume this
range but may not redefine its type, bounds, default policy, or rejection
semantics.

The application retry count is frozen as a separate integer configuration
contract:

```text
AGENT_MAX_RETRIES_CONFIGURATION_AUTHORITY=COLD_STORAGE_AGENT_MAX_RETRIES
TYPE=integer
MIN=0
MAX=1
ALLOWED_VALUES=0,1
STAGING_PRODUCTION_EXPLICIT_REQUIRED_WHEN_AGENT_ENABLEMENT_INTENT_PRESENT=YES
STAGING_PRODUCTION_REQUIRED_WHEN_AGENT_DISABLED=NO
STAGING_PRODUCTION_DEFAULT_ALLOWED=NO
ZERO_ALLOWED=YES
NEGATIVE_ALLOWED=NO
NON_INTEGER_ALLOWED=NO
NAN_INF_ALLOWED=NO
OUT_OF_RANGE_ALLOWED=NO
MAX_PROVIDER_RETRIES=1
MAX_PROVIDER_ATTEMPTS=2
```

The effective application rule is exact: configured retries `0` permits one
provider attempt, while configured retries `1` permits two provider attempts.
The application must never exceed one retry or two attempts. The official
OpenAI SDK remains configured with `OPENAI_SDK_MAX_RETRIES=0`; the SDK never
owns application retry policy. The retryable failure-code set in Section 8 is
unchanged, and no retry is permitted after any tool side effect, confirmation
claim, or mutation.

The retry policy is finite:

- maximum provider attempts: 2;
- maximum retries: 1;
- only timeout, connection, bounded rate-limit, 5xx, and unavailable failures
  may be retried;
- backoff is bounded and must be included in the total request budget;
- no retry occurs after a tool side effect, confirmation claim, or mutation;
- tool execution idempotency and CAS remain application concerns;
- confirmation execution is never retried by the provider transport policy;
- no unbounded retry, background approval retry, or timestamp-based winner
  selection is permitted.

## 10. Runtime capability states and readiness transition

The capability state is a closed three-state authority. It must never be
collapsed into a single `enabled` boolean or inferred from route presence.

| State | Meaning | Global application readiness | Route exposure |
| --- | --- | --- | --- |
| `AGENT_CAPABILITY_DISABLED` | Intentional capability-off state: neither provider id nor model id is configured; no provider is selected | `PASS_IF_ALL_OTHER_MANDATORY_READINESS_GATES_PASS` | `DISABLED_ROUTE_MATRIX` |
| `AGENT_CAPABILITY_ENABLED_READY` | Explicit `openai` provider and model are configured; credentials, bounded settings, adapter/schema probe, strict composition, and route audit all pass | `PASS_IF_PROVIDER_AND_ALL_OTHER_MANDATORY_READINESS_GATES_PASS` | `REAL_AGENT_ROUTES_ENABLED` |
| `AGENT_CAPABILITY_ENABLED_NOT_READY` | Explicit enablement intent exists, but configuration, credentials, provider availability, probe, composition, or route audit is invalid or unavailable | `FAIL` | `DISABLED_ROUTE_MATRIX` |

The disabled-state contract is explicit:

```text
AGENT_ENABLEMENT_INTENT_PRESENT=NO
CAPABILITY_STATE=AGENT_CAPABILITY_DISABLED
COLD_STORAGE_AGENT_TIMEOUT_SECONDS_REQUIRED=NO
COLD_STORAGE_AGENT_MAX_RETRIES_REQUIRED=NO
COLD_STORAGE_OPENAI_API_KEY_REQUIRED=NO
AGENT_SPECIFIC_CONFIG_ABSENCE_IS_CONFIGURATION_ERROR=NO
AGENT_SPECIFIC_CONFIG_ABSENCE_FAILS_GLOBAL_READINESS=NO
GLOBAL_APPLICATION_READINESS=PASS_IF_ALL_OTHER_MANDATORY_READINESS_GATES_PASS
ROUTE_EXPOSURE=DISABLED_ROUTE_MATRIX
REAL_PROVIDER_CONSTRUCTED=NO
FAKE_PROVIDER_CONSTRUCTED_ON_STRICT_ROUTE=NO
```

An intentionally disabled Agent does not require provider-specific timeout,
retry, model, provider credential, or provider-readiness evidence.

The enabled-state contract is also explicit:

```text
AGENT_ENABLEMENT_INTENT_PRESENT=YES
COLD_STORAGE_AGENT_PROVIDER_REQUIRED=YES
COLD_STORAGE_AGENT_MODEL_REQUIRED=YES
COLD_STORAGE_AGENT_TIMEOUT_SECONDS_REQUIRED=YES
COLD_STORAGE_AGENT_MAX_RETRIES_REQUIRED=YES
OPENAI_CREDENTIAL_REQUIRED_WHEN_PROVIDER=openai
CAPABILITY_STATE_ON_MISSING_INVALID_UNSUPPORTED_OR_UNUSABLE_REQUIRED_FIELD=AGENT_CAPABILITY_ENABLED_NOT_READY
GLOBAL_APPLICATION_READINESS_ON_ENABLED_NOT_READY=FAIL
ROUTE_EXPOSURE_ON_ENABLED_NOT_READY=DISABLED_ROUTE_MATRIX
REAL_AGENT_ROUTES_REACHABLE_ON_ENABLED_NOT_READY=NO
FAKE_FALLBACK_ON_ENABLED_NOT_READY=NO
```

The state-selection rule is deterministic:

1. neither `COLD_STORAGE_AGENT_PROVIDER` nor `COLD_STORAGE_AGENT_MODEL` is
   supplied -> `AGENT_CAPABILITY_DISABLED`;
2. either setting is supplied without the complete explicit selection, or the
   selected provider/configuration cannot be validated ->
   `AGENT_CAPABILITY_ENABLED_NOT_READY`;
3. `COLD_STORAGE_AGENT_PROVIDER=openai` plus an explicit model, valid secret
   source, bounded settings, successful provider/schema readiness probe, strict
   composition, and route audit PASS -> `AGENT_CAPABILITY_ENABLED_READY`.

An intentionally disabled capability is therefore distinct from an explicitly
enabled but misconfigured or unavailable provider. Disabled routes must use
the existing stable disabled-route matrix and must not construct a fake
gateway. Enabled-not-ready routes use the same disabled matrix, while global
readiness fails. Only enabled-ready may expose real agent routes. The
transition must be atomic from the application's readiness perspective. The
capability manifest must record the exact provider identity and readiness
evidence; a generic `enabled=true`, a configured API key, or a self-attested
adapter is not sufficient.

The existing startup/readiness phases, strict authority object, mandatory
probes, disabled-route matrix, and unsafe-capability enumeration remain the
authority. P2 must extend them narrowly; it must not weaken or bypass them.

## 11. Sensitive model I/O and persistence

The following must never appear in plaintext in logs, metrics, health
responses, exception text, audit labels, evidence files, or user-visible
agent messages:

- provider API keys and credential material;
- authorization headers and bearer tokens;
- confirmation tokens;
- database/password/secret values;
- signed URLs or cookies;
- full sensitive source documents unless a separately authorized business
  requirement and redaction policy exists.

The provider wire envelope is not persisted by default. The application may
persist only the existing, bounded application records: user/assistant
messages required by session history, the validated `AgentDecision` snapshot,
warnings, tool-call result records, provider/model metadata, and request
identity/hash. Raw provider response, hidden prompt material, headers, and
credentials must not be placed in `decision_snapshot`, `structured_content`,
tool results, or error strings.

If a future requirement needs raw prompt/response retention, it requires a
separate authorization that specifies purpose, minimum fields, redaction,
retention, access surface, and content hash. It is not implied by this
contract.

Existing `ConfigurationRedactor` and `redact_for_logging` are mandatory
boundaries for provider exceptions and operational diagnostics. Redaction
failure is fail-closed. Prompt/response text must not become a metric label or
an unbounded log field.

## 12. Observability

Provider-neutral observability may expose only bounded, non-sensitive values:

- provider id;
- model id, after explicit allow-listing and cardinality review;
- gateway version;
- request SHA-256 or an equivalent stable request identity;
- latency bucket or bounded duration;
- success/failure classification;
- bounded tool-call count;
- retry count and readiness state.

Provider credentials, authorization data, raw prompts, raw responses, tool
arguments, confirmation tokens, and unbounded user/project identifiers are
not metric labels. Detailed application records retain the existing exact
identity fields only where required for lifecycle and audit behavior.

## 13. Engineering authority separation

The following statements are frozen invariants:

```text
MODEL_PROPOSES_TOOL_CALLS=YES
MODEL_EXECUTES_ENGINEERING_FORMULAS=NO
MODEL_WRITES_AUTHORITATIVE_ENGINEERING_RESULTS=NO
MODEL_OVERRIDES_CALCULATOR_RESULTS=NO
MODEL_OVERRIDES_SCHEME_SCORING=NO
MODEL_APPROVES_REPORT=NO
DETERMINISTIC_OUTPUT_WINS=YES
```

The model must not become authoritative for cooling load, area, power,
equipment capability, investment, scheme scoring, review approval, or formal
report approval. If model prose conflicts with a deterministic tool result,
the deterministic result and its warnings/review flags win. If the model
proposes values that fail domain validation, the application rejects them or
asks for clarification; it does not repair them by guessing.

The deterministic five-stage calculation order remains an upstream authority
and is outside the model gateway:

```text
STAGE_ORDER=zone,cooling_load,equipment,power,investment
```

The gateway may describe or propose a tool call for a stage, but it may not
reorder, skip, synthesize, or reinterpret a stage result. A missing or
ambiguous stage input is an application/calculator validation condition, not a
model permission to invent a value.

## 14. Lifecycle preservation

P2 reuses the current:

- `AgentSession` lifecycle and ownership;
- `AgentTurn` processing/awaiting/completed/failed states;
- `AgentToolCall` proposed/awaiting/confirmed/executing/succeeded/failed
  states;
- `AgentConfirmation` expiry, hash binding, atomic claim, and replay checks;
- idempotency records and exact replay behavior;
- CAS/version checks;
- project/version authorization and approved-version write prohibition;
- registered tool input/output validation.

No new report status, project status, approval status, or background approval
state is introduced by P2. Any lifecycle expansion must be separately
justified and authorized.

## 15. Future implementation allowlists

These are exact future write authorities for a separately authorized P2
implementation. They are not write authority for this definition-freeze
round. No wildcard or directory-wide authority is granted.

### 15.1 Production code allowlist

```text
backend/src/cold_storage/modules/planning_agent/domain/gateways.py
backend/src/cold_storage/modules/planning_agent/domain/errors.py
backend/src/cold_storage/modules/planning_agent/infrastructure/real_gateways.py
backend/src/cold_storage/modules/planning_agent/application/orchestrator.py
backend/src/cold_storage/modules/planning_agent/application/service.py
backend/src/cold_storage/bootstrap/settings.py
backend/src/cold_storage/bootstrap/environment_model.py
backend/src/cold_storage/bootstrap/dependencies.py
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/bootstrap/runtime_readiness.py
backend/src/cold_storage/modules/planning_agent/api/routes.py
```

`real_gateways.py` is the single frozen infrastructure seam for the first
concrete provider adapter unless a later contract amendment names a more
specific provider file. No provider adapter may be placed in domain or
application code. The current fake gateway file is not a production-provider
write target and its local/test behavior remains read-only under this
contract.

`environment_model.py` is the canonical strict environment-key authority for
the four P2 keys named in Section 4. Its future P2 write authority is limited
to registering those keys while preserving strict unknown-key rejection,
legacy-key policy, resource/environment identity authority, and the existing
redacted `COLD_STORAGE_OPENAI_API_KEY` classification. It is not authority for
an unrelated configuration redesign.

`routes.py` is the future P2 API projection owner. Its write authority is
limited to projecting the ten frozen provider failure codes, their frozen safe
messages, and frozen retryable booleans in the existing API/HTTP and
actor/session boundaries. It must not expose provider-native bodies, headers,
credentials, authorization material, or raw exception text, and it must not
create an eleventh provider failure code or redesign unrelated API schemas.

The following are deliberately excluded from the P2 production allowlist:

```text
backend/src/cold_storage/modules/planning_agent/domain/models.py
backend/src/cold_storage/modules/planning_agent/application/tool_registry.py
backend/src/cold_storage/modules/planning_agent/infrastructure/fake_gateways.py
backend/src/cold_storage/modules/planning_agent/infrastructure/orm.py
```

If implementation proves one of these is required, it must stop and request a
contract amendment rather than silently widening scope.

### 15.2 Test allowlist

```text
backend/tests/unit/test_planning_agent_gateway.py
backend/tests/unit/test_planning_agent_service.py
backend/tests/unit/test_planning_agent_api.py
backend/tests/unit/test_planning_agent_comprehensive.py
backend/tests/unit/test_runtime_readiness.py
backend/tests/unit/test_planning_agent_real_gateway.py
backend/tests/unit/test_settings.py
backend/tests/architecture/test_architecture_boundaries.py
```

`test_planning_agent_real_gateway.py` is the exact new adapter unit-test
path. Provider transport must be mocked or replaced with a deterministic
test transport; ordinary CI must never call a live provider.

`test_settings.py` is the canonical P2 configuration test owner. It must cover
the four canonical P2 environment keys, strict unknown-`COLD_STORAGE_*` key
rejection, staging/production explicit configuration requirements,
timeout/retry shape validation, and preservation of existing Slice-1
configuration semantics. No broad `tests/**` wildcard is authorized.

### 15.3 Configuration/composition allowlist

```text
backend/src/cold_storage/bootstrap/settings.py
backend/src/cold_storage/bootstrap/environment_model.py
backend/src/cold_storage/bootstrap/dependencies.py
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/bootstrap/runtime_readiness.py
```

Configuration additions must be explicit, typed, redacted, bounded, and
validated in strict modes. `environment_model.py` may only register
`COLD_STORAGE_AGENT_PROVIDER`, `COLD_STORAGE_AGENT_MODEL`,
`COLD_STORAGE_AGENT_TIMEOUT_SECONDS`, and `COLD_STORAGE_AGENT_MAX_RETRIES`.
No environment variable alone may bypass the composition and readiness audit.

### 15.4 Dependency allowlist

```text
backend/pyproject.toml
backend/uv.lock
```

No dependency is added by this freeze. The first provider authority freezes
the runtime dependency and transport as:

```text
PROVIDER_TRANSPORT=official openai Python SDK
PROVIDER_RUNTIME_DEPENDENCY=openai Python package
HTTPX_AS_ALTERNATIVE_PROVIDER_TRANSPORT=NO
IMPLEMENTATION_MAY_SELECT_DIFFERENT_PROVIDER_PACKAGE=NO
CONTRACT_AMENDMENT_REQUIRED_FOR_DIFFERENT_PROVIDER_TRANSPORT_OR_PACKAGE=YES
CONTRACT_AMENDMENT_REQUIRED=YES
OPENAI_DEPENDENCY_DIRECT_PACKAGE=openai
OPENAI_DEPENDENCY_VERSION_POLICY=EXACT_PIN
PYPROJECT_FLOATING_SPECIFIER_ALLOWED=NO
PYPROJECT_WILDCARD_ALLOWED=NO
PRERELEASE_ALLOWED=NO
YANKED_RELEASE_ALLOWED=NO
GIT_REF_DEPENDENCY_ALLOWED=NO
DIRECT_URL_DEPENDENCY_ALLOWED=NO
ALTERNATIVE_PROVIDER_PACKAGE_ALLOWED=NO
HTTPX_AS_PROVIDER_TRANSPORT_ALLOWED=NO
UV_LOCK_EXACT_RESOLUTION_REQUIRED=YES
IMPLEMENTATION_MAY_CHANGE_VERSION_POLICY=NO
```

The existing `httpx` development dependency is not a provider transport and
must not be moved into the runtime dependency set for this purpose. A
separately authorized implementation may add only the official `openai`
Python package as the direct runtime dependency. It must audit a stable,
non-prerelease `openai` release compatible with Python `>=3.12`, record
`OPENAI_SDK_VERSION_SELECTED=<exact version>`, declare
`openai==<exact version>`, and produce the matching resolved entry in
`backend/uv.lock`. It must also record package/version/reason/license and
network-test evidence. It must block rather than select a prerelease, yanked
release, alternate package, direct Git dependency, direct URL dependency, or
direct HTTP transport. A later OpenAI SDK upgrade requires its own dependency
review and change authority; it is not implied by the original implementation
authorization. No unreviewed provider SDK, floating dependency, or transitive
package is implicitly authorized.

### 15.5 Documentation allowlist

```text
docs/runbooks/V0_3-P2-production-agent-gateway.md
```

The historical `docs/architecture/ADR-005-model-gateway.md` and this
contract are read-only after this freeze. No documentation change may rewrite
historical TASK-012 authority.

### 15.6 Implementation slices

The P2 implementation is divided into three independently reviewable slices.
Each slice may write only paths already present in the amended future
allowlists above; this section does not grant implementation authorization.

#### P2-A_CONFIG_ERROR_FOUNDATION

This slice covers canonical configuration, typed provider configuration,
timeout/retry validation, the three-state capability-resolution foundation,
the ten frozen provider error identities, and safe provider-error metadata
foundation. It does not add the OpenAI SDK, a real provider adapter, a network
call, or strict real-agent route enablement.

#### P2-B_OPENAI_ADAPTER

This slice covers the official `openai` dependency and matching
`backend/uv.lock` entry, `real_gateways.py`, Responses API request/response
mapping, strict `AgentDecision` decoding, frozen provider failure
classification, bounded retry, provider metadata, and mocked transport tests.
Ordinary CI must not call a live provider, and staging/production routes remain
disabled.

#### P2-C_STRICT_COMPOSITION_API

This slice covers `dependencies.py`, `app.py`, `runtime_readiness.py`, and
`planning_agent/api/routes.py` within their frozen allowlist roles. It
implements the three capability states, strict readiness probing, strict
composition evidence, route exposure mapping, and safe API provider-error
projection. Controlled real-provider acceptance remains separately
authorized.

## 16. Forbidden paths and changes

Unless a later contract explicitly amends them, the following are forbidden
for P2 implementation:

```text
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/coefficients/**
backend/src/cold_storage/modules/schemes/**
backend/src/cold_storage/modules/reports/**
backend/src/cold_storage/evaluation/adapter.py
backend/src/cold_storage/evaluation/followup_acceptance.py
backend/src/cold_storage/alembic/**
backend/alembic/**
frontend/**
.github/workflows/**
docs/tasks/**
docs/architecture/ADR-005-model-gateway.md
historical TASK-011/TASK-012 authority, golden, and manifest files
V0_3-P3/**
V0_3-P4/**
V0_3-P5/**
```

The forbidden change classes are:

```text
NO_NEW_ENGINEERING_FORMULA=YES
NO_COEFFICIENT_CHANGE=YES
NO_SCHEME_SCORING_CHANGE=YES
NO_REPORT_APPROVAL_BYPASS=YES
NO_STATUS_MACHINE_REDESIGN=YES
NO_MIGRATION=YES
NO_FRONTEND_REWRITE=YES
NO_PRODUCTION_DEPLOYMENT=YES
NO_RELEASE_PUBLICATION=YES
NO_CREDENTIAL_IN_REPOSITORY=YES
NO_AUTONOMOUS_PROVIDER_ROUTER=YES
NO_P3_OCR_IMPLEMENTATION=YES
NO_P4_WORKBENCH_IMPLEMENTATION=YES
NO_P5_RELEASE_WORK=YES
```

## 17. Required future test matrix

The following tests are required before a separately authorized P2
implementation can be considered complete:

| Area | Required assertion |
| --- | --- |
| Fake local/test | deterministic fake remains explicit and network-free |
| Strict composition | strict mode never constructs or reaches fake fallback |
| Provider selection | explicit provider/model selection only; unknown selection fails closed |
| Configuration | missing/invalid configuration is `NOT_READY` |
| Credentials | missing/invalid credentials have stable classification and no fallback |
| Transport | timeout, connection, rate-limit, 5xx, unavailable classifications |
| Retry | at most one bounded pre-side-effect retry; no post-side-effect retry |
| Structured output | malformed, unknown decision, extra invalid structure rejected |
| Tool registry | unknown tool rejected; registered input schema enforced |
| Inputs | missing/ambiguous required values ask for clarification or fail validation |
| Tool output | deterministic output schema and authority preserved |
| Read tools | auto-execution remains read-only and authorized |
| Calculate tools | deterministic calculation boundary remains authoritative |
| Mutations | explicit confirmation and existing authorization required |
| Confirmation | replay, expiry, stale binding, actor mismatch, argument mismatch rejected |
| Engineering authority | model cannot override numerical results or scheme scoring |
| Lifecycle | session, turn, CAS, idempotency, and project/version binding preserved |
| Audit | provider/model/gateway/request identity and bounded latency recorded |
| Redaction | credentials, headers, tokens, raw provider payloads absent from emissions |
| Readiness | strict route enablement requires provider readiness and composition audit |
| Adapter unit | mocked transport covers success/failure without live network |
| Ordinary CI | no external provider network call by default |

## 18. Separately authorized real-provider acceptance

A later controlled acceptance may use runtime-injected secrets only after a
separate authorization. It must prove, at minimum:

1. the exact production source SHA/tree is bound;
2. the provider and model are explicitly configured;
3. one normal `ANSWER` is decoded;
4. one `ASK_CLARIFICATION` is decoded for missing/ambiguous input;
5. one structured deterministic tool proposal is validated;
6. one mutation reaches explicit confirmation and cannot self-confirm;
7. one provider failure receives the frozen classification;
8. no fake fallback or autonomous second-provider routing occurs;
9. no credential, token, or sensitive model I/O leaks into evidence;
10. strict readiness, lifecycle, persistence, and normalized results remain
    valid.

This acceptance is not ordinary PR CI, is not authorized by this document,
and must not be dispatched, retried, or treated as production operation
without its own gate.

## 19. Non-goals

This definition freeze does not authorize:

- a real provider or SDK;
- provider credentials or secret changes;
- staging/production Agent enablement;
- a multi-model or multi-provider router;
- new engineering formulas, coefficients, thresholds, or scoring;
- autonomous project mutation or report approval;
- frontend changes;
- schema migration or new persistence tables;
- production deployment or release publication;
- P3 OCR work;
- P4 workbench work;
- P5 release work;
- controlled real-provider acceptance execution.

## 20. Governance record

```text
CURRENT_AGENT_STRICT_MODE_STATE=STAGING_PRODUCTION_DISABLED_ROUTES_FAIL_CLOSED_READINESS
CURRENT_FAKE_GATEWAY_SCOPE=LOCAL_TEST_DEMO_EXPLICIT_INJECTION_ONLY
CURRENT_REAL_PROVIDER_ADAPTER_EXISTS=NO
CURRENT_STRUCTURED_TOOL_CALLING_EXISTS=YES
CURRENT_CONFIRMATION_BOUNDARY_EXISTS=YES
PROVIDER_AUTHORITY_RECORD_ID=5323439225
FIRST_CONCRETE_PROVIDER_FROZEN=YES
FIRST_PROVIDER_ID=openai
PROVIDER_ID=openai
PROVIDER_API_SURFACE=OpenAI Responses API
PROVIDER_TRANSPORT_FROZEN=YES
PROVIDER_ENDPOINT_POLICY_FROZEN=YES
PROVIDER_CREDENTIAL_SOURCE_FROZEN=YES
PROVIDER_MODEL_AUTHORITY_FROZEN=YES
PROVIDER_DEPENDENCY_STRATEGY_FROZEN=YES
PROVIDER_TEST_TRANSPORT_FROZEN=YES
PROVIDER_RUNTIME_DEPENDENCY=openai Python package
HTTPX_AS_ALTERNATIVE_PROVIDER_TRANSPORT=NO
IMPLEMENTATION_MAY_SELECT_DIFFERENT_PROVIDER_PACKAGE=NO
CONTRACT_AMENDMENT_REQUIRED_FOR_DIFFERENT_PROVIDER_TRANSPORT_OR_PACKAGE=YES
CONTRACT_AMENDMENT_REQUIRED=YES
MACHINE_READABLE_PROVIDER_FAILURE_CODES_FROZEN=YES
MACHINE_READABLE_PROVIDER_FAILURE_CODE_COUNT=10
MACHINE_READABLE_FAILURE_CODES_FROZEN=YES
FAILURE_CODE_COUNT=10
CAPABILITY_STATES_FROZEN=YES
CAPABILITY_DISABLED_SEMANTICS_FROZEN=YES
CAPABILITY_ENABLED_READY_SEMANTICS_FROZEN=YES
CAPABILITY_ENABLED_NOT_READY_SEMANTICS_FROZEN=YES
GLOBAL_READINESS_MAPPING_FROZEN=YES
ROUTE_EXPOSURE_MAPPING_FROZEN=YES
CAPABILITY_DISABLED_GLOBAL_READINESS=PASS_IF_ALL_OTHER_MANDATORY_READINESS_GATES_PASS
CAPABILITY_DISABLED_ROUTE_EXPOSURE=DISABLED_ROUTE_MATRIX
CAPABILITY_ENABLED_READY_GLOBAL_READINESS=PASS_IF_PROVIDER_AND_ALL_OTHER_MANDATORY_READINESS_GATES_PASS
CAPABILITY_ENABLED_READY_ROUTE_EXPOSURE=REAL_AGENT_ROUTES_ENABLED
CAPABILITY_ENABLED_NOT_READY_GLOBAL_READINESS=FAIL
CAPABILITY_ENABLED_NOT_READY_ROUTE_EXPOSURE=DISABLED_ROUTE_MATRIX
TIMEOUT_CONFIGURATION_AUTHORITY=COLD_STORAGE_AGENT_TIMEOUT_SECONDS
TIMEOUT_CONFIGURATION_TYPE=integer
TIMEOUT_CONFIGURATION_MIN=1
TIMEOUT_CONFIGURATION_MAX=30
STAGING_PRODUCTION_EXPLICIT_REQUIRED_WHEN_AGENT_ENABLEMENT_INTENT_PRESENT=YES
STAGING_PRODUCTION_REQUIRED_WHEN_AGENT_DISABLED=NO
STAGING_PRODUCTION_TIMEOUT_DEFAULT_ALLOWED=NO
TIMEOUT_ZERO_ALLOWED=NO
TIMEOUT_NEGATIVE_ALLOWED=NO
TIMEOUT_NON_INTEGER_ALLOWED=NO
TIMEOUT_NAN_INF_ALLOWED=NO
TIMEOUT_OUT_OF_RANGE_ALLOWED=NO
PROVIDER_NEUTRAL_GATEWAY_FROZEN=YES
NO_SILENT_FAKE_FALLBACK_FROZEN=YES
REAL_PROVIDER_CONFIGURATION_FROZEN=YES
PROVIDER_FAILURE_SEMANTICS_FROZEN=YES
PROVIDER_TIMEOUT_RETRY_BOUNDARY_FROZEN=YES
SENSITIVE_MODEL_IO_POLICY_FROZEN=YES
ENGINEERING_AUTHORITY_SEPARATION_FROZEN=YES
RUNTIME_READINESS_GATE_FROZEN=YES
FUTURE_PRODUCTION_ALLOWLIST_FROZEN=YES
FUTURE_TEST_ALLOWLIST_FROZEN=YES
FUTURE_CONFIG_ALLOWLIST_FROZEN=YES
FUTURE_DEPENDENCY_ALLOWLIST_FROZEN=YES
FORBIDDEN_PATHS_FROZEN=YES
TEST_MATRIX_FROZEN=YES
IMPLEMENTATION_AUTHORIZATION_MAY_DEFINE_NEW_CONTRACT_SEMANTICS=NO
STAGE_ORDER=zone,cooling_load,equipment,power,investment
CONTRACT_FREEZE_SCOPE=CONTRACT_DEFINITION_FREEZE_ONLY
CONTRACT_FREEZE_CHANGED_FILE_COUNT=1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_3-P2-production-agent-gateway-contract.md
P2_IMPLEMENTATION_AUTHORIZED=NO
REAL_PROVIDER_CALL_AUTHORIZED=NO
PROVIDER_CREDENTIAL_CHANGE_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
V03_P3_AUTHORIZED=NO
V03_P4_AUTHORIZED=NO
V03_P5_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 21. V0.3 P2 Implementation Authority Contract Amendment R1

This record closes the five implementation-readiness gaps identified by the
readiness review. It amends contract authority only; it does not authorize
P2 implementation, dependency mutation, credentials, provider calls, or
production enablement.

```text
AMENDMENT_NAME=V0.3 P2 Implementation Authority Contract Amendment R1
AMENDMENT_BASE_MAIN_SHA=9647f4b6ec928e191bce798fc8eb1636ed26b610
AMENDMENT_BASE_MAIN_TREE_SHA=c4a0efb01c05519bee8f5a9e1f419510ebb156fd
AUTHORIZATION_RECORD_ID=5324209900
READINESS_REVIEW_AUTHORIZATION_RECORD_ID=5324154144
READINESS_REVIEW_RESULT_RECORD_ID=5324182799
AUTHORIZATION_SCOPE=CONTRACT_AMENDMENT_ONLY

FINDING_01_CANONICAL_ENVIRONMENT_AUTHORITY=CLOSED
FINDING_02_SAFE_API_ERROR_PROJECTION=CLOSED
FINDING_03_CANONICAL_CONFIGURATION_TEST_OWNER=CLOSED
FINDING_04_AGENT_MAX_RETRIES_SEMANTICS=CLOSED
FINDING_05_OPENAI_SDK_VERSION_POLICY=CLOSED

ENVIRONMENT_MODEL_ALLOWLIST_GAP_CLOSED=YES
AGENT_API_ROUTES_ALLOWLIST_GAP_CLOSED=YES
SETTINGS_TEST_ALLOWLIST_GAP_CLOSED=YES
AGENT_MAX_RETRIES_SEMANTICS_GAP_CLOSED=YES
OPENAI_DEPENDENCY_VERSION_POLICY_GAP_CLOSED=YES

ENVIRONMENT_MODEL_FUTURE_WRITE_AUTHORITY=REGISTER_ONLY_THE_FOUR_P2_CANONICAL_KEYS_AND_PRESERVE_STRICT_UNKNOWN_KEY_REJECTION_LEGACY_POLICY_RESOURCE_IDENTITY_AND_OPENAI_KEY_REDACTION
AGENT_API_ROUTES_FUTURE_WRITE_AUTHORITY=PROJECT_THE_TEN_FROZEN_PROVIDER_FAILURE_CODES_SAFE_MESSAGES_AND_RETRYABLE_BOOLEANS_ONLY
SETTINGS_TEST_FUTURE_WRITE_AUTHORITY=OWN_THE_FOUR_P2_KEYS_STRICT_UNKNOWN_KEY_REJECTION_EXPLICIT_STRICT_CONFIGURATION_AND_TIMEOUT_RETRY_SHAPE_TESTS

AGENT_MAX_RETRIES_CONFIGURATION_AUTHORITY=COLD_STORAGE_AGENT_MAX_RETRIES
AGENT_MAX_RETRIES_TYPE=integer
AGENT_MAX_RETRIES_MIN=0
AGENT_MAX_RETRIES_MAX=1
AGENT_MAX_RETRIES_ALLOWED_VALUES=0,1
AGENT_MAX_RETRIES_STRICT_EXPLICIT_REQUIRED_WHEN_AGENT_ENABLEMENT_INTENT_PRESENT=YES
AGENT_MAX_RETRIES_STRICT_REQUIRED_WHEN_AGENT_DISABLED=NO
AGENT_MAX_RETRIES_STRICT_DEFAULT_ALLOWED=NO
AGENT_MAX_RETRIES_ZERO_ALLOWED=YES
AGENT_MAX_RETRIES_NEGATIVE_ALLOWED=NO
AGENT_MAX_RETRIES_NON_INTEGER_ALLOWED=NO
AGENT_MAX_RETRIES_NAN_INF_ALLOWED=NO
AGENT_MAX_RETRIES_OUT_OF_RANGE_ALLOWED=NO
MAX_PROVIDER_RETRIES=1
MAX_PROVIDER_ATTEMPTS=2
OPENAI_SDK_MAX_RETRIES=0

OPENAI_DEPENDENCY_DIRECT_PACKAGE=openai
OPENAI_DEPENDENCY_VERSION_POLICY=EXACT_PIN
UV_LOCK_EXACT_RESOLUTION_REQUIRED=YES
PYPROJECT_FLOATING_SPECIFIER_ALLOWED=NO
PYPROJECT_WILDCARD_ALLOWED=NO
PRERELEASE_ALLOWED=NO
YANKED_RELEASE_ALLOWED=NO
GIT_REF_DEPENDENCY_ALLOWED=NO
DIRECT_URL_DEPENDENCY_ALLOWED=NO
ALTERNATIVE_PROVIDER_PACKAGE_ALLOWED=NO
HTTPX_AS_PROVIDER_TRANSPORT_ALLOWED=NO
IMPLEMENTATION_MAY_CHANGE_VERSION_POLICY=NO

IMPLEMENTATION_SLICE_A=P2-A_CONFIG_ERROR_FOUNDATION
IMPLEMENTATION_SLICE_B=P2-B_OPENAI_ADAPTER
IMPLEMENTATION_SLICE_C=P2-C_STRICT_COMPOSITION_API

CONTRACT_AMENDMENT_CHANGED_FILE_COUNT=1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_3-P2-production-agent-gateway-contract.md
P2_IMPLEMENTATION_EXECUTED=NO
OPENAI_DEPENDENCY_ADDED=NO
OPENAI_CREDENTIAL_CHANGED=NO
OPENAI_REAL_API_CALL_EXECUTED=NO
PRODUCTION_AGENT_ENABLEMENT=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 22. V0.3 P2 Implementation Authority Contract Amendment Correction R2

This record closes the disabled-versus-strict-configuration requirement
identified by the independent review. It clarifies the existing contract
without authorizing P2 implementation, dependency mutation, credentials,
provider calls, or production enablement.

```text
AMENDMENT_NAME=V0.3 P2 Implementation Authority Contract Amendment Correction R2
SOURCE_REVIEW_ID=4957909268
PREVIOUS_HEAD_SHA=635548e32d86eb76218acde82d83f58166930ee6
BLOCKER=DISABLED_VS_STRICT_AGENT_CONFIG_REQUIREMENT
AUTHORIZATION_SCOPE=CONTRACT_AMENDMENT_ONLY

AGENT_ENABLEMENT_INTENT_SEMANTICS_FROZEN=YES
AGENT_ENABLEMENT_INTENT_TRIGGER=PROVIDER_OR_MODEL_SUPPLIED
ONLY_PROVIDER_OR_MODEL_SELECTION_CREATES_ENABLEMENT_INTENT=YES
OPENAI_API_KEY_EXISTENCE_IMPLIES_ENABLEMENT=NO
OPENAI_PACKAGE_EXISTENCE_IMPLIES_ENABLEMENT=NO
TIMEOUT_CONFIG_EXISTENCE_IMPLIES_ENABLEMENT=NO
RETRY_CONFIG_EXISTENCE_IMPLIES_ENABLEMENT=NO
NETWORK_AVAILABILITY_IMPLIES_ENABLEMENT=NO

DISABLED_AGENT_OPTIONAL_CONFIG_SEMANTICS_FROZEN=YES
DISABLED_PROVIDER_REQUIRED=NO
DISABLED_MODEL_REQUIRED=NO
DISABLED_TIMEOUT_REQUIRED=NO
DISABLED_MAX_RETRIES_REQUIRED=NO
DISABLED_OPENAI_CREDENTIAL_REQUIRED=NO
DISABLED_AGENT_CONFIG_ABSENCE_FAILS_GLOBAL_READINESS=NO
DISABLED_CAPABILITY_STATE=AGENT_CAPABILITY_DISABLED
DISABLED_GLOBAL_READINESS=PASS_IF_ALL_OTHER_MANDATORY_READINESS_GATES_PASS
DISABLED_ROUTE_EXPOSURE=DISABLED_ROUTE_MATRIX
DISABLED_REAL_PROVIDER_CONSTRUCTED=NO
DISABLED_FAKE_PROVIDER_CONSTRUCTED_ON_STRICT_ROUTE=NO

ENABLED_AGENT_COMPLETE_CONFIG_REQUIREMENT_FROZEN=YES
ENABLED_PROVIDER_REQUIRED=YES
ENABLED_MODEL_REQUIRED=YES
ENABLED_TIMEOUT_REQUIRED=YES
ENABLED_MAX_RETRIES_REQUIRED=YES
ENABLED_PROVIDER_CREDENTIAL_REQUIRED=YES_WHEN_PROVIDER_OPENAI
ENABLED_NOT_READY_CAPABILITY_STATE=AGENT_CAPABILITY_ENABLED_NOT_READY
ENABLED_NOT_READY_GLOBAL_READINESS=FAIL
ENABLED_NOT_READY_ROUTE_EXPOSURE=DISABLED_ROUTE_MATRIX
ENABLED_NOT_READY_REAL_AGENT_ROUTES_REACHABLE=NO
ENABLED_NOT_READY_FAKE_FALLBACK=NO

TIMEOUT_CONDITIONAL_STRICT_REQUIREMENT_FROZEN=YES
TIMEOUT_CONFIGURATION_AUTHORITY=COLD_STORAGE_AGENT_TIMEOUT_SECONDS
TIMEOUT_TYPE=integer
TIMEOUT_MIN=1
TIMEOUT_MAX=30
STAGING_PRODUCTION_EXPLICIT_REQUIRED_WHEN_AGENT_ENABLEMENT_INTENT_PRESENT=YES
STAGING_PRODUCTION_REQUIRED_WHEN_AGENT_DISABLED=NO
STAGING_PRODUCTION_DEFAULT_ALLOWED=NO

RETRY_CONDITIONAL_STRICT_REQUIREMENT_FROZEN=YES
RETRY_CONFIGURATION_AUTHORITY=COLD_STORAGE_AGENT_MAX_RETRIES
RETRY_TYPE=integer
RETRY_MIN=0
RETRY_MAX=1
RETRY_ALLOWED_VALUES=0,1
AGENT_MAX_RETRIES_STRICT_EXPLICIT_REQUIRED_WHEN_AGENT_ENABLEMENT_INTENT_PRESENT=YES
AGENT_MAX_RETRIES_STRICT_REQUIRED_WHEN_AGENT_DISABLED=NO
AGENT_MAX_RETRIES_STRICT_DEFAULT_ALLOWED=NO
MAX_PROVIDER_RETRIES=1
MAX_PROVIDER_ATTEMPTS=2
OPENAI_SDK_MAX_RETRIES=0

CAPABILITY_DISABLED_SEMANTICS_PRESERVED=YES
CAPABILITY_ENABLED_NOT_READY_SEMANTICS_PRESERVED=YES
CAPABILITY_ENABLED_READY_SEMANTICS_PRESERVED=YES
GLOBAL_READINESS_MAPPING_FROZEN=YES
ROUTE_EXPOSURE_MAPPING_FROZEN=YES
PRIOR_R1_FINDING_COUNT=5
PRIOR_R1_FINDINGS_REMAIN_CLOSED=YES
BLOCKER_CLOSED=YES

P2_IMPLEMENTATION_EXECUTED=NO
OPENAI_DEPENDENCY_ADDED=NO
OPENAI_CREDENTIAL_CHANGED=NO
OPENAI_REAL_API_CALL_EXECUTED=NO
PRODUCTION_AGENT_ENABLEMENT=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
