# Entroping Technical Design Specification

**System:** Entroping Core
**Design Version:** 4.1
**Implementation Maturity:** Alpha; stable-core readiness is blocked by package-index proof, downstream feedback, and compatibility graduation.
**Versioning Note:** v4.1 is the product/spec/CLI contract generation, not the Python package release version; package releases use alpha Git tags and PEP 440 package metadata tracked from `pyproject.toml`.
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
instead of going through LiteLLM. `scripts/architecture_integrity.sh` runs this
focused guard as a named feature-gate step before the broader lint/type/test
suite. Direct-provider SDK prefixes such as OpenAI, Anthropic, Gemini,
DeepSeek, and common model-provider SDKs are rejected inside `src/entroping`;
maintainer-only worker scripts remain outside the product runtime boundary and
produce ignored local artifacts for Codex validation.

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

`qanstitution.yaml` is the executable law and canonical policy filename. It is
YAML because it must be schema-validatable, diffable, easy to import, and safe
for deterministic runtime parsing. Compatibility aliases such as
`entroping.yaml` or `entroping-policy.yaml` are not supported unless a future
ADR accepts a migration and backward-compatibility plan.

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
  protected_environments:
    - "prod"
    - "production"
    - "protected"
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

### Gate Group Semantics

`gate_groups` is a local authoring construct, not a second runtime policy
format. The Pydantic model expands top-level `{ group: "<name>" }` entries into
ordinary `GateRule` objects before runtime matching, Hurl injection, and report
generation. A group expands nested `groups` in order, then its own `gates`.
Missing groups and cycles fail validation before execution.

The filesystem loader uses the same expansion semantics while retaining group
provenance in `QanstitutionEvidence`. Effective-policy reports include the
source file and source group for every expanded gate. Imported documents expand
their groups before merge, so duplicate IDs and `final: true` protections keep
the same behavior as directly-authored imported gates.

Reusable QAnstitution policy packs use the same import boundary and are
documented in [POLICY_PACK_LAYOUT.md](POLICY_PACK_LAYOUT.md). The pack layout is
a design contract and example shape; `config vendor-policy-pack` can copy a
reviewed local pack into `policy-packs/` and append a local import, but it does
not add registry, remote-fetch, or runtime manifest behavior.

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
| `story_traceability.py` | Story IDs, local story Markdown files, owners, external doc URLs | Business-system API clients |
| `merge.py` | Manual-edit-preserving Hurl merge/refactor logic | Test generation strategy |

The shipped `story_traceability.py` bridge compiles discovered Hurl metadata
and core-discovered `docs/stories/*.md` story documents into local story/test
reports. It validates missing `story_id` comments, Hurl story IDs with no local
story Markdown, Markdown stories without tests, duplicate Markdown story IDs,
malformed story metadata, unsafe story paths, and external `doc_url` values that
point to multiple story IDs. It does not call Jira, Notion, Linear, monday.com,
or other business-system APIs.

## 7. Hurl Execution Design

`core.hurl_runner` is the only module allowed to invoke Hurl.

Requirements:

- Locate `hurl` through PATH or explicit config.
- Hurl binary trust policy:
  - A bare binary name such as `hurl` intentionally trusts the parent process
    `PATH`, matching normal CLI and CI setup behavior, then executes the
    resolved binary target so PATH-selected symlinks such as Homebrew shims are
    safe to reuse as explicit paths.
  - An explicit binary path must be absolute, executable, free of symlinked
    user-selected components, and resolved before execution; this lets
    high-assurance or CI callers pin the reviewed Hurl binary and bypass
    earlier `PATH` entries. Host-level filesystem aliases such as macOS
    `/var -> /private/var` do not make an otherwise direct path unsafe.
  - Relative binary paths such as `./hurl` are rejected because they depend on
    the current working directory and can be spoofed by local project files.
  - The child process still receives a minimized `PATH` containing only the
    resolved Hurl binary directory plus `/usr/bin` and `/bin`.
- Treat Hurl 4.3.0 as the minimum supported syntax/runtime floor. The reviewed
  CI examples pin Hurl 8.0.1 for repeatable setup evidence.
- Check `hurl --version` through a bounded subprocess argument array in
  `doctor`; version checks must not execute API requests.
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
Brain foundation for Builder generation by default and Breaker generation when
`--agent breaker` is selected. The command loads the configured role persona,
builds a redaction-checked prompt package, invokes LiteLLM through the lazy adapter,
parses provider JSON into validated Architect edits, injects requested tags, adds
the `breaker` tag for Breaker output, validates generated Hurl through
`hurlfmt --out json`, and writes Architect-owned Hurl files through the staged
writer. `architect refactor` also supports manual Hurl files that opt into
managed-block replacement, and `architect refactor --preview` renders a
validated unified diff without writing target Hurl files. `architect build
--strategy merge --prompt` reuses the same managed-block and prepared-write
boundaries for existing files only. Provider
summaries, warnings, parser failures, and errors are redacted or summarized before
CLI output. `architect audit --focus auditor` uses the configured Auditor route
to produce validated review findings without writing files. `entroping run`
remains LLM-free.

