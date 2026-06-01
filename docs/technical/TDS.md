# Entroping Technical Design Specification

**System:** Entroping Core  
**Version:** 4.1 Stable  
**Architecture:** Hexagonal, local-first, Git-native  
**Runtime Principle:** Python orchestrates. Hurl enforces.

## 1. Technical Goals

Entroping must provide a reliable local CLI that can:

- Parse and validate governance policy from `qanstitution.yaml`.
- Generate and maintain valid Hurl tests with AI assistance.
- Observe HTTP/S traffic through mitmproxy and persist redacted sessions.
- Execute tests through the external Rust `hurl` binary.
- Inject policy gates at runtime without mutating source files.
- Produce deterministic reports for humans and CI.

The implementation should prefer boring, inspectable, strongly typed modules over clever orchestration.

## 2. Technology Stack

| Layer | Technology | Requirement |
| --- | --- | --- |
| Language | Python 3.12 or 3.13 | Strict typing for application code; CI proves Python 3.12 and 3.13, while 3.12 remains the syntax and mypy floor |
| CLI | Typer + Rich | Human-friendly commands and errors |
| TUI | Textual/Rich | `studio` local mission control |
| Domain schemas | Pydantic v2 | Validated immutable-ish data models |
| State | SQLite + SQLModel | Local traffic/session database under `.entroping/`; SQLModel provides typed persistence over the local SQLite file |
| Execution | Hurl Rust binary | Invoked through `subprocess`, never reimplemented |
| Proxy | mitmproxy | Native addon for `watch` traffic capture |
| AI | LiteLLM | Provider abstraction for all model calls |
| Agent graph | Small typed in-process router for MVP | Builder/Auditor/Breaker task routing without adding orchestration dependency early |
| Packaging | uv, then Nuitka/Homebrew | Source install first, binary distribution later |
| Local model runtime | Ollama | Preferred local-first Brain for solo/dev workflows |
| Credential storage | Environment variables or OS keychain | API keys must not be stored in plaintext config |

## 3. Architectural Style

Entroping follows Ports and Adapters. Dependencies point inward toward pure domain models and policies.

```text
src/entroping/
  models/        # Domain schemas. No adapter imports.
  bridge/        # Domain transformations and compilers.
  cli/           # Typer primary adapter.
  core/          # Hurl, proxy, DB, reports, config adapters.
  brain/         # LiteLLM and agent orchestration adapters.
  studio/        # Textual UI adapter.
```

### Dependency Rules

- `models/` must not import `cli/`, `core/`, `brain/`, or `studio/`.
- `bridge/` can import `models/` and pure utility code only.
- `cli/` coordinates use cases but should not contain business rules.
- `core/` adapts external systems such as Hurl, SQLite, filesystem, and mitmproxy.
- `brain/` adapts LLM providers and validates structured outputs before returning domain objects.
- Cross-module contracts use Pydantic models, typed protocols, or explicit dataclasses.

`tests/test_architecture_boundaries.py` is the executable regression guard for
these dependency rules. It parses Python imports with `ast` and fails the normal
test suite if domain or bridge code imports adapters, deterministic run-core
modules import Brain/LiteLLM code, or source modules import provider SDKs directly
instead of going through LiteLLM.

Current Brain foundation modules:

- `models.architect` defines validated Architect Hurl edit output models.
- `brain.output_parser` parses raw provider JSON into validated Architect edits.
- `brain.architect_writer` stages Architect-owned Hurl file writes safely.
- `brain.persona_loader` loads root-bounded Markdown persona files from agent config.
- `brain.prompt_builder` builds redaction-checked prompt packages.
- `brain.litellm_client` lazily wraps `litellm.completion` behind an injectable adapter.
- `brain.architect_build` orchestrates Builder prompt generation across persona
  loading, prompt packaging, LiteLLM invocation, output parsing, and staged writes.

## 4. Proposed Package Layout

