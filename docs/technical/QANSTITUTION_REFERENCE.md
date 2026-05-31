# QAnstitution Reference

**File:** `qanstitution.yaml`  
**Purpose:** Executable quality law for Entroping  
**Version:** 4.1

## 1. Design Intent

The QAnstitution defines what a project must prove before its API behavior is trusted.

It is not a prose policy document. It is a validated configuration file that Entroping loads, merges, and injects into runtime execution.

If you are editing your first policy, start with
[QANSTITUTION_FIRST_HOUR.md](../user/QANSTITUTION_FIRST_HOUR.md). This reference
is the full schema and advanced behavior.

## 2. Minimal Example

```yaml
project: "checkout-api"
version: "4.1"

sources:
  spec: "./openapi.json"

gates:
  - id: "no_server_errors"
    description: "Fail when an endpoint returns a server error"
    condition: "true"
    gate: "status < 500"
    enforcement: "block"
  - id: "global_latency"
    description: "Every endpoint should respond within two seconds"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
  - id: "request_id_header"
    description: "Warn when a response is missing a request ID header for debugging"
    condition: "true"
    gate: 'header "X-Request-Id" exists'
    enforcement: "warn"
```

## 3. Full Example

```yaml
project: "checkout-api"
version: "4.1"
description: "Runtime quality law for checkout"

sources:
  spec: "./openapi.json"
  stories: "./docs/stories"
  traffic: ".entroping/state.db"
  graph: "./schema.graphql"
  types: "./specs/typespec"

dependencies:
  - name: "auth-service"
    spec: "../auth-service/openapi.json"
  - name: "payments"
    spec: "https://raw.githubusercontent.com/acme/payments/main/openapi.json"

imports:
  - "./rules/security.yaml"
  - "./rules/performance.yaml"
  - "https://raw.githubusercontent.com/acme/governance/main/common.yaml"

agents:
  builder:
    source: "agents/builder.md"
    model: "anthropic/<builder-model>"
    temperature: 0.1
    max_tokens: 4096
  auditor:
    source: "agents/auditor.md"
    model: "openai/<auditor-model>"
    temperature: 0.0
    max_tokens: 4096
  breaker:
    source: "agents/breaker.md"
    model: "deepseek/<breaker-model>"
    temperature: 0.7
    max_tokens: 4096

gates:
  - id: "global_latency"
    description: "All API responses must complete under 2 seconds"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
  - id: "smoke_latency"
    description: "Smoke tests must stay very fast"
    condition: "tags contains 'smoke'"
    gate: "duration < 500"
    enforcement: "block"
  - id: "security_header"
    description: "API responses must include a request ID"
    condition: "path startswith '/api'"
    gate: 'header "X-Request-Id" exists'
    enforcement: "warn"

ignore_failures:
  - test: "tests/payments/refund.hurl"
    rule_id: "global_latency"
    issue_id: "PAY-1024"
    expires: "2026-12-31"
    reason: "Temporary database index migration"

settings:
  timeout: 30000
  parallel_workers: 4
  follow_redirects: true
  retry: 2
  state_retention:
    max_size_mb: 1024
    max_age_days: 30
  env_defaults:
    base_url: "http://localhost:8080"

redaction:
  headers:
    - authorization
    - cookie
    - x-api-key
  json_fields:
    - password
    - token
    - access_token
    - refresh_token
```

## 4. Top-Level Fields

| Field | Required | Description |
| --- | --- | --- |
| `project` | Yes | Human-readable project or service name |
| `version` | Recommended | QAnstitution or Entroping version marker |
| `description` | No | Short purpose statement |
| `sources` | Recommended | Pointers to specs, stories, traffic DB, schemas |
| `dependencies` | No | Cross-service spec pointers used for mocks and compatibility checks |
| `imports` | No | Local or remote governance files |
| `agents` | No for run, yes for AI | Builder/Auditor/Breaker routing |
| `gates` | Yes | Runtime governance assertions |
| `ignore_failures` | No | Temporary known-failure exceptions |
| `settings` | No | Runtime defaults |
| `redaction` | No | Traffic and log redaction settings |

## 5. Sources

```yaml
sources:
  spec: "./openapi.json"
  stories: "./docs/stories"
  traffic: ".entroping/state.db"
  graph: "./schema.graphql"
  types: "./specs/typespec"
```