Self-healing Hurl maintenance stays a review-first Architect workflow, not an
autonomous runtime repair loop. Accepted proposal inputs are an explicit prompt,
an OpenAPI diff, a failed deterministic run or failure bundle, or a drift report.
The proposal must remain previewable as a diff or structured artifact, pass
structured provider-output validation and parser-backed Hurl validation before
any target write, and require a human to review, write, commit, push, or merge
the change.

Prompt-backed Architect build, merge, refactor, and Auditor review paths also
write value-free manifests under `.entroping/agent-runs/` with schema
`entroping.agent-run-manifest.v1`. These manifests record role, model, persona
path/digest, prompt hashes, output paths, value-free source evidence such as
prompt hashes and selected target content hashes, tags, validation status,
provider, latency, token counts, and estimated cost when per-million-token rates
are configured and provider usage metadata is available. They are audit evidence
only; they do not store raw prompts, provider output, persona content, target
Hurl contents, secrets, traffic, or model approval.

The deterministic `architect build --new` OpenAPI path also validates every
compiled Hurl file through the same parser-backed Hurl validation boundary
before writing any generated file. If one compiled file fails validation, no
partial generated files are left behind.

When an OpenAPI operation has a JSON request body and an explicit validation
failure response (`400` or `422`), the same deterministic path emits a bounded
negative-path corpus under `tests/generated/negative/`. The current corpus is
reviewable committed Hurl for malformed JSON, schema violations, boundary
values, SQLi-like strings, and IDOR-style path variations. It never runs during
generation, never calls an LLM from `entroping run`, and never performs random
or hidden fuzzing. Generated negative files carry `negative_category`,
`severity`, and safety metadata plus category tags so QAnstitution conditions
and suite tag filters can opt into categories deliberately; mutating generated
negative tests are marked `safety=destructive` so protected environments block
them before Hurl execution unless teams review and rewrite the test safety.

### Provider Strategy

The Brain is local-first and cloud-second:

- Default local provider should be Ollama where available.
- Cloud models are configured explicitly through model IDs such as `anthropic/...`, `openai/...`, `gemini/...`, or `deepseek/...`.
- Local OpenAI-compatible runtimes, including oMLX, can be configured with
  non-secret loopback-only `api_base` endpoint metadata and optional
  `api_key_env` environment-variable names on each agent.
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
parser-backed Hurl validator, and writes through staged filesystem writes.
Preview mode uses the same provider, parser, merge, and validation boundaries,
then emits a redacted unified diff and value-free agent manifest without writing
target Hurl files. Refactor manifests record `source_evidence` for the explicit
prompt and selected Hurl targets using hashes rather than raw prompt or Hurl
content, so review bundles can explain why a proposal exists without leaking
secrets. Prompt build merge uses the same rules for existing files; merge
without a prompt remains deferred.

## 10. Observation Design

`entroping watch` starts a mitmproxy-based recorder.

The recorder should reduce noise before persistence. Static assets, analytics beacons, browser favicon calls, large binary payloads, and hosts outside the selected target/dependency scope can be filtered or marked as ignored. Recorded calls should be grouped by session ID so `freeze` can operate on a coherent user flow rather than a flat traffic dump.

Current implementation:

- `core.traffic_proxy` lazy-loads mitmproxy so default installs can fail with an actionable optional-dependency message.
- `TrafficCaptureAddon.response()` records completed HTTP flows only after converting them into `TrafficExchange` models, redacting them, and persisting through `TrafficStore`.
- `watch` fails closed unless an explicit capture scope is configured with
  `--target`, `--scope-host`, or `--scope-url-prefix`.
- `watch --target <url>` scopes capture to the exact normalized target origin,
  while `--scope-host` matches host names case-insensitively and
  `--scope-url-prefix` matches normalized absolute URL prefixes without query
  strings or fragments.
- Out-of-scope and malformed flow URLs are ignored before persistence, and the
  recorder reports only counts for recorded, out-of-scope, and malformed flows.
- Request and response body summaries decode textual media types, summarize
  multipart bodies with a redacted media-type placeholder before persistence,
  keep binary bodies as size-only records, and reuse the global traffic body
  limit.
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
- Multipart request and response bodies. File fields, token fields, and
  harmless text fields are not persisted; the body text is replaced with a
  redacted media-type summary.

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
| `agent_run_manifest` | Value-free AI-assisted Architect run evidence |
| `traffic_artifact_approval` | Value-free approval evidence for generated traffic-derived artifacts |
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
| `--dry-run` | Preview selected redacted records, output paths, golden status, and redaction categories without writing artifacts |
| `--include-host api.example.test` | Include only captured requests for an exact host |
| `--exclude-method OPTIONS` | Exclude a noisy HTTP method before generation |
| `--include-path /checkout` | Include a request path prefix or glob pattern |
| `--exclude-path "/assets/*"` | Exclude a noisy request path pattern before generation |

Generated tests should parameterize volatile fields such as IDs and timestamps. Golden assertions should avoid locking unstable values unless explicitly requested.

Mock generation selects records by safe service selector, matching either an
exact host such as `payments.example.test` or the first host label such as
`payments`. Entroping generates mappings for standard mock servers such as
WireMock; it does not become the mock server itself.

`freeze` and `freeze --mock` write review manifests under `reports/approvals/`.
The manifest uses schema `entroping.traffic-artifact-approval.v1` and records
generated artifact paths, SHA-256 checksums, deterministic source session
fingerprints, source record fingerprints, and counts-only redaction summaries,
including low-confidence record counts.
It must not store raw traffic state, URLs, headers, query values, request or
response bodies, local env files, generated artifact contents, provider
credentials, or approval decisions.