```text
src/entroping/
  __init__.py
  cli/
    main.py
    commands/
      init.py
      doctor.py
      config.py
      architect.py
      watch.py
      freeze.py
      map.py
      run.py
      report.py
      studio.py
  models/
    conditions.py
    qanstitution.py
    hurl.py
    traffic.py
    report.py
    agent.py
    errors.py
  bridge/
    openapi_to_hurl.py
    traffic_to_hurl.py
    traffic_to_wiremock.py
    traffic_to_graph.py
    policy_to_hurl.py
    story_traceability.py
    merge.py
  core/
    config_loader.py
    hurl_runner.py
    gate_injector.py
    traffic_store.py
    mitm_addon.py
    report_writer.py
    dependency_mapper.py
    env_loader.py
  brain/
    router.py
    litellm_client.py
    structured_outputs.py
    prompts.py
  studio/
    app.py
tests/
```

## 5. Domain Models

Core models must be explicit and validated:

| Model | Purpose |
| --- | --- |
| `Qanstitution` | Effective governance config after imports |
| `Condition` | Parsed and validated small DSL for gate matching |
| `GateRule` | Runtime assertion rule with condition and enforcement |
| `AgentConfig` | Model/persona routing for Builder, Auditor, Breaker |
| `IgnoreFailure` | Known-failure exception with issue ID and expiry |
| `HurlTest` | Parsed test metadata, path, tags, story IDs |
| `TestScenario` | LLM/generated intermediate representation |
| `TrafficExchange` | Redacted observed request/response record |
| `TrafficRequest` / `TrafficResponse` | Request/response metadata plus bounded body summaries |
| `TrafficBody` | Size, content type, truncation flag, and redacted text summary |
| `FreezeSession` | Group of traffic records converted into tests or mocks |
| `DependencySpec` | Optional provider/consumer spec pointer for cross-service validation |
| `AiEditAudit` | Metadata about generated or refactored files for human review |
| `RunResult` | Aggregated Hurl execution outcome |
| `ReportArtifact` | Path, type, and summary metadata for generated reports |

Avoid `Any` in application-facing models. Use discriminated unions or typed dictionaries only where the format is genuinely variable.

`AgentConfig.model` is routing metadata only. It must reject empty values,
control characters, and API-key-shaped strings so configuration commands cannot
turn `qanstitution.yaml` into a credential store.

## 6. QAnstitution Design

`qanstitution.yaml` is the executable law. It is YAML because it must be schema-validatable, diffable, easy to import, and safe for deterministic runtime parsing.

Example:

```yaml
project: "checkout-api"
version: "4.1"
description: "Checkout service quality law"

sources:
  spec: "./openapi.json"
  stories: "./docs/stories"
  traffic: ".entroping/state.db"
  graph: "./schema.graphql"

dependencies:
  - name: "auth-service"
    spec: "../auth-service/openapi.json"
  - name: "payments"
    spec: "https://raw.githubusercontent.com/acme/payments/main/openapi.json"

imports:
  - "./rules/security.yaml"
  - "https://raw.githubusercontent.com/acme/governance/main/performance.yaml"

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
  breaker:
    source: "agents/breaker.md"
    model: "deepseek/<breaker-model>"
    temperature: 0.7

gates:
  - id: "global_latency"
    description: "Every endpoint must respond within 2 seconds"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
  - id: "smoke_speed"
    condition: "tags contains 'smoke'"
    gate: "duration < 500"
    enforcement: "block"

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
  env_defaults:
    base_url: "http://localhost:8080"
```

### Import Semantics

1. Resolve local imports relative to the importing file.
2. Resolve HTTP(S) imports with timeouts and optional cache.
3. Validate each imported document before merging.
4. Merge imported gates before local gates.
5. Local gates override imported gates with the same ID unless the imported gate is `final: true`.
6. The effective policy must be inspectable through `doctor` or report output.

Reusable QAnstitution policy packs use the same import boundary and are
documented in [POLICY_PACK_LAYOUT.md](POLICY_PACK_LAYOUT.md). The pack layout is
a design contract and example shape; it does not add registry, remote-fetch, or
runtime manifest behavior by itself.