| Source | Purpose |
| --- | --- |
| `spec` | OpenAPI input for generation and drift |
| `stories` | Markdown product stories for traceability |
| `traffic` | SQLite traffic store used by Eye workflows |
| `graph` | GraphQL schema input |
| `types` | TypeSpec or future schema input |

## 6. Dependencies

Dependencies describe provider services that this service consumes. They are not governance imports; they are source context for Architect generation, mock validation, and cross-service compatibility checks.

```yaml
dependencies:
  - name: "auth-service"
    spec: "../auth-service/openapi.json"
  - name: "payments"
    spec: "https://raw.githubusercontent.com/acme/payments/main/openapi.json"
```

Rules:

- `name` is the logical service name used by reports, maps, and `freeze --mock`.
- `spec` can be a local path or HTTP(S) URL.
- Dependency specs must be read-only inputs. Entroping should not write into another service repo unless the user explicitly runs there.
- If dependency specs cannot be loaded, Architect commands should warn or fail depending on whether the task needs that dependency.

## 7. Imports

Imports allow federated governance:

```yaml
imports:
  - "./rules/security.yaml"
  - "../central-quality/performance.yaml"
  - "https://raw.githubusercontent.com/acme/governance/main/security.yaml"
```

Rules:

- Local paths resolve relative to the file that declares them.
- HTTP(S) imports require timeouts.
- Imported files must pass schema validation.
- Imported gates merge before local gates.
- Local gate IDs override imported gate IDs unless the imported gate has `final: true`.

Phase 1A implementation note: local imports are supported first and must resolve under the root `qanstitution.yaml` directory. Remote HTTP(S) imports and broader local trust roots remain part of the architecture contract but are rejected by the current loader so `doctor` and local validation never make network calls.

Example imported final rule:

```yaml
gates:
  - id: "no_5xx_in_smoke"
    condition: "tags contains 'smoke'"
    gate: "status < 500"
    enforcement: "block"
    final: true
```

## 8. Agents

Agents map logical roles to Markdown persona files and models:

```yaml
agents:
  builder:
    source: "agents/builder.md"
    model: "anthropic/<builder-model>"
    temperature: 0.1
  auditor:
    source: "agents/auditor.md"
    model: "openai/<auditor-model>"
    temperature: 0.0
  breaker:
    source: "agents/breaker.md"
    model: "deepseek/<breaker-model>"
    temperature: 0.7
```

Local OpenAI-compatible providers can add non-secret endpoint metadata:

```yaml
agents:
  builder:
    source: "agents/builder.md"
    model: "openai/<local-qwen-model>"
    api_base: "http://127.0.0.1:8000/v1"
    api_key_env: "ENTROPING_OMLX_API_KEY"
    temperature: 0.1
    max_tokens: 4096
```

`api_base` must be an `http` or `https` URL without userinfo, query
parameters, or fragments. `api_key_env` must be a valid environment variable
name. No API keys in qanstitution.yaml.

The runtime prompt is composed from:

1. Agent persona Markdown.
2. Effective QAnstitution.
3. User task.
4. Relevant source context.

Agent output must be parsed into structured data and validated before writing files.

Model IDs are provider-specific and change over time. Treat the examples as routing placeholders and verify current access before committing a default.

Current implementation note: `entroping config list` prints this routing metadata,
and `entroping config set --agent <builder|auditor|breaker> --model <provider/model>`
updates only the selected agent model. If the selected persona source is missing,
`config set` creates a local Markdown template after validating that the path stays
inside the project and does not use symlinks. The model value is validated as routing
metadata, not a credential; empty values, control characters, and API-key-shaped
strings are rejected. Optional `api_base` and `api_key_env` values are also
printed by `config list` when present, while the actual environment value is
never printed.

## 9. Gates

A gate is a policy assertion that can be injected into matching Hurl executions.

```yaml
gates:
  - id: "global_latency"
    description: "Every endpoint must respond within 2 seconds"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
```

| Field | Required | Description |
| --- | --- | --- |
| `id` | Yes | Stable rule ID |
| `description` | Recommended | Human explanation |
| `condition` | Yes | Match expression |
| `gate` | Yes | Hurl assertion syntax |
| `enforcement` | Yes | `block`, `warn`, or `audit_only` |
| `final` | No | Prevent local overrides when imported |