`freeze --dry-run` performs the same redacted traffic selection and generated
path resolution as the write path, then prints a value-free preview. It does
not write Hurl files, WireMock mappings, approval manifests, or source
artifacts, and it must not print raw secrets, cookies, tokens, request bodies,
or unredacted query values.

Capture filters are applied after redaction and before Hurl, WireMock, or graph
compilation. Include filters narrow by host, method, and path; exclude filters
win. Host filters are exact, method filters normalize to uppercase, and path
filters match request paths only. Query strings, headers, cookies, and bodies
are not filter output and must not appear in empty-filter or validation errors.

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
with an actionable missing-renderer message otherwise. The same capture filters
used by `freeze` can narrow map exports before graph compilation. PNG exports
also write `reports/approvals/dependency-map-png.json` with the same
value-free traffic artifact approval schema used by `freeze`.

## 13. Reporting Design

Reports are written under `reports/`.

| Report | Command | Purpose |
| --- | --- | --- |
| HTML | `run --report html` | Human review |
| JUnit XML | `run --report junit` | CI systems |
| JSON | `run --report json` | Tooling integration |
| Drift JSON | `run --drift-check` or `--report drift` | `.entroping/drift-baseline.json` comparison |
| Audit Markdown/JSON | `architect audit --output md|json` | OpenAPI operation-to-Hurl coverage matrix |
| Drift Baseline Promotion | `report promote-drift-baseline` | Reviewed candidate promotion |
| Bug Markdown | `report bug` | Issue tracker handoff |
| Run Delta | `report delta` | Run-to-run regression delta for PR review |
| Coverage Badges | `report badges` | Local Shields endpoint JSON from existing reports |
| Redaction Review | `report redaction --output md|html` | Captured-traffic redaction coverage review |
| Capture Summary | `report capture-summary --output md|json` | Counts-only captured-traffic session summary |
| Effective Policy | `report policy --output md|json` | Resolved QAnstitution gate provenance |
| Effective Policy Diff | `report policy-diff --base <path> --current <path> --output md|json [--fail-on-change]` | Import/gate differences between two effective-policy JSON artifacts; opt-in CI failure on changed diff |
| Artifact Manifest | `report artifact-manifest` | Checksum manifest for local report artifacts |
| Agent Review Bundle | `report agent-bundle` | Local Builder/Breaker/Auditor evidence from sanitized manifests |
| Traceability Markdown/JSON | `report traceability --output md|json` | Local story/test coverage review |
| GitHub Annotations | `report github-annotations` | Pull request workflow-command annotations |
| SARIF | `report sarif` | Code-scanning import for local Entroping findings |
| Review Summary | `report review-summary` | Provider-neutral Markdown from local report artifacts |

JUnit is required because it is the common denominator for CI. Allure can consume JUnit later. JaCoCo is not a fit because Entroping is black-box runtime testing, not code coverage instrumentation.
HTML report rendering must escape all dynamic header and row content, including
project, environment, generated timestamp, summary text, test paths, statuses,
rule IDs, known-failure summaries, and captured Hurl output.

## 14. CLI Contracts

Compatibility audit: [CLI_COMPATIBILITY_AUDIT.md](CLI_COMPATIBILITY_AUDIT.md).

### Setup

```text
entroping init [--minimal] [--github-actions]
entroping doctor [--ci] [--output <text|json>]
entroping config list
entroping config set --agent <builder|auditor|breaker> --model <model-id>
entroping config vendor-policy-pack --pack <path> [--name <dir>]
entroping config test-policy-pack --pack <path> [--output <text|json>]
```

`init --github-actions` is an explicit opt-in setup path. It installs the
packaged, reviewed starter workflow to `.github/workflows/entroping.yml` using
create-only path handling, rejects symlinked workflow path components, and
refuses to overwrite an existing workflow. The starter uses pinned Hurl guidance
and installs Entroping from the latest GitHub source branch by default, with an
explicit `ENTROPING_INSTALL_SPEC` override for teams that want to pin a reviewed
tag; it does not add secrets, provider credentials, hosted-service coupling, or
PyPI/TestPyPI readiness claims.

A future reusable `entroping/action` must stay separate from the generated
starter workflow until package-index install proof exists. The action belongs
in a dedicated action repository, installs released Entroping artifacts or an
explicit tagged prerelease fallback, installs or verifies Hurl, uploads local
`reports/` artifacts without `.entroping/` state by default, keeps optional PR
comments permission-scoped, and must not call LLM providers during
`entroping run --ci`.

`doctor --output json` emits schema version `entroping.doctor.v1` with overall
status, Python version, Hurl and hurlfmt availability, Hurl compatibility
evidence, traffic-state health, QAnstitution health, and agent-readiness
entries. Hurl compatibility states are `compatible`, `missing`, `unsupported`,
and `unparsable`; the check runs only `hurl --version`, never API requests.
Warning states such as missing Hurl, unsupported or unparsable Hurl versions,
missing config, missing traffic state, or missing configured `api_key_env`
values keep the human-compatible `0` exit code; invalid QAnstitution, invalid
traffic state, or unsafe configured personas exit `1`.

