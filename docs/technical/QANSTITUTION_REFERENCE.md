# QAnstitution Reference

**File:** `qanstitution.yaml`  
**Purpose:** Executable quality law for Entroping  
**Version:** 4.1

`qanstitution.yaml` is the canonical policy filename. `entroping.yaml` and
`entroping-policy.yaml` are not compatibility aliases.

## 1. Design Intent

The QAnstitution defines what a project must prove before its API behavior is trusted.

It is not a prose policy document. It is a validated configuration file that Entroping loads, merges, and injects into runtime execution.

If you are editing your first policy, start with
[QANSTITUTION_FIRST_HOUR.md](../user/QANSTITUTION_FIRST_HOUR.md). This reference
is the full schema and advanced behavior.

## Authoring Schema

The committed JSON Schema lives at
[qanstitution.schema.json](qanstitution.schema.json). It is generated from the
Pydantic runtime model with:

```bash
uv run python scripts/update_qanstitution_schema.py
```

VS Code and YAML language server users can rely on the checked-in
`.vscode/settings.json` mapping, which associates `qanstitution.yaml` and
`**/qanstitution.yaml` with that schema:

```json
{
  "yaml.schemas": {
    "./docs/technical/qanstitution.schema.json": [
      "qanstitution.yaml",
      "**/qanstitution.yaml"
    ]
  }
}
```

## 1A. IDE Authoring Support Evaluation (Issue #597)

The current minimum viable IDE path is schema-only, offline authoring:

- Schema autocomplete and structural linting from
  `docs/technical/qanstitution.schema.json`.
- Runtime authority from `entroping doctor`, `entroping report policy`, and the
  usual execution commands.
- No hosted services, no required API keys, and no local provider setup.

This means IDEs that consume YAML schemas can give immediate authoring value
without runtime or network requirements.

### VS Code and JetBrains

- VS Code:
  the checked-in `.vscode/settings.json` mapping is available for local and
  versioned policy authoring.
- JetBrains:
  the built-in YAML schema support can consume the same `docs/technical/qanstitution.schema.json`
  file and map it to `qanstitution.yaml`-style files.

### Decision

Entroping will treat schema-based authoring support as the Apache-2.0 core
experience for now. A dedicated IDE extension (run/test workflow integration,
advanced policy linting, or cross-editor command surfaces) is out of core scope
until a separate roadmap item requests it.

For today, the first useful IDE workflow is:

1. Enable schema-based completion for `qanstitution.yaml`.
2. Edit policy with immediate feedback from schema constraints.
3. Run `entroping doctor --ci` or `entroping report policy` before commit.

The schema is an editor and review aid; runtime validation remains authoritative:
`entroping doctor`, `entroping run`, and Architect commands load the effective
policy through the Pydantic model and config loader before trusting it.

To inspect the effective local policy after imports and local overrides, run:

```bash
entroping report policy --output md
```

Use `--output json` when a downstream review tool needs the versioned
`entroping.effective-policy-report.v1` payload at
`reports/effective-policy.json`.

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

gate_groups:
  api_baseline:
    description: "Reusable baseline checks for every API route"
    gates:
      - id: "no_server_errors"
        condition: "true"
        gate: "status < 500"
        enforcement: "block"
      - id: "global_latency"
        condition: "true"
        gate: "duration < 2000"
        enforcement: "block"

gates:
  - group: "api_baseline"
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
  protected_environments:
    - "prod"
    - "production"
    - "protected"
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
| `gate_groups` | No | Reusable local gate collections expanded into top-level gates |
| `gates` | Yes | Runtime governance assertions |
| `ignore_failures` | No | Temporary known-failure exceptions |
| `settings` | No | Runtime defaults |

## QAnstitution Schema Compatibility

`qanstitution.yaml` remains the only supported policy filename. Names such as
`entroping.yaml` and `entroping-policy.yaml` are intentionally not compatibility
aliases.

The top-level `version` field is policy metadata for humans, governance packs,
and future migration notes. It is not the Python package version, not a PEP 440
release marker, and not the JSON Schema `$id`.

Current compatibility rules:

- Supported explicit marker for the v4.1 policy shape is `version: "4.1"`.
- Absence of `version` is accepted for existing legacy files that already match
  the v4.1 shape. Entroping does not rewrite those files automatically.
- Older markers such as `4.0` fail closed until a reviewed migration exists.
- Future or unknown markers such as `4.2` or `5.0` fail closed so a newer
  policy file is not silently enforced by an older Entroping binary.
- Any non-empty `version` not in the supported set is rejected during config load
  and `entroping doctor` with a migration-focused error message.
- Unknown top-level fields continue to fail validation through the Pydantic
  model and checked-in JSON Schema.
- Additive optional fields can stay within the current policy shape when they
  include model updates, regenerated `qanstitution.schema.json`, examples, and
  tests.
- Removing, renaming, or making a field required needs a migration issue,
  migration note, examples for old and new shapes, and `doctor` guidance that
  fails clearly before runtime execution.