## 10. Condition DSL

Initial supported expressions:

```text
true
tags contains 'smoke'
method == 'POST'
path startswith '/api/v1'
path contains '/checkout'
url contains 'payments'
meta.story_id == 'CHK-001'
```

The first implementation should keep this small and deterministic. Compound expressions such as `and` and `or` can be added later after tests exist.

The parser must validate the supported condition syntax when `qanstitution.yaml` is loaded. Invalid condition strings are configuration errors, not runtime warnings.

## 11. Gate Syntax

The `gate` field should use Hurl-compatible assertion syntax:

```yaml
gate: "duration < 2000"
gate: "header \"X-Request-Id\" exists"
gate: "jsonpath \"$.error\" not exists"
gate: "status < 500"
```

The gate injector is responsible for translating these into the correct Hurl assertion placement for each execution copy.

Current implementation note: gate matching evaluates `true`, tags, metadata, and shallow parsed Hurl request method/path/URL values. Injection writes temporary execution copies and adds `# entroping-gate: <rule_id> enforcement=<level>` comments next to injected assertions so runner and report layers can distinguish `block`, `warn`, and `audit_only` gates without mutating source `.hurl` files.

## 12. Enforcement Behavior

| Enforcement | Behavior |
| --- | --- |
| `block` | Failing gate causes non-zero exit in normal and CI runs |
| `warn` | Failing gate is reported but does not fail the run |
| `audit_only` | Gate is evaluated or listed for visibility without blocking |

Reports must show enforcement level and rule ID.

## 13. Known Failures

Known failures prevent temporary issues from becoming invisible.

```yaml
ignore_failures:
  - test: "tests/payments/refund.hurl"
    rule_id: "global_latency"
    issue_id: "PAY-1024"
    expires: "2026-12-31"
    reason: "Temporary database index migration"
```

Required fields:

- `test`
- `rule_id`
- `issue_id`
- `expires`
- `reason`

Expired exceptions must fail validation before execution. If a compatibility mode is ever added, expired exceptions must still be reported as blocking configuration errors, not silently ignored.

## 14. Settings

```yaml
settings:
  timeout: 30000
  parallel_workers: 4
  follow_redirects: true
  retry: 2
  state_retention:
    max_size_mb: 1024
    max_age_days: 30
  env_defaults:
    base_url: "http://localhost:8080"
```

Settings are defaults. Command-line flags and environment variables can override them where documented.

`state_retention` controls `.entroping/state.db` growth for traffic capture, baselines, and run history.

## 15. Redaction

```yaml
redaction:
  headers:
    - authorization
    - cookie
    - x-api-key
  json_fields:
    - password
    - token
    - access_token
```

Redaction applies to:

- Traffic persistence.
- Logs.
- Reports.
- LLM context preparation.

Raw secrets should not be persisted or sent to model providers.

## 16. External Business Truth

Entroping should not force teams to abandon Jira, Notion, Linear, or monday.com. Treat those systems as business truth and Entroping as the executable cache.

For solo or small-team use, link tests manually:

```hurl
# entroping: tags=regression,auth
# entroping: story_id=NOTION-101
# entroping: doc_url=https://notion.so/workspace/task-101
```

For larger teams, a sync script can generate `docs/stories/*.md` from the external system. The generated Markdown gives the Architect local context without making the LLM query Jira or Notion on every run.

## 17. Hurl Metadata Example

```hurl
# entroping: tags=smoke,checkout,critical
# entroping: story_id=CHK-001
# entroping: owner=payments
# entroping: doc_url=https://notion.so/workspace/CHK-001

GET {{base_url}}/checkout/{{checkout_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == "{{checkout_id}}"
```

QAnstitution conditions can match tags and metadata from these comments. Because they are comments, plain Hurl ignores them.

## 18. Validation Rules

The config loader should reject:

- Missing required fields.
- Duplicate gate IDs after merge.
- Invalid enforcement values.
- Invalid condition syntax.
- Invalid remote import URLs.
- Expired known failures.
- Agent source paths that do not exist when an AI command needs them.
- Dependency spec paths that are required by the current command but cannot be loaded.
- Unsafe output or import paths.

Validation failures must identify the field path and file involved.