`doctor --ci` adds strict CI-readiness evidence to the same human and JSON
doctor contract. It validates Hurl availability and compatibility, safe
`.entroping/` and `reports/` artifact paths, committed suite manifests, required
Hurl variables from suite env files or `HURL_VARIABLE_*`, and the provider-free
`run --ci` boundary. It does not call external CI provider APIs, mutate workflow
files, print env values, or require Architect provider keys.

`config set` updates non-secret routing metadata only. If the selected agent's
persona file is missing, it creates a local Markdown template under the configured
relative source path after rejecting absolute paths, traversal, symlinks, non-Markdown
paths, URLs, and control characters.

`config vendor-policy-pack` copies a reviewed local policy-pack directory under
`policy-packs/<name>/`, validates its `entroping-policy-pack.yaml` manifest and
QAnstitution entrypoint before writing, then appends a local import to
`qanstitution.yaml`. It is local-only: it does not fetch HTTP imports, consult a
registry, authenticate to a catalog, or add runtime manifest dependency.

`config test-policy-pack` validates a local policy-pack directory without
copying it, editing `qanstitution.yaml`, consulting a registry, requiring
network access, or requiring provider keys. It emits pass/fail checks for safe
source boundaries, manifest/entrypoint/gate/final-gate consistency,
consumer-example loading, and local-only execution. JSON output uses schema
`entroping.policy-pack-self-test.v1` with artifact type
`policy-pack-verification`.

`doctor` validates configured agent persona files through the same root-bounded
persona loader used by Architect commands. It reports unsafe, missing,
oversized, unreadable, non-Markdown, control-character, and secret-like persona
content as setup failures. It may report whether configured `api_key_env`
environment-variable names are present, but it must not print values or call
providers.

### Intelligence

```text
entroping architect build [--new] [--changed-from <ref>] [--prompt <text>] [--strategy merge] [--tag <tag>] [--agent <builder|breaker>]
entroping architect refactor --target <glob> --prompt <text> [--preview]
entroping architect audit [--focus <logic|auditor>] [--output <json|md>] [--changed-from <ref>]
```

`architect audit --focus logic` is a deterministic bridge report. It compares
OpenAPI operations with committed Hurl metadata and request lines, emits
covered, uncovered, and ambiguous operation rows, and lists stale
`operation_id` references. Generated negative-path Hurl evidence is reported
separately from positive/non-negative coverage so it does not make an operation
look happy-path covered. When `.entroping/state.db` contains redacted Eye
traffic, the same audit also compares captured route summaries against OpenAPI
path templates and reports documented, undocumented, and spec-only routes
without raw query strings, headers, cookies, bodies, host userinfo, or captured
values. JSON output carries schema marker `entroping.openapi-audit.v1`; the
nested traffic route section uses `entroping.traffic-openapi-audit.v1`.
`architect audit --focus logic --changed-from <ref>` also compares the
configured local OpenAPI spec against the same file at a Git base ref and
attaches `entroping.openapi-breaking-diff.v1` findings for removed or added
operations, method/path moves, response status changes, newly required request
parameters or body fields, and practical top-level JSON response-shape changes.
The diff audit is deterministic, LLM-free, report-only, and never generates,
deletes, or overwrites tests.

`architect build --new --changed-from <ref>` compares the configured local
OpenAPI spec against the same spec at a Git base ref, classifies added,
modified, renamed, removed, and unchanged operations, and regenerates only the
current added/modified/renamed operation IDs. Removed operations are reported
for manual review; Entroping does not delete existing tests automatically.

`architect build --new` also compiles deterministic auth-negative coverage for
OpenAPI operations that declare security requirements and an explicit `401` or
`403` response. Supported schemes are HTTP bearer/basic and API-key
header/query/cookie. Generated files live under `tests/generated/security/`
with `security`, `security_scheme`, `negative_category=invalid-auth`,
`severity`, and safety metadata. Unsupported schemes, missing scheme
definitions, and operations without explicit auth-failure responses are
reported as warnings rather than guessed.

For JSON request bodies with explicit `400` or `422` responses,
`architect build --new` also emits bounded schema-derived negative tests under
`tests/generated/negative/`. These files are tagged `negative` plus their
category (`malformed-json`, `schema-violations`, `boundary-values`,
`sqli-like-strings`, or `idor-path-variants`; auth-negative files use
`invalid-auth`) and include
`negative_category`, `severity`, and safety metadata so reports and suites can
distinguish generated negative coverage from spec-derived happy paths.

### Observation

```text
entroping watch [--port <port>] [--target <url>] [--scope-host <host> ...] [--scope-url-prefix <url> ...]
entroping freeze --name <flow> [--golden] [--mock <service>] [--dry-run] [capture filters]
entroping map [--export <mermaid|dot|md|png>] [capture filters]
```

### Execution and Reporting