- Future-policy files that cannot be validated must fail closed. Do not silently
  ignore unknown governance fields.

Migration helpers, if they are needed, belong in reviewed one-shot tooling or a
future explicitly scoped `config` workflow. They must never run implicitly from
`entroping run`, `entroping doctor`, or config loading. Runtime commands only
validate the policy and return clear migration guidance.

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

Reusable policy-pack structure is documented in
[POLICY_PACK_LAYOUT.md](POLICY_PACK_LAYOUT.md). Policy packs are currently
normal local QAnstitution imports plus reviewable metadata and examples, not a
separate runtime format.
Use `entroping config vendor-policy-pack --pack <path> [--name <dir>]` to copy a
reviewed local pack under `policy-packs/`, validate its manifest and entrypoint,
and append the local import without fetching from a remote registry.
Use `entroping config test-policy-pack --pack <path> [--output text|json]`
before vendoring or publishing a pack when you need local pass/fail evidence
without modifying the consumer project.

Organization import controls are defined in
[ADR-0011-organization-qanstitution-import-controls.md](https://github.com/sakibshuvo/Entroping/blob/main/decisions/ADR-0011-organization-qanstitution-import-controls.md).
Organization imports still compile into the same effective local policy; they
must preserve provenance, final-gate behavior, and offline/local-first
validation before any remote registry behavior is implemented.

Example imported final rule:

```yaml
gates:
  - id: "no_5xx_in_smoke"
    condition: "tags contains 'smoke'"
    gate: "status < 500"
    enforcement: "block"
    final: true
```

## 8. Gate Groups

Gate groups reduce repetition inside a local QAnstitution file while preserving
the deterministic runtime model. They are authoring-time structure only:
Entroping expands them into ordinary `GateRule` entries before gate matching,
injection, and Hurl execution.

```yaml
gate_groups:
  latency:
    description: "Latency checks shared by local suites"
    gates:
      - id: "smoke_latency"
        condition: "tags contains 'smoke'"
        gate: "duration < 500"
        enforcement: "block"
  api_baseline:
    groups:
      - "latency"
    gates:
      - id: "no_server_errors"
        condition: "true"
        gate: "status < 500"
        enforcement: "block"

gates:
  - group: "api_baseline"
  - id: "request_id"
    condition: "true"
    gate: 'header "X-Request-Id" exists'
    enforcement: "warn"
```

Expansion rules:

- Top-level `gates` may contain ordinary gates or `{ group: "<name>" }`
  references.
- A group expands nested `groups` first, in listed order, then its own `gates`.
- Unknown group references and group cycles fail QAnstitution validation before
  runtime execution.
- Imported files expand their local groups before effective-policy merging, so
  imported `final: true` gates still cannot be overridden by local gates.
- `entroping report policy` includes the expanded gate and its source group so
  reusable authoring does not erase review provenance.

Gate groups do not add a remote registry, expression language, conditional
include system, or second runtime policy format.

## 9. Agents

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
    input_cost_per_1m_tokens_usd: 0.25
    output_cost_per_1m_tokens_usd: 1.25
    temperature: 0.1
    max_tokens: 4096
```

`api_base` must be an `http` or `https` URL without userinfo, query
parameters, or fragments. `api_key_env` must be a valid environment variable
name. Optional `input_cost_per_1m_tokens_usd` and
`output_cost_per_1m_tokens_usd` are local estimation hints used in value-free
Architect run evidence when providers return token usage. No API keys in qanstitution.yaml.

The runtime prompt is composed from:

1. Agent persona Markdown.
2. Effective QAnstitution.
3. User task.
4. Relevant source context.

Agent output must be parsed into structured data and validated before writing files.

Model IDs are provider-specific and change over time. Treat the examples as routing placeholders and verify current access before committing a default.

Current role behavior:

- `architect build --prompt` defaults to the Builder persona.
- `architect build --agent breaker --prompt` selects the Breaker persona,
  model route, and automatically marks generated tests with the `breaker` tag.
- `architect audit --focus auditor` selects the Auditor persona and model route
  for provider-backed review findings. Auditor does not edit files.

Deterministic OpenAPI negative-path generation does not add a new
`qanstitution.yaml` section in v4.1. Instead, `architect build --new` writes
ordinary Hurl files with `negative`, category, `negative_category`, `severity`,
and `safety` metadata. Suites can opt into a category with tags, and gates can
target category or severity with conditions such as
`meta.negative_category == 'boundary-values'` or
`meta.severity == 'high'`; auth-negative files use category `invalid-auth`.
Product runtime remains deterministic: generated negative tests must be
committed/reviewed before `entroping run`, and
`entroping run` does not call LLM providers or perform hidden fuzzing.

Current implementation note: `entroping config list` prints this routing metadata,
and `entroping config set --agent <builder|auditor|breaker> --model <provider/model>`
updates only the selected agent model. If the selected persona source is missing,
`config set` creates a local Markdown template after validating that the path stays
inside the project and does not use symlinks. The model value is validated as routing
metadata, not a credential; empty values, control characters, and API-key-shaped
strings are rejected. Optional `api_base` and `api_key_env` values are also
printed by `config list` when present, while the actual environment value is
never printed.

## 10. Gates

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

## 11. Condition DSL

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

## 12. Gate Syntax

The `gate` field should use Hurl-compatible assertion syntax:

```yaml
gate: "duration < 2000"
gate: "header \"X-Request-Id\" exists"
gate: "jsonpath \"$.error\" not exists"
gate: "status < 500"
```

The gate injector is responsible for translating these into the correct Hurl assertion placement for each execution copy.

Current implementation note: gate matching evaluates `true`, tags, metadata, and shallow parsed Hurl request method/path/URL values. Injection writes temporary execution copies and adds `# entroping-gate: <rule_id> enforcement=<level>` comments next to injected assertions so runner and report layers can distinguish `block`, `warn`, and `audit_only` gates without mutating source `.hurl` files.

## 13. Enforcement Behavior

| Enforcement | Behavior |
| --- | --- |
| `block` | Failing gate causes non-zero exit in normal and CI runs |
| `warn` | Failing gate is reported but does not fail the run |
| `audit_only` | Gate is evaluated or listed for visibility without blocking |

Reports must show enforcement level and rule ID.

## 14. Known Failures

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

Current runtime semantics:

- `test` matches the exact project-relative Hurl source path, for example `tests/payments/refund.hurl`.
- `rule_id` matches the exact QAnstitution gate ID.
- A matching active exception skips only that Entroping-injected gate in the temporary execution copy.
- An active exception that targets a selected test but does not match any injected gate fails before Hurl execution with issue, test, and rule evidence.
- Exceptions for tests outside the selected run subset are not evaluated for that subset.
- Source `.hurl` files are never modified.
- Authored Hurl assertions, unrelated QAnstitution gates, and unrelated Hurl failures still run and still fail normally.
- JSON, JUnit, and HTML run reports include only applied exceptions with test path, rule ID, issue ID, expiry, and reason.
- `expires` must use `YYYY-MM-DD`; invalid or expired exceptions fail before Hurl execution.

## 15. Settings

```yaml
settings:
  timeout: 30000
  parallel_workers: 4
  follow_redirects: true
  retry: 2
  protected_environments:
    - "prod"
    - "production"
    - "protected"
```

Settings are deterministic runtime defaults. Command-line flags and environment
variables can override them where documented.

`protected_environments` controls which `entroping run --env <name>` values are
treated as protected by the production-safety preflight. The default protected
names are `prod`, `production`, and `protected`. In a protected run, mutating
Hurl request methods (`POST`, `PUT`, `PATCH`, and `DELETE`) fail before Hurl
execution unless the selected test or suite declares reviewed safety metadata:

```hurl
# entroping: tags=smoke
# entroping: safety=idempotent

POST {{base_url}}/maintenance/reindex
HTTP 202
```

Accepted safety values are:

| Value | Protected-run behavior |
| --- | --- |
| `read-only` | Allow a mutating-looking request that is reviewed as read-only. |
| `idempotent` | Allow a reviewed repeatable mutation. |
| `teardown-backed` | Allow a mutation with committed cleanup or reset safety. |
| `destructive` | Always block in protected environments. |

A named suite can also set `protected: true` and `safety: <value>` in
`suites/<name>.yaml`. Test-level safety metadata wins over suite defaults, so a
test marked `destructive` remains blocked even in a suite whose default safety is
`idempotent`.

## 16. Redaction Roadmap

Traffic and prompt redaction are currently handled by built-in redactors and
review reports, not a `qanstitution.yaml` field. Do not add `redaction` to the
current policy file; the JSON Schema and Pydantic model intentionally reject
unknown top-level keys.

Future policy-backed redaction rules should cover:

- Traffic persistence.
- Logs.
- Reports.
- LLM context preparation.

Raw secrets should not be persisted or sent to model providers. Adding a
policy-backed redaction section requires a Pydantic model update, regenerated
`qanstitution.schema.json`, examples, and tests in the same change.

## 17. External Business Truth

Entroping should not force teams to abandon Jira, Notion, Linear, or monday.com. Treat those systems as business truth and Entroping as the executable cache.

For solo or small-team use, link tests manually:

```hurl
# entroping: tags=regression,auth
# entroping: story_id=NOTION-101
# entroping: doc_url=https://notion.so/workspace/task-101
```

For larger teams, a sync script can generate `docs/stories/*.md` from the external system. The generated Markdown gives the Architect local context without making the LLM query Jira or Notion on every run.

## 18. Hurl Metadata Example

```hurl
# entroping: tags=smoke,checkout,critical
# entroping: story_id=CHK-001
# entroping: owner=payments
# entroping: doc_url=https://notion.so/workspace/CHK-001
# entroping: safety=read-only

GET {{base_url}}/checkout/{{checkout_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == "{{checkout_id}}"
```

QAnstitution conditions can match tags and metadata from these comments. Because they are comments, plain Hurl ignores them.

## 19. Validation Rules

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