Organization QAnstitution import controls are defined by
[ADR-0011-organization-qanstitution-import-controls.md](https://github.com/sakibshuvo/Entroping/blob/main/decisions/ADR-0011-organization-qanstitution-import-controls.md).
Remote, registry, signature, and approval workflows must preserve the same
effective-policy merge, provenance, final-gate, and local-first execution
boundary before they become runtime features.

### Condition DSL

The first supported condition language should be intentionally small:

```text
true
tags contains 'smoke'
method == 'POST'
path startswith '/api/v1/payments'
url contains 'checkout'
meta.story_id == 'STORY-123'
```

Invalid conditions fail configuration validation. Do not silently skip malformed gates.

Implementation rule: keep the YAML-facing `GateRule.condition` field as the original string for readable diffs, but validate it by compiling into a typed condition object at parse time. The typed condition parser belongs in the domain model layer and must not depend on CLI, Hurl, LLM, or proxy adapters.

## 6.1 Bridge Compiler Boundaries

`bridge/` is a set of small compilers, not a dumping ground:

| Module | Owns | Must not own |
| --- | --- | --- |
| `openapi_to_hurl.py` | OpenAPI operation/schema to Hurl models | LLM calls, file writes, merge strategy |
| `traffic_to_hurl.py` | Redacted traffic session to Hurl models | mitmproxy capture, SQLite persistence |
| `traffic_to_wiremock.py` | Redacted dependency traffic to WireMock mappings | Filesystem writes, mock server runtime |
| `traffic_to_graph.py` | Redacted traffic to dependency graph models | SQLite reads, renderer invocation |
| `policy_to_hurl.py` | QAnstitution gate to Hurl assertions | Hurl subprocess execution |
| `story_traceability.py` | Story IDs, owners, external doc URLs | Business-system API clients |
| `merge.py` | Manual-edit-preserving Hurl merge/refactor logic | Test generation strategy |

The shipped `story_traceability.py` bridge compiles discovered Hurl metadata
into local story/test reports. It validates missing `story_id` comments and
flags external `doc_url` values that point to multiple story IDs; it does not
call Jira, Notion, Linear, monday.com, or other business-system APIs.

## 7. Hurl Execution Design

`core.hurl_runner` is the only module allowed to invoke Hurl.

Requirements:

- Locate `hurl` through PATH or explicit config.
- Use `subprocess.run` or `asyncio.create_subprocess_exec` with argument arrays.
- Set timeouts.
- Capture stdout and stderr without leaking secrets.
- Return typed `RunResult` objects.
- Never execute API requests with Python `requests`, `httpx`, or `urllib` as a replacement for Hurl.

Gate injection should write temporary execution copies or feed Hurl through safe temporary files. Source `.hurl` files must not be mutated during `entroping run`.

### Runtime Flow

1. Discover test files.
2. Parse metadata tags and story IDs.
3. Load and validate effective QAnstitution.
4. Match gates to tests.
5. Create execution material with injected assertions.
6. Invoke `hurl`.
7. Parse outputs and enforcement levels.
8. Write reports and exit with deterministic status.

## 8. Hurl Metadata Conventions

Tests should use Entroping metadata comments to support selection and traceability. Do not put `tags` or `meta` keys inside Hurl `[Options]`; those are not Hurl options and can make files invalid. Comments remain valid Hurl and are safe for Entroping to parse.

```hurl
# entroping: tags=smoke,checkout,critical
# entroping: story_id=CHK-001
# entroping: owner=payments

POST {{base_url}}/checkout
Content-Type: application/json
{
  "cart_id": "{{cart_id}}"
}

HTTP 201
[Asserts]
jsonpath "$.id" exists
jsonpath "$.status" == "accepted"
```

Folders provide physical organization. Entroping metadata comments provide
virtual suites and traceability. The traceability bridge can aggregate these
comments into local reports before a future CLI/report adapter exposes that
workflow directly. Hurl `[Options]` remains available for real Hurl options
such as `variable`, `retry`, `location`, and `delay`.

## 9. Architect Design

The Architect is an AI-assisted adapter, not a source of authority. Its outputs must be validated before being accepted.

### Agent Routing

| Agent | Responsibilities |
| --- | --- |
| Builder | Generate positive path, contract, and story-linked tests |
| Auditor | Find missing coverage, weak assertions, policy gaps, and drift risk |
| Breaker | Generate negative, hostile, fuzz, auth, IDOR, and boundary tests |

Use a small typed router for the MVP. LangGraph or another orchestration framework can be added later only if routing complexity justifies the dependency.

### LLM Call Boundaries

Separate:

1. Prompt construction.
2. Model invocation through LiteLLM.
3. Structured response parsing.
4. Domain validation.
5. File merge/write.

Prompts should include only necessary context. Secrets and raw sensitive traffic must not be sent to models.

Current implementation note: `architect build --prompt` now wires the CLI to the
Brain foundation for the Builder happy path. The command loads the configured Builder
persona, builds a redaction-checked prompt package, invokes LiteLLM through the lazy
adapter, parses provider JSON into validated Architect edits, injects requested tags,
validates generated Hurl through `hurlfmt --out json`, and writes Architect-owned
Hurl files through the staged writer. `architect refactor` also supports manual
Hurl files that opt into managed-block replacement. `architect build --strategy
merge --prompt` reuses the same managed-block and prepared-write boundaries for
existing files only. Provider summaries, warnings, parser failures, and errors are
redacted or summarized before CLI output. `entroping run` remains LLM-free.

### Provider Strategy

The Brain is local-first and cloud-second:

- Default local provider should be Ollama where available.
- Cloud models are configured explicitly through model IDs such as `anthropic/...`, `openai/...`, `gemini/...`, or `deepseek/...`.
- Local OpenAI-compatible runtimes, including oMLX, can be configured with
  non-secret `api_base` endpoint metadata and optional `api_key_env`
  environment-variable names on each agent.
- Entroping must not shell out to external Gemini, Claude, or ChatGPT CLIs for intelligence.
- If a local model is missing, the CLI should fail with helpful setup guidance or, in a future UX layer, offer an explicit pull/start flow.
- API keys must come from environment variables or OS credential storage. Do not write provider keys into `qanstitution.yaml`, `.env.example`, logs, reports, or traffic state.
- The same agent persona and QAnstitution constraints should be used across local and cloud models so behavior stays consistent.

### Source Grounding

The Architect can use these sources as grounding:

- OpenAPI or GraphQL schemas from `sources`.
- Markdown story snapshots from `docs/stories`.
- Observed and redacted traffic sessions.
- Cross-service specs listed in `dependencies`.
- Explicit user prompts.

Generated endpoints must be traceable to one of those sources. If the user asks for exploratory or negative tests beyond the spec, the generated file should carry metadata that marks the test as prompt-derived or breaker-derived.

### Merge Strategy

`architect build --strategy merge` and `architect refactor` must:

- Preserve comments.
- Preserve manual sections where possible.
- Avoid rewriting unrelated files.
- Produce a diff-oriented result.
- Run parser-backed syntax validation on modified Hurl files, using `hurlfmt --out json <file>` or an equivalent Hurl parser-backed validator.

Manual files opt into AI-maintained sections with explicit managed-block markers:

```hurl
# entroping: managed-begin checkout-auth
GET {{base_url}}/checkout
HTTP 200
# entroping: managed-end checkout-auth
```

The `bridge.merge` primitive replaces only matching generated managed blocks and
preserves content outside those markers byte-for-byte. It rejects malformed,
duplicate, nested, missing, or unknown managed blocks before a caller can write
anything.

Current implementation note: `architect refactor` supports two safe target modes:
Architect-owned whole-file targets marked with `# entroping: source=architect`, and
manual targets that contain valid managed-block markers. It loads selected target
files into Builder prompt context, rejects unsafe globs and symlinked or non-Hurl
targets, requires returned edits to stay within the selected target set, merges
manual managed blocks before validation, validates final Hurl through the
parser-backed Hurl validator, and writes through staged filesystem writes. Prompt
build merge uses the same rules for existing files; merge without a prompt remains
deferred.

## 10. Observation Design

`entroping watch` starts a mitmproxy-based recorder.

The recorder should reduce noise before persistence. Static assets, analytics beacons, browser favicon calls, large binary payloads, and hosts outside the selected target/dependency scope can be filtered or marked as ignored. Recorded calls should be grouped by session ID so `freeze` can operate on a coherent user flow rather than a flat traffic dump.

Current implementation:

- `core.traffic_proxy` lazy-loads mitmproxy so default installs can fail with an actionable optional-dependency message.
- `TrafficCaptureAddon.response()` records completed HTTP flows only after converting them into `TrafficExchange` models, redacting them, and persisting through `TrafficStore`.
- `watch --target <url>` scopes capture to the exact target scheme and host.
- Request and response body summaries decode textual media types, keep binary bodies as size-only records, and reuse the global traffic body limit.
- `freeze` and `map` are intentionally not coupled to capture startup.

### Captured Data

| Field | Notes |
| --- | --- |
| Timestamp | UTC |
| Request method/path/url | Normalized |
| Request headers | Redacted allowlist/blocklist |
| Request body | Size-limited and redacted |
| Response status | Required |
| Response headers | Redacted |
| Response body | Size-limited and redacted |
| Duration | Milliseconds |
| Upstream host/service | For dependency mapping |
| Session ID | For freeze grouping |

### Redaction Requirements

Default redactions must cover:

- Authorization headers.
- Cookies.
- API keys and bearer tokens.
- Password-like fields.
- Session IDs where unsafe.
- Large binary bodies.

Users can extend redaction rules in QAnstitution or local config.

### State Store

The SQLite database under `.entroping/state.db` should be treated as local runtime state, not a product database. The implementation uses SQLModel as the typed persistence layer while preserving SQLite as the local on-disk store.

Current foundation:

- `TrafficStore.open_project(<root>)` opens `.entroping/state.db`.
- `traffic_store_metadata` stores `schema_version=1` through
  `TrafficStoreMetadataRow`.
- `TrafficEventRow` maps the `traffic_events` table through SQLModel.
- `traffic_events` stores only redacted `TrafficExchange` JSON plus indexed method, URL, host, path, status, duration, and capture time.
- Persistence refuses any exchange whose `redacted` flag is false.
- Retention keeps local growth bounded by a configurable event count.
- Traffic state modules are covered by import-boundary tests so they do not call Brain/LiteLLM providers.
- Proxy capture modules are adapter-only and should not send captured traffic to Brain/LiteLLM providers.

Traffic-store schema policy:

- Current schema version is `1`.
- Write-capable opens create missing metadata for pre-version alpha stores.
- Read-only Studio/status paths validate existing metadata without creating or
  migrating `.entroping/state.db`; older alpha stores with no metadata are
  treated as version 1 for read compatibility.
- A store with a future schema version fails closed with an upgrade-required
  error before traffic rows are read or written.
- Explicit older schema versions fail until a reviewed migration is added. Do
  not silently rewrite state with an unknown schema contract.

Suggested future tables:

| Table | Purpose |
| --- | --- |
| `traffic_log` | Redacted request/response records |
| `traffic_session` | User-flow grouping for freeze operations |
| `run_history` | Last run summary used by reports and bug templates |
| `ai_edit_audit` | AI generation/refactor metadata, prompts, file paths, and validation status |
| `baseline_snapshot` | Drift and golden-master comparison metadata |

Retention must be configurable. A safe default is bounded local growth, such as size-based rotation around 1 GB or age-based cleanup, with explicit export commands later if needed.

## 11. Freeze and Mock Design

`entroping freeze` converts traffic sessions into artifacts.

The canonical implementation plan is
[[docs/technical/FREEZE_MAP_PLAN|FREEZE_MAP_PLAN]]. The boundary rule is that
capture, persistence, session/filtering, Hurl compilation, and graph compilation
stay separate. `watch` must not generate Hurl, and bridge compilers must not
read SQLite directly.

| Option | Output |
| --- | --- |
| `--name checkout_flow` | `tests/generated/checkout_flow.hurl` |
| `--golden` | Stable assertions against known-good behavior |
| `--mock payments` | WireMock mappings for observed dependency behavior |

Generated tests should parameterize volatile fields such as IDs and timestamps. Golden assertions should avoid locking unstable values unless explicitly requested.

Mock generation selects records by safe service selector, matching either an
exact host such as `payments.example.test` or the first host label such as
`payments`. Entroping generates mappings for standard mock servers such as
WireMock; it does not become the mock server itself.

Implementation order:

1. Add deterministic traffic filtering and session candidate models. Done in `bridge.traffic_sessions`.
2. Add a pure `bridge.traffic_to_hurl` compiler for redacted traffic. Done.
3. Wire `freeze` through safe generated-file writes and parser validation. Done for basic Hurl generation.
4. Add WireMock-compatible mock mappings after basic freeze and redaction tests are stable. Done.

## 12. Dependency Map Design

`entroping map --export <fmt>` reads traffic records and emits dependency graphs.

Supported exports:

- `mermaid`
- `dot`
- `md`
- `png` where Graphviz or a renderer is available

The map should show services, routes, methods, call counts, failures, and latency summaries where available.

MVP map output is host-level. Service-level inference and external system labels
are follow-up layers after the Mermaid/Markdown/DOT/PNG compiler path is stable
and escaped.

Current implementation note: Mermaid, DOT, Markdown, and PNG exports are implemented
through a pure `bridge.traffic_to_graph` compiler and `core.dependency_mapper`
adapter. PNG export renders through local Graphviz `dot` when available and fails
with an actionable missing-renderer message otherwise.

## 13. Reporting Design

Reports are written under `reports/`.

| Report | Command | Purpose |
| --- | --- | --- |
| HTML | `run --report html` | Human review |
| JUnit XML | `run --report junit` | CI systems |
| JSON | `run --report json` | Tooling integration |
| Drift JSON | `run --drift-check` or `--report drift` | `.entroping/drift-baseline.json` comparison |
| Audit Markdown | `architect audit --output md` | Gap review |
| Bug Markdown | `report bug` | Issue tracker handoff |
| Redaction Review | `report redaction --output md|html` | Captured-traffic redaction coverage review |
| Effective Policy | `report policy --output md|json` | Resolved QAnstitution gate provenance |
| Traceability Markdown | `report traceability --output md` | Local story/test coverage review |
| GitHub Annotations | `report github-annotations` | Pull request workflow-command annotations |

JUnit is required because it is the common denominator for CI. Allure can consume JUnit later. JaCoCo is not a fit because Entroping is black-box runtime testing, not code coverage instrumentation.

## 14. CLI Contracts

Compatibility audit: [CLI_COMPATIBILITY_AUDIT.md](CLI_COMPATIBILITY_AUDIT.md).

### Setup

```text
entroping init [--minimal]
entroping doctor
entroping config list
entroping config set --agent <builder|auditor|breaker> --model <model-id>
```

`config set` updates non-secret routing metadata only. If the selected agent's
persona file is missing, it creates a local Markdown template under the configured
relative source path after rejecting absolute paths, traversal, symlinks, non-Markdown
paths, URLs, and control characters.

### Intelligence

```text
entroping architect build [--new] [--prompt <text>] [--strategy merge] [--tag <tag>]
entroping architect refactor --target <glob> --prompt <text>
entroping architect audit [--focus logic] [--output <json|md>]
```

### Observation

```text
entroping watch [--port <port>] [--target <url>]
entroping freeze --name <flow> [--golden] [--mock <service>]
entroping map [--export <mermaid|dot|md|png>]
```

### Execution and Reporting

```text
entroping studio [--env <name>]
entroping run [--env <name>] [--tag <tag>] [--ci] [--parallel] [--report <html|junit|json|drift> ...] [--drift-check]
entroping report bug
entroping report redaction [--output <md|html>]
entroping report policy [--output <md|json>]
entroping report traceability [--output md]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
```

`studio` is an interactive read-only Textual TUI. It requires the optional
Studio extra and renders tabs for local QAnstitution status, latest-run summary,
suite rows, failure details, applied-gate drilldowns, report artifacts, and a
read-only traffic session browser. Applied-gate drilldowns read latest-run report rule IDs
and QAnstitution gate definitions; Studio does not run Hurl and does not edit tests or config
to build this view. The traffic browser reads
redacted SQLModel-backed state from `.entroping/state.db` through a read-only
query path, infers target/dependency grouping from filtered captured traffic,
and displays route summaries plus safe redaction categories and counts. It does
not start `watch`, control live capture, or render raw URLs with query values,
headers, bodies, cookies, tokens, or secrets.
It must not mutate tests, config, reports, or runtime state. Near-term Studio
work is report-backed: CLI and report artifacts remain the primary workflow,
and Studio may only add read-only views over sanitized reports, applied gate
metadata, and redacted traffic summaries until a separate mutation design is
accepted. The accepted design gate for any future write action lives in
[STUDIO_MUTATION_WORKFLOW_DESIGN.md](STUDIO_MUTATION_WORKFLOW_DESIGN.md).
`--report` is repeatable so a single run can emit both CI and human artifacts, for example `--report junit --report html`.
`--parallel` uses `settings.parallel_workers` from `qanstitution.yaml`, keeps the
per-file timeout and output-redaction behavior, and preserves deterministic
input ordering in reports.
`--drift-check` and `--report drift` compare the sanitized current run report
against `.entroping/drift-baseline.json`. The MVP baseline compares test path,
Hurl result status, exit code, injected QAnstitution rule IDs, material
per-test latency regressions, and optional response fingerprints. Latency
comparison uses the sanitized `duration_ms` values already present in reviewed
run baselines and reports only conservative warning findings. Response
fingerprints contain only status code, selected stable headers such as
`content-type`, and JSON body shape paths; full response bodies and volatile
headers are not stored as drift truth. `--report drift` also writes
`reports/drift-baseline.candidate.json` after a passing Hurl suite. That
candidate is sanitized and reviewable; the active
`.entroping/drift-baseline.json` file is never written automatically.

### Report Artifact Contracts

| Command | Artifact | Stability note |
| --- | --- | --- |
| `entroping run` | `.entroping/latest-run.json` | Runtime state for follow-up report commands; uses `entroping.run-report.v1`; not committed. |
| `entroping run --report json` | `reports/run-latest.json` | Machine-readable run report using `entroping.run-report.v1`. |
| `entroping run --report junit` | `reports/junit.xml` | CI-compatible test report. |
| `entroping run --report html` | `reports/run-latest.html` | Human-readable local report. |
| `entroping run --report drift` | `reports/drift.json` | Machine-readable drift findings using `entroping.drift-report.v1`. |
| `entroping run --report drift` | `reports/drift-baseline.candidate.json` | Reviewable sanitized baseline candidate after a passing Hurl suite. |
| `entroping report bug` | `reports/bug.md` | Markdown handoff for issue trackers. |
| `entroping report redaction --output md` | `reports/redaction-review.md` | Counts-only captured-traffic redaction review. |
| `entroping report redaction --output html` | `reports/redaction-review.html` | Browser-readable captured-traffic redaction review. |
| `entroping report policy --output md` | `reports/effective-policy.md` | Human-readable resolved QAnstitution gate provenance. |
| `entroping report policy --output json` | `reports/effective-policy.json` | Machine-readable effective policy evidence using `entroping.effective-policy-report.v1`. |
| `entroping report traceability --output md` | `stdout Markdown` | Local story/test coverage report. |
| `entroping report github-annotations` | `stdout GitHub Actions annotations` | Workflow-command annotations from JUnit, drift, and optional traceability findings. |

Versioned report schema contracts are documented in
`docs/technical/REPORT_SCHEMAS.md`. JSON report writers must include
`schema_version`; loaders remain tolerant of older local state that predates the
version field.

If `.entroping/dependency-baseline.json` exists, the same drift run also compares
current redacted traffic observations from `.entroping/state.db` against reviewed
dependency routes. The dependency baseline shape is intentionally route-only:

```json
{
  "source_label": "client",
  "routes": [
    {
      "destination_host": "payments.example.test",
      "method": "POST",
      "path_template": "/charges/{id}"
    }
  ]
}
```

Dependency drift findings report `missing_dependency_route` and
`new_dependency_route`. Query strings, headers, cookies, tokens, request bodies,
response bodies, call counts, and latency values are excluded from dependency
drift truth.

No additional commands or flags should be implemented without updating the product specification first.

## 15. Configuration and Secrets

- Secrets come from environment variables, secret managers, or gitignored env files.
- Cloud provider credentials should use OS credential storage where practical, for example macOS Keychain through a keyring adapter.
- No API keys in qanstitution.yaml. Agent `api_key_env` values are environment
  variable names only, never secret values.
- `envs/*.env.example` can be committed.
- Real `envs/*.env` files should be gitignored unless sanitized.
- Logs and reports must redact known secret patterns.
- LLM prompts must not include secrets.
- Traffic persistence must apply redaction before storing raw data.

## 16. Error Handling

Errors must be explicit and actionable:

- Missing Hurl binary: tell user how to install or configure it.
- Invalid QAnstitution: identify path and field.
- Bad gate condition: identify rule ID and invalid expression.
- Hurl validation failure: show the generated file path and retry guidance
  without echoing raw provider content from parser stdout/stderr.
- mitmproxy certificate issue: explain CA installation steps.
- LLM provider failure: include role/model and retry/fallback status without exposing keys.
- Local model unavailable: explain whether Ollama is missing, not running, or missing the configured model.
- State store too large: explain retention settings and cleanup/export options.

Do not swallow exceptions silently. Convert expected failures into typed domain errors and user-friendly Rich output.

## 17. Observability

Runtime logs should include:

- Command and mode.
- Effective environment name.
- Test count, tag filters, and report types.
- Gate IDs applied.
- Agent role/model metadata, latency, token usage, and estimated cost where available.
- Hurl execution duration and exit status.

Logs must not include request secrets, API keys, or sensitive captured bodies.

## 18. Testing Strategy

| Area | Tests |
| --- | --- |
| QAnstitution parser | Valid configs, invalid configs, imports, override/final semantics |
| Condition DSL | Match and non-match cases, syntax failures |
| Gate injector | Source file immutability, injected assertions, tags |
| Hurl runner | Subprocess command construction, timeout, stderr parsing |
| Architect merge | Preserve comments/manual sections, reject invalid Hurl |
| Traffic redaction | Headers, cookies, JSON fields, body limits |
| Traffic filtering/session stitching | Static asset exclusion, ignored hosts, session grouping |
| Freeze | Traffic to parameterized Hurl and WireMock mappings |
| State retention | Rotation/cleanup behavior for `.entroping/state.db` |
| Reports | JUnit schema, JSON shape, bug template content |
| Performance smoke | Large synthetic Hurl suite, bounded parallel runner behavior, report size, and SQLModel traffic-store retention evidence |
| CLI | Typer command contracts and exit codes |

External integrations should be tested with small fixtures and deterministic subprocess stubs where possible. A smoke suite should exercise real Hurl when available. Local release-owner scalability evidence is generated through `uv run python scripts/performance_smoke.py`, which writes ignored JSON evidence under `reports/performance-smoke.json`.

## 19. Security Requirements

Threat model: [THREAT_MODEL.md](THREAT_MODEL.md).

- Never log secrets.
- Validate all file paths before writing generated artifacts.
- Avoid path traversal when using flow names, mock names, and report names.
- Use network timeouts for remote imports and LLM calls.
- Cache remote imports only with clear provenance.
- Avoid sending raw captured traffic to LLMs by default.
- Require explicit user intent for cloud upload or remote model use with sensitive traffic.
- Make known-failure exceptions expire.
- Treat generated tests as code and require review.

## 20. Distribution Plan

### MVP Distribution

Use source/GitHub distribution first:

```text
uv tool install -e .
uv tool install git+https://github.com/sakibshuvo/Entroping.git
uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha
```

Before any release claim, verify local artifacts:

```text
scripts/package_check.sh
```

The package check builds wheel/sdist artifacts with `uv build` and inspects
metadata for project name, version, SPDX license expression, license file
presence, and alpha maturity classifiers. It does not publish to PyPI/TestPyPI
and must not require package-index credentials.

Package-index publishing is controlled by `docs/meta/PYPI_RELEASE_RUNBOOK.md`
and the manual `.github/workflows/publish-python-package.yml` workflow. The
preferred path is TestPyPI first, then PyPI, using Trusted Publishing through
protected GitHub Actions environments instead of long-lived package-index
tokens.

Distribution sequencing is documented in
`docs/meta/DISTRIBUTION_RECOMMENDATION.md`: keep `uv tool install` as the
immediate cross-platform path, activate PyPI/TestPyPI next, prototype a Homebrew
tap after the PyPI alpha is stable, and defer standalone binaries until demand
justifies signing, notarization, and platform build ownership.

### Later Distribution

- Nuitka standalone binary.
- Homebrew formula.
- PyPI package.
- Docker image for CI runners.
- GitHub release artifacts.
- Optional Entroping Cloud integration for central governance, audit logs, SSO, and team dashboards.

## 21. Implementation Guardrails

1. Preserve the locked command namespace.
2. Keep Hurl as the only execution engine.
3. Keep LiteLLM as the only LLM provider abstraction.
4. Keep `mitmproxy` as the traffic capture foundation.
5. Keep domain code independent from adapters.
6. Validate generated files before accepting them.
7. Treat security and quality as release gates.