```text
entroping studio [--env <name>]
entroping run [--env <name>] [--suite <name>] [--tag <tag>] [--tag-expression <expr>] [--operation-id <id>] [--ci] [--parallel] [--fail-fast] [--dry-run] [--report <html|junit|json|drift> ...] [--drift-check] [--changed-from <ref>] [--rerun-failures]
entroping report bug
entroping report failure-bundle [--output <directory>]
entroping report delta [--base <path>] [--current <path>] [--output <md|json>]
entroping report badges [--output <directory>] [--run-json <path>] [--policy-json <path>] [--openapi-json <path>] [--traceability-json <path>]
entroping report redaction [--output <md|html>]
entroping report capture-summary [--output <md|json>]
entroping report policy [--output <md|json>]
entroping report policy-diff [--base <path>] [--current <path>] [--output <md|json>] [--fail-on-change]
entroping report gate-coverage [--output <md|json>]
entroping report gate-injection --target <path> [--output <md|json>]
entroping report artifact-manifest [--output <path>]
entroping report agent-bundle [--output <md|json>] [--role <builder|auditor|breaker>] [--scope <path>]
entroping report traceability [--output <md|json>]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
entroping report sarif [--output <path>] [--junit <path>] [--drift <path>] [--traceability]
entroping report promote-drift-baseline [--candidate <path>] [--output <path>]
entroping report review-summary [--output md] [--junit <path>] [--run-json <path>] [--drift <path>] [--traceability]
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
not start `watch`, control live capture, or render raw URLs with query values, headers, bodies, cookies, tokens, or secrets.
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
`--fail-fast` stops scheduling new Hurl files after the first failing result.
Sequential fail-fast executes tests in selection order and stops immediately.
Parallel fail-fast remains bounded by `settings.parallel_workers`: already
scheduled workers may complete, but Entroping schedules no additional tests
after the first failure is observed. Latest-run state and requested reports
include only executed tests and record `selected`, `executed`, `not_scheduled`,
and `fail_fast` summary evidence. Normal full runs omit those suite-level
scheduling fields from JSON, JUnit, and HTML because the ordinary totals already
describe the run.
Protected-environment safety preflight runs after Hurl discovery and temporary
gate injection but before variable preflight and Hurl subprocess execution.
Environment names listed in `settings.protected_environments` default to
`prod`, `production`, and `protected`; named suite manifests can also force the
classification with `protected: true`. In protected runs, `GET`, `HEAD`, and
`OPTIONS` are treated as read-only. `POST`, `PUT`, `PATCH`, `DELETE`, and
unknown methods are mutating and fail closed unless the selected test or suite
declares reviewed safety metadata: `read-only`, `idempotent`, or
`teardown-backed`. A selected test can declare this through
`# entroping: safety=<value>` or an equivalent safety tag. `destructive`
metadata always blocks in protected environments and overrides suite defaults.
Blocked runs do not call Hurl. They write latest-run state and requested JSON,
JUnit, or HTML reports with status `blocked`, method-level safety evidence, and
value-free reasons; they do not print request URLs, headers, bodies, cookies,
or variable values.
`--dry-run` builds a deterministic execution plan and stops before Hurl
execution. It loads QAnstitution, resolves suite/tag/tag-expression/operation
ID/changed-from/rerun selectors, loads environment variable names, writes
temporary gate-injected execution copies only in a disposable temp directory,
summarizes selected paths, skipped counts, report formats, effective and
injected gate rule IDs, worker/timeout/retry settings, and missing variable
names, then removes the temporary copies. It must not invoke Hurl, write
`.entroping/latest-run.json`, write `.entroping/latest-run-events.jsonl`, write
JUnit/HTML/drift/run JSON reports, or mutate source `.hurl` files. With
`--report json`, dry-run writes `reports/run-plan.json` using schema
`entroping.run-plan.v1`; requested executed-report paths are included only as
`would_write` evidence.
`settings.retry` is a bounded per-file subprocess retry budget. `entroping run`
stops retrying as soon as a Hurl file passes, never hides a final failure, and
records retry evidence in JSON, JUnit, HTML, and review-summary artifacts.
Retry evidence contains attempt number, status, exit code, duration, and
truncation flags only; it must not copy raw per-attempt stdout or stderr into
the evidence block.
Every executed test row also records the effective Hurl subprocess
`timeout_ms`. Subprocess timeouts use status `timeout`, exit code `124`, a
timeout-specific JUnit failure type, and timeout findings in review summaries so
operators can distinguish time-budget failures from Hurl assertion failures.
Every run also writes `.entroping/latest-run-events.jsonl`, a sanitized JSONL
progress log using schema `entroping.run-events.v1`. Events include run start,
selected test paths, safe tags and rule IDs, per-test status/duration/timeout
evidence, artifact paths, no-match or error events, and completion status. The
log omits variables and raw passing stdout/stderr; failed stdout/stderr and
error messages use the existing Hurl output redaction path. The writer resets
stale latest-run event evidence with a safe first-line write, then appends each
subsequent JSONL event line through the same root and symlink safety checks so
large runs do not repeatedly rewrite accumulated evidence. A crash during
append may leave one incomplete trailing line; run-event readers recover the
complete JSONL prefix and reject malformed completed lines.
Because latest-run state, latest reports, and latest event logs are singleton
project artifacts, concurrent `entroping run` invocations in one project root
fail fast before Hurl execution when another run already owns the latest
event-log writer lock. This preserves complete latest evidence instead of
interleaving two runs into one audit stream.
`--changed-from <ref>` uses `git diff --name-status` to select existing changed
`.hurl` files from a base ref. Deleted files are skipped, rename targets are
used, and paths outside the project root are rejected before discovery. This is
for fast local and agent feedback only; CI release gates should keep running the
full deterministic suite.
`--rerun-failures` reads `reports/run-latest.json` first and falls back to
`.entroping/latest-run.json`, selects failed source `.hurl` paths that still
exist inside the project, rejects malformed reports, path escapes, symlinked
paths, missing files, non-Hurl paths, and zero-failure reports before execution,
and feeds those paths into the same Hurl discovery, gate injection, env loading,
variable preflight, subprocess runner, and report writers. It reuses the report
environment unless `--env` overrides it, and it cannot be combined with
`--suite`, `--tag`, `--tag-expression`, `--operation-id`, or `--changed-from`.
`--operation-id <id>` is a repeatable deterministic selector over committed
Hurl `operation_id` metadata. It cannot be combined with suite, changed-from,
rerun-failures, tag, or tag-expression selectors, and run reports preserve
optional per-test operation ID evidence in JSON, JUnit, and HTML artifacts.
`--suite <name>` loads a committed `suites/<name>.yaml` manifest with schema
version `entroping.suite.v1`. A suite can define `env`, `tags`, root-bounded
`paths` globs, `reports`, `parallel`, `fail_fast`, `drift_check`, `protected`,
and `safety`. The suite manifest feeds the same deterministic run workflow; it does not change default
`entroping run` behavior, and it cannot be combined with ad hoc selectors such
as `--env`, `--tag`, `--report`, `--parallel`, `--fail-fast`, `--drift-check`,
`--changed-from`, or `--rerun-failures`.
Before Hurl starts, the run workflow scans selected temporary execution copies
for unresolved `{{variable}}` references. Resolved variables can come from
`envs/<name>.env`, explicit shell `HURL_VARIABLE_<name>` values, Hurl
`[Options] variable` entries, captures, or known Hurl built-ins. Missing-variable
errors must list names and paths only; they must not print variable values.
Auth chaining stays inside this deterministic Hurl/env boundary. Hurl files may
declare value-free `# entroping: auth_flow=<id>`,
`# entroping: auth_requires=<var>[,<var>]`, and
`# entroping: auth_produces=<var>[,<var>]` metadata to describe local token,
cookie, or CSRF setup. The metadata stores identifiers and variable names only:
captures and variable substitution remain Hurl behavior, secret values come from
env variables, secret managers, or gitignored env files, and run plans plus
JSON/JUnit/HTML reports expose only names.
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
`entroping report promote-drift-baseline` is the explicit human-reviewed
promotion step. It reads `reports/drift-baseline.candidate.json` by default,
requires the current `entroping.drift-baseline.v1` schema, rejects unsafe paths
and malformed candidates, then atomically writes `.entroping/drift-baseline.json`.

`entroping report delta` compares two local JSON run reports without executing
Hurl, calling model providers, or uploading results. It emits Markdown or JSON
with schema version `entroping.run-delta-report.v1`, sorted added failures,
resolved failures, changed failures, unchanged failures, latency deltas, and
policy-gate deltas. The command exits `1` when the current run introduces added
or changed failures, exits `0` when failures only resolve or stay unchanged,
and never renders raw stdout, stderr, headers, bodies, prompts, provider data,
or secrets.

`entroping run` resolves selected source `.hurl` files only after rejecting
leaf symlinks and symlinked user-selected path components while tolerating
host-level filesystem aliases such as macOS `/var -> /private/var`.
`entroping report gate-injection --target <path>` resolves the effective
QAnstitution, parses selected local Hurl metadata, and writes
`reports/gate-injection.md` or `reports/gate-injection.json` showing gate ID,
source policy path, condition, assertion, enforcement, final/group provenance,
target file, and active known-failure skips without running Hurl or mutating
source `.hurl` files. Targets are root-bounded local `.hurl` files; symlinked
targets, path escapes, missing files, and non-Hurl files are rejected before
report writing.

`entroping report gate-coverage --output md|json` resolves the effective
QAnstitution, discovers committed local Hurl tests under `tests/`, and writes
`reports/gate-coverage.md` or `reports/gate-coverage.json` showing each gate's
matching test files, tags, operation IDs, methods, and redacted paths. It is
policy coverage evidence only: it does not execute Hurl, inject temporary
assertions, evaluate pass/fail, call providers, or render full URLs, query
strings, headers, bodies, variables, or captured traffic values.

`entroping report artifact-manifest` writes `reports/artifact-manifest.json`
by default with project-relative report paths, schema versions when available,
artifact sizes, and SHA-256 checksums for standard JSON, JUnit, HTML, drift,
agent-bundle JSON, SARIF, and review-summary artifacts. Missing expected
artifacts are listed instead of failing the command. Each successful write also
appends a value-free event to `.entroping/report-audit-chain.jsonl` with the
previous event hash, artifact checksums, command metadata, schema versions, and
manifest summary counts. The manifest exposes audit verification status and
broken-chain diagnostics, while the chain and report omit artifact contents,
raw traffic, provider prompts or outputs, env values, and secret-like metadata.
This is local integrity evidence for CI upload and release review; it is not a
signing, notarization, or attestation system.

`entroping report badges` writes local Shields endpoint JSON files under
`reports/badges/` by default. It reads existing local reports only:
`reports/run-latest.json`, `reports/effective-policy.json`,
`reports/openapi-audit.json`, and `reports/traceability.json`. Policy-gate
coverage is the number of effective QAnstitution gate IDs observed in the run
report, OpenAPI coverage comes from the deterministic OpenAPI audit summary,
and story-link coverage comes from traceability JSON over local Hurl metadata
and `docs/stories/*.md` story documents. Missing or malformed source reports
fail before badge files are written. The command does not call shields.io, host
a badge service, upload artifacts, execute Hurl, or render raw report
stdout/stderr.

`entroping report review-summary` writes a provider-neutral Markdown artifact
from local reports only. It reads the JSON run report, JUnit XML, drift JSON,
and optional local traceability metadata, then writes `reports/review-summary.md`
for CI logs, uploaded artifacts, or pull-request comments created by the user's
CI system. The command does not call GitHub, GitLab, Buildkite, Linear, Jira, or
any model provider; posting or uploading the Markdown remains a downstream CI
step. Missing artifacts are recorded as missing instead of failing the command,
while malformed artifacts fail with a clear report error. Rendered findings are
redacted and Markdown-escaped.
Unstable pass-after-retry run evidence is rendered as a warning; retried tests
with unchanged final failure/pass state are rendered as notice-level context.

`entroping report agent-bundle` writes a local multi-agent review bundle from
sanitized `.entroping/agent-runs/*.json` manifests. It defaults to configured
Builder, Breaker, and Auditor roles, supports repeatable `--role` filters and a
project-relative `--scope`, and writes `reports/agent-bundle.md` or
`reports/agent-bundle.json` with schema
`entroping.agent-review-bundle.v1`. The command does not call model providers
or Hurl and is not read by `entroping run`. It reports missing role config,
missing local role evidence, malformed or secret-like manifests, invalid
provider output validation evidence, missing generated-Hurl validation, and
multi-role output-path conflicts as review findings instead of resolving them
with an LLM. Rendered evidence is value-free: role/model/persona metadata,
output paths, validation flags, usage, and cost estimates only; it excludes raw
prompts, provider responses, persona content, traffic, env values, cookies, and
credentials. Prompt hashes remain available in the source agent-run manifests.

`entroping report failure-bundle` writes a sanitized local handoff directory at
`reports/failure-bundle` by default. It requires a latest failed run, refuses
passing runs, and includes a manifest, sanitized run JSON, generated bug
Markdown, selected failed-test Hurl metadata, and any already-reviewed local
JUnit, HTML, effective-policy, or redaction-review artifacts that exist. It does
not include raw traffic databases, local env files, source Hurl contents, or
upload anything to external services. The manifest records included artifact
paths, source paths, schema versions, sizes, and SHA-256 hashes.

`entroping report sarif` writes SARIF 2.1.0 to `reports/entroping.sarif` by
default. It converts the same local JUnit, drift, and optional traceability
findings used by GitHub annotation output into stable SARIF rule IDs, severity,
message text, and best-effort file locations. The command does not execute
Hurl, call providers, or upload results; downstream CI remains responsible for
uploading the SARIF artifact to code scanning. Finding text and locations are
redacted before serialization, and absolute project-root paths are relativized.

### Report Artifact Contracts

| Command | Artifact | Stability note |
| --- | --- | --- |
| `entroping run` | `.entroping/latest-run.json` | Runtime state for follow-up report commands; uses `entroping.run-report.v1`; not committed. |
| `entroping run` | `.entroping/latest-run-events.jsonl` | Sanitized execution progress events using `entroping.run-events.v1`; not committed. |
| Prompt-backed `entroping architect ...` | `.entroping/agent-runs/*.json` | Value-free AI run evidence using `entroping.agent-run-manifest.v1`, including source-evidence hashes; not committed and not read by `run`. |
| `entroping freeze` / `freeze --mock` / `map --export png` | `reports/approvals/*.json` | Value-free approval evidence for generated traffic artifacts using `entroping.traffic-artifact-approval.v1`. |
| `entroping run --report json` | `reports/run-latest.json` | Machine-readable run report using `entroping.run-report.v1`. |
| `entroping run --report junit` | `reports/junit.xml` | CI-compatible test report. |
| `entroping run --report html` | `reports/run-latest.html` | Human-readable local report. |
| `entroping run --report drift` | `reports/drift.json` | Machine-readable drift findings using `entroping.drift-report.v1`. |
| `entroping run --report drift` | `reports/drift-baseline.candidate.json` | Reviewable sanitized baseline candidate after a passing Hurl suite. |
| `entroping report promote-drift-baseline` | `.entroping/drift-baseline.json` | Active local drift baseline promoted from a reviewed candidate. |
| `entroping report bug` | `reports/bug.md` | Markdown handoff for issue trackers. |
| `entroping report failure-bundle` | `reports/failure-bundle/manifest.json` | Sanitized local handoff bundle using `entroping.failure-bundle.v1`. |
| `entroping report delta --output md|json` | `stdout Run Delta Markdown/JSON` | Run-to-run regression delta using `entroping.run-delta-report.v1`. |
| `entroping report badges` | `reports/badges/*.json` | Local Shields endpoint JSON for policy, OpenAPI, and traceability coverage. |
| `entroping report redaction --output md` | `reports/redaction-review.md` | Counts-only captured-traffic redaction review. |
| `entroping report redaction --output html` | `reports/redaction-review.html` | Browser-readable captured-traffic redaction review. |
| `entroping report capture-summary --output md` | `reports/capture-summary.md` | Counts-only captured-traffic session summary for freeze review. |
| `entroping report capture-summary --output json` | `reports/capture-summary.json` | Machine-readable capture summary using `entroping.capture-summary.v1`. |
| `entroping report policy --output md` | `reports/effective-policy.md` | Human-readable resolved QAnstitution gate provenance. |
| `entroping report policy --output json` | `reports/effective-policy.json` | Machine-readable effective policy evidence using `entroping.effective-policy-report.v1`. |
| `entroping report policy-diff --output md|json` | `stdout Effective Policy Diff Markdown/JSON` | Import and gate differences between two effective-policy JSON artifacts using `entroping.effective-policy-diff.v1`; `--fail-on-change` exits `1` when the status is changed. |
| `entroping report gate-coverage --output md` | `reports/gate-coverage.md` | Human-readable policy gate coverage matrix for committed Hurl tests. |
| `entroping report gate-coverage --output json` | `reports/gate-coverage.json` | Machine-readable policy gate coverage matrix using `entroping.gate-coverage-report.v1`. |
| `entroping report gate-injection --output md` | `reports/gate-injection.md` | Human-readable gate-injection explanation for selected Hurl files. |
| `entroping report gate-injection --output json` | `reports/gate-injection.json` | Machine-readable gate-injection explanation using `entroping.gate-injection-report.v1`. |
| `entroping report artifact-manifest` | `reports/artifact-manifest.json` and `.entroping/report-audit-chain.jsonl` | Machine-readable checksum manifest using `entroping.report-artifact-manifest.v1` plus a local tamper-evident audit chain using `entroping.report-audit-event.v1`; the chain is local state and not committed. |
| `entroping report agent-bundle --output md` | `reports/agent-bundle.md` | Human-readable local multi-agent review bundle from sanitized manifests. |
| `entroping report agent-bundle --output json` | `reports/agent-bundle.json` | Machine-readable local multi-agent review bundle using `entroping.agent-review-bundle.v1`. |
| `entroping report traceability --output md|json` | `stdout Markdown/JSON` | Local story/test coverage report. |
| `entroping report github-annotations` | `stdout GitHub Actions annotations` | Workflow-command annotations from JUnit, drift, and optional traceability findings. |
| `entroping report sarif` | `reports/entroping.sarif` | SARIF 2.1.0 code-scanning evidence from JUnit, drift, and optional traceability findings. |
| `entroping report review-summary` | `reports/review-summary.md` | Provider-neutral Markdown summary from local JSON, JUnit, drift, and optional traceability evidence. |

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
- Logs and reports must redact known secret patterns, including bearer tokens,
  cookies, API keys, and CSRF token key/value forms.
- LLM prompts must not include secrets.
- Traffic persistence must apply redaction before storing raw data.

## 16. Error Handling

Errors must be explicit and actionable:

- Missing Hurl binary: tell user how to install or configure it.
- Missing Hurl variables: fail before subprocess execution and list missing
  names without values.
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
- Auth-chain flow IDs and Hurl variable names, never token or cookie values.
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
uv run python scripts/local_wheel_install_smoke.py --skip-build
uv run python scripts/downstream_smoke.py
```

The package check builds wheel/sdist artifacts with `uv build` and inspects
metadata for project name, version, SPDX license expression, license file
presence, alpha maturity classifiers, and the `entroping/py.typed` PEP 561
marker in both artifacts. It also verifies the packaged GitHub Actions starter
template required by `entroping init --github-actions`. It does not publish to
PyPI/TestPyPI and must not require package-index credentials.

The local wheel install smoke reuses the built wheel, creates an external
temporary virtual environment and project, installs the wheel through
`uv pip install --offline`, and runs only installed public CLI commands:
`entroping --version`, `entroping init --minimal`, and `entroping doctor`.
The smoke emits `entroping.local-wheel-install-smoke.v1` evidence and remains
separate from TestPyPI/PyPI package-index proof.

The downstream smoke creates a separate temporary API project and executes
`entroping run --ci` from that project through the public CLI. It is a local
release-gate proof that the core works outside its own checkout, while real
downstream user feedback remains a separate stable-core blocker.

Release evidence is recorded in `docs/meta/release-evidence.json` and validated
offline with `uv run python scripts/release_evidence.py --strict`. Maintainers
can optionally run
`uv run python scripts/release_evidence.py --check-freshness --strict` to
compare recorded CI and Pages run IDs/commits against the latest successful
GitHub Actions runs on `main`. That freshness path is read-only, reports
unavailable GitHub CLI/auth states clearly, and never updates the ledger
automatically.

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

Docker CI images are also deferred until package-index proof exists. A future
GHCR image should be a Linux CI convenience with pinned Entroping, Hurl, and
hurlfmt versions, a non-root runtime user, OCI labels/provenance, immutable tags
and digest pinning, rollback rules, and smoke checks. It must not replace local
`uv tool install`, PyPI, source checkout, or later Homebrew paths.

### Later Distribution

- Nuitka standalone binary.
- Homebrew formula.
- PyPI package.
- Docker image for CI runners after package-index proof.
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
