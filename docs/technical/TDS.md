---
title: Entroping Technical Design Specification
description: Alpha technical design; stable-core readiness remains blocked.
type: technical
status: active
tags:
  - architecture
  - technical-design
---

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
- `core/evidence/`, `core/readiness/`, `core/plan/`, and `core/export/`
  group local report packet implementation families; existing
  `entroping.core.<module>` paths remain compatibility shims until callers
  migrate deliberately.
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
    openapi_to_hurl/
      __init__.py
      compiler.py
      models.py
      parameters.py
      schema.py
      validation.py
    traffic_to_hurl.py
    traffic_to_wiremock.py
    traffic_to_graph.py
    graphql_to_hurl.py
    policy_to_hurl.py
    story_traceability.py
    merge.py
  core/
    evidence/
    readiness/
    plan/
    export/
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
source file, source group, import chain, and value-free source digest evidence
for every expanded gate. Imported documents expand their groups before merge,
so duplicate IDs and `final: true` protections keep the same behavior as
directly-authored imported gates.

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

`bridge/` is a set of small compilers and analyzers, not a dumping ground. The
current top-level inventory is:

| Module | Owns | Must not own |
| --- | --- | --- |
| `capture_summary.py` | Safe aggregate summaries from redacted captured traffic | Proxy capture, SQLite persistence, raw body retention |
| `effective_policy.py` | Effective QAnstitution policy evidence rendering | Policy loading, filesystem writes outside the report adapter |
| `effective_policy_diff.py` | Effective-policy evidence diffs | Policy mutation, compatibility decisions |
| `gate_coverage.py` | QAnstitution gate coverage over discovered Hurl tests | Hurl subprocess execution, report file writes |
| `gate_injection_explain.py` | Gate-injection explanation reports | Temporary execution-copy creation, Hurl execution |
| `asyncapi_to_hurl.py` | AsyncAPI webhook-ack Hurl scaffold from local contract metadata | Broker/cloud/webhook execution, message delivery, file writes |
| `graphql_to_hurl.py` | GraphQL SDL typename-smoke Hurl scaffold from local schema metadata | GraphQL runtime execution, resolver calls, file writes |
| `merge.py` | Manual-edit-preserving Hurl merge/refactor logic | Test generation strategy |
| `openapi_audit.py` | OpenAPI operation coverage audit against Hurl tests | File discovery, Hurl execution, LLM calls |
| `openapi_diff.py` | Pure OpenAPI operation-change detection | Git invocation, file reads, generated-test writes |
| `openapi_to_hurl/` | OpenAPI operation/schema/parameter translation to Hurl models through bounded compiler modules | LLM calls, file writes, merge strategy |
| `policy_to_hurl.py` | QAnstitution gate to Hurl assertions | Hurl subprocess execution |
| `proto_to_hurl.py` | Proto HTTP-transcoding Hurl scaffold | Native gRPC, streaming, proto detail rendering |
| `redaction_review.py` | Safe redaction review summaries from redacted traffic | Raw traffic capture, secret storage |
| `soap_to_hurl.py` | Local WSDL to SOAP smoke Hurl scaffold | SOAP runtime, network execution, WSDL detail rendering |
| `story_traceability.py` | Story IDs, local story Markdown files, owners, external doc URLs | Business-system API clients |
| `target_to_hurl.py` | Single target URL smoke-test Hurl scaffold | Network execution, CLI file writes, non-read-only HTTP methods |
| `test_pyramid.py` | Local test-pyramid evidence summaries | Test execution, artifact generation |
| `test_quality.py` | Deterministic quality reports for generated Hurl tests | Hurl parsing side effects, source mutation |
| `traffic_openapi_audit.py` | Redacted traffic route audit against OpenAPI operations | Traffic persistence, OpenAPI file loading |
| `traffic_sessions.py` | Pure traffic filtering and session candidate transformations | Database access, proxy capture |
| `traffic_to_hurl.py` | Redacted traffic session to Hurl models | mitmproxy capture, SQLite persistence |
| `traffic_to_wiremock.py` | Redacted dependency traffic to WireMock mappings | Filesystem writes, mock server runtime |
| `traffic_to_graph.py` | Redacted traffic to dependency graph models | SQLite reads, renderer invocation |

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

### Generated-test QA loop sequence

The planned QA loop for generated changes is a deterministic read-only chain:

- `entroping report test-quality`
- `entroping report mutation-readiness`
- `entroping report qa-brain-seed`
- `entroping report qa-brain-eval-plan`
- `entroping report qa-brain-retrieval-plan`
- `entroping report qa-brain-prompt-plan`
- `entroping report qa-brain-routing-plan`
- `entroping report qa-brain-repair-plan`

Each step records structured local artifacts and advisory planning state only.
None of these packets execute code, call providers for enforcement evidence,
or replace Hurl-based pass/fail behavior.

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
OpenAPI query-array parameter examples/defaults support deterministic
`style: form` rendering: exploded arrays repeat the query key, and
non-exploded arrays join encoded item values with commas. Unsupported array
parameter locations or styles fail closed with explicit guidance instead of
falling back to ambiguous scalar rendering.
OpenAPI operation and path parameters may also reference local reusable
definitions under `#/components/parameters/...`; external, malformed, missing,
non-parameter, or cyclic parameter references fail closed before Hurl is
generated.
OpenAPI request and response bodies are treated as JSON only when the content
map contains exact `application/json` or, if exact JSON is absent, an
`application/*+json` media type such as `application/problem+json` or
`application/merge-patch+json`. Exact `application/json` remains preferred when
both are present; unsupported non-JSON media types are not guessed.

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

- `core.traffic_proxy` lazy-loads mitmproxy so default installs can fail with an actionable optional-dependency message, and rejects vulnerable `msgpack` runtimes before capture starts.
- `TrafficCaptureAddon.response()` records completed HTTP flows only after converting them into `TrafficExchange` models, redacting them, and persisting through `TrafficStore`.
- `watch` fails closed unless an explicit capture scope is configured with
  `--target`, `--scope-host`, or `--scope-url-prefix`.
- `watch --target <url>` scopes capture to the exact normalized target origin,
  while `--scope-host` matches host names case-insensitively and
  `--scope-url-prefix` matches normalized absolute URL prefixes without query
  strings or fragments.
- Out-of-scope and malformed flow URLs are ignored before persistence, and the
  recorder reports only counts for recorded, out-of-scope, and malformed flows.
- Request and response body summaries decode textual media types before
  redaction applies the persistence body limit, summarize multipart bodies with
  a redacted media-type placeholder before persistence, keep binary bodies as
  size-only records, and reuse the global traffic body limit.
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
| `baseline_snapshot` | Drift and golden-master comparison metadata |

Traffic artifact approval evidence is already implemented as value-free JSON
manifests under `reports/approvals/*.json` rather than as a SQLite table.

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
WireMock request mappings preserve redacted query matching: non-sensitive
captured query values are matched exactly, while sensitive or already-redacted
query values require parameter presence without serializing the captured value.

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
`entroping report --help` classifies report commands as launch-critical,
stable-public, maintainer/baseline, or experimental design-partner evidence.
This is a help-discovery boundary only: command names, flags, deterministic
report generation, and artifact schemas remain the compatibility contract.

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
| Redaction Review | `report redaction --output md|html [--fail-on-unsafe]` | Captured-traffic redaction coverage review; opt-in CI failure on unsafe counts |
| Capture Summary | `report capture-summary --output md|json [--fail-on-unredacted]` | Counts-only captured-traffic session summary |
| Effective Policy | `report policy --output md|json` | Resolved QAnstitution gate provenance |
| Effective Policy Diff | `report policy-diff --base <path> --current <path> --output md|json [--fail-on-change]` | Import/gate differences between two effective-policy JSON artifacts; opt-in CI failure on changed diff |
| Generated-Test Quality | `report test-quality --output md|json` | Static quality score for generated Hurl tests |
| Test Pyramid Evidence | `report test-pyramid --output md|json` | Local test/evidence layer summary from existing artifacts |
| External Test Evidence | `report external-test-evidence --output md|json` | Counts-only local ingestion of fixed external JUnit, coverage, LCOV, and SARIF artifacts |
| Artifact Manifest | `report artifact-manifest [--output <path>] [--fail-on-incomplete]` | Checksum manifest for local report artifacts; opt-in CI failure on incomplete evidence |
| Evidence Bundle | `report evidence-bundle` | Sanitized local upload-readiness evidence |
| Design-Partner Feedback | `report design-partner-feedback` | Sanitized local feedback template artifact |
| Runtime Evidence Card | `report runtime-card` | Concise PR/runtime proof card from local reports |
| Cross-Surface Handoff | `report handoff --output md|json [--fail-on-insufficient]` | Local value-free handoff packet for CLI, PR, desktop, cloud, mobile, and agent surfaces; opt-in CI failure when no source artifacts are present |
| Notification Packet | `report notification-packet --output md|json` | Read-only value-free messages for issue tracker, chat, automation, and agent surfaces |
| Team Evidence Readiness | `report team-evidence-readiness --output md|json` | Read-only value-free readiness packet for future team evidence cloud promotion from existing sanitized report artifacts |
| Team Access-Control Plan | `report team-access-control-plan --output md|json` | Read-only value-free role, action, boundary, and audit-event plan for future team evidence surfaces |
| Integration Readiness | `report integration-readiness --output md|json` | Read-only value-free readiness packet for issue tracker, chat, enterprise automation, cross-surface continuity, observability, and API governance surfaces |
| Developer Experience Readiness | `report devex-readiness --output md|json` | Read-only value-free readiness packet for CLI, VS Code/editor, local workbench, PR runtime card, desktop, cloud, and mobile surfaces |
| Evidence Cloud Readiness | `report evidence-cloud-readiness --output md|json` | Read-only value-free readiness packet for future Evidence Cloud upload/export promotion from sanitized local report artifacts |
| Evidence Cloud Export | `report evidence-cloud-export --output md|json` | Local value-free export manifest for future explicit Evidence Cloud upload review from sanitized report metadata |
| Evidence Cloud Workspace | `report evidence-cloud-workspace --manifest <path> --output md|json` | Local value-free workspace dashboard packet from explicit Evidence Cloud export manifests |
| Evidence Cloud Dashboard | `report evidence-cloud-dashboard --manifest <path> --output html|json` | Static local value-free workspace dashboard from explicit Evidence Cloud export manifests |
| Evidence Links | `report evidence-links --output md|json` | Read-only value-free cross-surface link targets for CLI, PR, desktop, cloud, mobile, and agent surfaces from sanitized local evidence artifacts |
| Evidence Portal | `report evidence-portal --output html|json` | Static local value-free evidence dashboard from sanitized report artifacts |
| PR Evidence Card | `report pr-evidence-card --output md|json` | Local value-free PR review card |
| Evidence Action Plan | `report evidence-action-plan --output md|json` | Local value-free prioritized action plan from sanitized evidence-loop artifacts |
| Work Item Draft | `report work-item-draft --output md|json` | Local read-only tracker draft rows from sanitized evidence artifacts |
| Work Item Import Bundle | `report work-item-import-bundle --output json|csv` | Local read-only tracker import rows from the work item draft packet |
| Pilot Outcome | `report pilot-outcome --output md|json` | Local value-free design-partner pilot outcome packet from sanitized evidence artifacts |
| Pilot Cohort | `report pilot-cohort --manifest <path> --output md|json` | Local value-free design-partner cohort rollup from explicit pilot outcome packets |
| Connector Intent | `report connector-intent --output md|json` | Read-only value-free connector intents for issue trackers, chat, enterprise automation, enterprise AI, observability, and developer-experience surfaces |
| OpenTelemetry Mapping | `report otel-mapping --output md|json` | Local value-free mapping packet from sanitized observability and test-evidence artifacts for future OTLP adapters |
| OTLP Preview | `report otlp-preview --output md|json` | Local deterministic OTLP-shaped preview fixture from sanitized run/report evidence; not an exporter |
| Observability Adapter Readiness | `report observability-adapter-readiness --output md|json` | Local value-free readiness packet for future OpenTelemetry, Datadog, Splunk, Grafana, and generic observability adapters |
| Evidence Index | `report evidence-index --output md|json` | Stable value-free local evidence artifact index for cross-surface navigation |
| QA Brain Seed | `report qa-brain-seed --output md|json` | Deterministic value-free seed metadata for future QA Brain retrieval and eval design |
| QA Brain Eval Plan | `report qa-brain-eval-plan --output md|json` | Deterministic eval-case plan metadata for future QA Brain evaluation before fine-tuning |
| QA Brain Retrieval Plan | `report qa-brain-retrieval-plan --output md|json` | Deterministic retrieval-plan metadata for future QA Brain retrieval before embeddings or fine-tuning |
| QA Brain Prompt Plan | `report qa-brain-prompt-plan --output md|json` | Deterministic prompt-plan metadata for future QA Brain prompt design before execution or fine-tuning |
| QA Brain Fine-Tune Readiness | `report qa-brain-fine-tune-readiness --output md|json` | Deterministic fine-tune readiness metadata for future QA Brain proprietary-model experiments before dataset export, training, or provider calls |
| QA Brain Model-Packaging Plan | `report qa-brain-model-packaging-plan --output md|json` | Deterministic model-packaging plan metadata for future hosted, local, and enterprise QA Brain Pro surfaces before endpoints, packages, training, or provider calls |
| QA Brain Routing Plan | `report qa-brain-routing-plan --output md|json` | Deterministic routing-readiness metadata for future LiteLLM/OpenAI-compatible QA Brain Pro surfaces before config changes, endpoints, provider calls, or model invocation |
| QA Brain Repair Plan | `report qa-brain-repair-plan --output md|json` | Deterministic repair-proposal readiness metadata from value-free local quality, mutation, action-plan, routing-plan, and evidence-index states before generation, mutation, or model calls |
| Pilot Metrics | `report pilot-metrics` | Local pilot metric inference from sanitized evidence |
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
values. Ambiguous route-template matches are reported separately and do not
credit all candidate operations as observed. JSON output carries schema marker
`entroping.openapi-audit.v1`; the nested traffic route section uses
`entroping.traffic-openapi-audit.v1`.
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
entroping report redaction [--output <md|html>] [--fail-on-unsafe]
entroping report capture-summary [--output <md|json>] [--fail-on-unredacted]
entroping report policy [--output <md|json>]
entroping report policy-diff [--base <path>] [--current <path>] [--output <md|json>] [--fail-on-change]
entroping report gate-coverage [--output <md|json>] [--fail-under <0-100>]
entroping report gate-injection --target <path> [--output <md|json>]
entroping report test-quality [--output <md|json>] [--fail-under <0-100>]
entroping report test-pyramid [--output <md|json>]
entroping report external-test-evidence [--output <md|json>]
entroping report artifact-manifest [--output <path>] [--fail-on-incomplete]
entroping report evidence-bundle [--output <path>]
entroping report design-partner-feedback [--output <path>]
entroping report runtime-card [--output <md|json>]
entroping report handoff [--output <md|json>] [--fail-on-insufficient]
entroping report notification-packet [--output <md|json>]
entroping report team-evidence-readiness [--output <md|json>]
entroping report team-access-control-plan [--output <md|json>]
entroping report integration-readiness [--output <md|json>]
entroping report devex-readiness [--output <md|json>]
entroping report evidence-cloud-readiness [--output <md|json>]
entroping report evidence-cloud-export [--output <md|json>]
entroping report evidence-cloud-workspace --manifest <path> [--output <md|json>]
entroping report evidence-cloud-dashboard --manifest <path> [--output <html|json>]
entroping report evidence-links [--output <md|json>]
entroping report evidence-portal [--output <html|json>]
entroping report pr-evidence-card [--output <md|json>]
entroping report evidence-action-plan [--output <md|json>]
entroping report work-item-draft [--output <md|json>]
entroping report work-item-import-bundle [--output <json|csv>]
entroping report pilot-outcome [--output <md|json>]
entroping report pilot-cohort --manifest <path> [--output <md|json>]
entroping report connector-intent [--output <md|json>]
entroping report observability-packet [--output <md|json>]
entroping report otel-mapping [--output <md|json>]
entroping report otlp-preview [--output <md|json>]
entroping report observability-adapter-readiness [--output <md|json>]
entroping report api-inventory [--output <md|json>]
entroping report mutation-readiness [--output <md|json>]
entroping report evidence-index [--output <md|json>]
entroping report qa-brain-seed [--output <md|json>]
entroping report qa-brain-eval-plan [--output <md|json>]
entroping report qa-brain-retrieval-plan [--output <md|json>]
entroping report qa-brain-prompt-plan [--output <md|json>]
entroping report qa-brain-fine-tune-readiness [--output <md|json>]
entroping report qa-brain-model-packaging-plan [--output <md|json>]
entroping report qa-brain-routing-plan [--output <md|json>]
entroping report qa-brain-repair-plan [--output <md|json>]
entroping report pilot-metrics [--output <md|json>]
entroping report agent-bundle [--output <md|json>] [--role <builder|auditor|breaker>] [--scope <path>]
entroping report traceability [--output <md|json>]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
entroping report sarif [--output <path>] [--junit <path>] [--drift <path>] [--traceability]
entroping report promote-drift-baseline [--candidate <path>] [--output <path>]
entroping report review-summary [--output md] [--junit <path>] [--run-json <path>] [--drift <path>] [--traceability]
```

`studio` is an interactive read-only Textual TUI. It requires the optional
Studio extra and renders tabs for local QAnstitution status, latest-run summary,
suite rows, failure details, applied-gate drilldowns, a read-only evidence
viewer for report artifacts, and a read-only traffic session browser. The
evidence viewer indexes canonical sanitized report paths with stable evidence
IDs such as `run-json`, `capture-summary-json`, `artifact-manifest-json`,
`evidence-bundle-json`, `runtime-card-json`, `agent-bundle-json`, and
`review-summary-md`. It shows presence, invalid, and unsafe states, controlled
schema metadata, and counts-only summaries; oversized, unreadable, malformed, or
schema-mismatched JSON artifacts are marked invalid without rendering contents.
Studio also derives a read-only pilot readiness panel from
`reports/evidence-bundle.json`, showing schema, bundle status, required artifact
counts, missing/invalid/unsafe diagnostic counts, checksum mismatch count, and
artifact-manifest audit-chain status without opening raw report artifacts,
executing remediation hints, or uploading evidence.
It does not render raw report contents, does not upload artifacts, and does not edit tests, QAnstitution, reports, traffic state, or runtime state.
Applied-gate drilldowns read latest-run report rule IDs and QAnstitution gate definitions; Studio does not run Hurl
and does not edit tests or config to build this view. The traffic browser reads
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
matching test files, tags, operation IDs, methods, and redacted paths.
`--fail-under <0-100>` is an optional CI gate that still writes the requested
report, then exits `1` when matched-gate coverage is below the reviewed
threshold. Coverage is computed from the report summary as
`matched_gates / total_gates * 100`; zero total gates count as `0`. It is policy
coverage evidence only: it does not execute Hurl, inject temporary assertions,
evaluate pass/fail, call providers, or render full URLs, query strings, headers,
bodies, variables, or captured traffic values.

`entroping report test-quality --output md|json` discovers committed generated
Hurl tests under `tests/generated/` or tests carrying generated metadata, then
writes `reports/test-quality.md` or `reports/test-quality.json` with schema
`entroping.test-quality-report.v1`. `--fail-under <0-100>` is an optional CI
gate that still writes the requested report, then exits `1` when the static
score is below the reviewed threshold. The score is static review evidence over
generated test structure: assertion strength, positional selectors, negative
coverage metadata, auth/security metadata, schema-check depth, overfitted
examples, and traceability metadata. It does not execute Hurl, inject gates,
call model providers, upload artifacts, render raw Hurl values, or replace
QAnstitution/Hurl pass-fail authority. A weak score should guide repair
proposals and review; only an explicit threshold turns it into a CI guardrail.

`entroping report test-pyramid --output md|json` reads existing local artifacts
under `reports/`, classifies code coverage, runtime API proof, policy
governance, drift/contract, static/security, and generated-test quality layers,
and writes `reports/test-pyramid.md` or `reports/test-pyramid.json` with schema
`entroping.test-pyramid-report.v1`. Missing, invalid, or unsafe run JSON, JUnit
XML, and gate-coverage JSON artifacts are reported as missing
runtime-governance proof so review can distinguish incomplete evidence from
executed proof. When `reports/external-test-evidence.json` is present with
schema `entroping.external-test-evidence.v1`, the report adds an optional
External Test Evidence layer with counts-only status, layer, test, failure,
error, and skipped totals; a missing packet remains non-blocking, and invalid
or unsafe packets remain value-free layer evidence rather than
runtime-governance findings. The command does not execute Hurl or pytest, parse
source Hurl, call model providers, upload artifacts, render raw artifact
contents, or expose raw traffic, provider prompts, stdout/stderr, env values,
source coverage file names, or raw external test artifact values.

`entroping report external-test-evidence --output md|json` reads only the
fixed local external-test artifact paths under `reports/external-tests/`:
`unit-junit.xml`, `integration-junit.xml`, `component-junit.xml`,
`contract-junit.xml`, `e2e-junit.xml`, `coverage.xml`, `lcov.info`, and
`sarif.json`. It writes `reports/external-test-evidence.md` or
`reports/external-test-evidence.json` with schema
`entroping.external-test-evidence.v1`, source states and hashes, counts-only
JUnit summaries, coverage percentages/counts, SARIF run/result/severity counts,
layer readiness, blockers, and next actions. Missing artifacts are
non-blocking. Malformed, oversized, non-file, symlinked, wrong-format,
out-of-root, or secret-like artifacts are unsafe or invalid. The command does
not execute tests or Hurl, call model or vendor providers, upload artifacts,
mutate external systems, parse raw traffic, render raw test names, stack traces,
source snippets, coverage file names, SARIF messages or locations, stdout or
stderr, prompts, provider outputs, secrets, environment values, webhook URLs,
or full artifact contents, and it does not change `entroping run`.

`entroping report artifact-manifest` writes `reports/artifact-manifest.json`
by default with project-relative report paths, schema versions when available,
artifact sizes, and SHA-256 checksums for standard JSON, JUnit, HTML, drift,
test-quality JSON/Markdown, agent-bundle JSON, SARIF, and review-summary
artifacts. Missing expected artifacts are listed instead of failing the command
unless `--fail-on-incomplete` is set. With that guard, Entroping still writes
the manifest first, then exits `1` when expected artifacts are missing or audit
verification is not `verified`. Present artifacts are size-checked before full
reads, checksums, or schema sniffing; oversized artifacts fail with value-free
path and size-limit metadata instead of loading artifact contents into memory.
Each successful write also appends a value-free event to
`.entroping/report-audit-chain.jsonl` with the previous event hash, artifact
checksums, command metadata, schema versions, and manifest summary counts. The
manifest exposes audit verification status and broken-chain diagnostics, while
the chain and report omit artifact contents, raw traffic, provider prompts or
outputs, env values, and secret-like metadata. This is local integrity evidence
for CI upload and release review; it is not a signing, notarization, or
attestation system.

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

`entroping report evidence-bundle` writes a sanitized local upload-readiness
bundle at `reports/evidence-bundle.json` by default. A `.md` or `.markdown`
output path writes a reviewer-facing Markdown summary from the same sanitized
data model. It verifies that the local run report, effective-policy report, and
artifact manifest exist, use supported schemas, pass their full v1 artifact
contracts, and match manifest checksums where the artifact manifest covers
them. A matching `schema_version` string alone is not enough to mark an
artifact valid. The bundle records project-relative paths, schema versions,
byte sizes, SHA-256 hashes, missing/invalid diagnostics, artifact-manifest
audit-chain status, and deterministic local remediation hints for missing,
malformed, checksum, and unsafe evidence states. Markdown output renders those
hints as next local commands without executing them. The bundle does not embed
artifact contents, raw traffic, source Hurl contents, stdout/stderr, provider
prompts, provider outputs, credentials, environment
values, or upload anything to a hosted service. A `not_ready` bundle is
reviewable evidence of missing or inconsistent local proof, not a cloud upload.

`entroping report design-partner-feedback` writes
`reports/design-partner-feedback.json` by default. It creates a schema-valid
sanitized local template using `entroping.design-partner-feedback.v1`, derives
value-free evidence statuses from existing `reports/evidence-bundle.json`,
`reports/runtime-card.json`, and `reports/pilot-metrics.json` when those
artifacts pass their local contracts, and leaves manual feedback categories as
`null` or `manual input required`; the command-history field also starts as
`manual input required` until a user replaces it with sanitized command
summaries. The command does not execute Hurl, call providers, read raw traffic,
upload artifacts, or claim validated demand, enterprise readiness, hosted
aggregation readiness, or premium policy-pack readiness.

`entroping report runtime-card` writes a concise PR/runtime evidence card at
`reports/runtime-card.md` by default, or `reports/runtime-card.json` with
`--output json`. It reads existing local sanitized report artifacts only:
`reports/run-latest.json` is required, while drift,
`reports/capture-summary.json`, artifact manifest, evidence bundle, agent
bundle, and test-pyramid artifacts are summarized when present. Test-pyramid
evidence is optional and value-free: a present `reports/test-pyramid.json`
contributes runtime-governance status, layer counts, and finding count to the
card; missing test-pyramid evidence does not block card generation.
`entroping report capture-summary --fail-on-unredacted` is an optional CI guard
that still writes the requested counts-only capture summary, then exits `1`
when sanitized local evidence contains unredacted records. A `pass` card is a PR or release
review signal, so missing `reports/artifact-manifest.json` or
`reports/evidence-bundle.json` adds warning findings, marks the card
`attention`, and makes the CLI exit nonzero. Missing required run evidence
writes a failed card, and missing redaction evidence marks the card for
reviewer attention. Present malformed artifacts fail closed before output is
written. The card does not execute Hurl, call providers, upload results, or
render raw Hurl output, raw traffic, prompts, provider responses, credentials,
or environment values.

`entroping report pilot-metrics` writes a local design-partner pilot metric
report at `reports/pilot-metrics.md` by default, or
`reports/pilot-metrics.json` with `--output json`. It reads only existing
sanitized local artifacts: `reports/run-latest.json`,
`reports/runtime-card.json`, `reports/evidence-bundle.json`,
`reports/artifact-manifest.json`, and `reports/agent-bundle.json`. It can infer
evidence-bundle ready rate from the evidence bundle and waived-gate count from
run-report known-failure evidence. Setup time, useful failures, false positives,
and human steering remain explicit `manual_input_required` metrics because they
need design-partner or reviewer input. Missing, malformed, or unsafe artifacts
are recorded as `unknown` source-backed metric states instead of causing hosted
uploads, Hurl execution, provider calls, or raw artifact rendering.

`entroping report handoff` writes a local cross-surface evidence handoff packet
at `reports/handoff.md` by default, or `reports/handoff.json` with
`--output json`. It summarizes existing sanitized report artifacts for future
CLI, PR, desktop, cloud, mobile, and coding-agent handoffs: runtime card,
evidence bundle, pilot metrics, artifact manifest, and test-pyramid evidence.
The packet records only value-free metadata such as artifact state, schema
version, bounded SHA-256, runtime-card summary counts, failed-gate count,
pilot-readiness status, test-pyramid status, best-effort local Git
branch/commit, generated handoff path, and next-action text. Missing artifacts
are non-blocking unless `--fail-on-insufficient` is set and no source evidence
artifacts are present.
Malformed, unsupported, oversized, non-file, symlinked, or secret-like source
artifacts are marked invalid or unsafe. The command does not execute Hurl, call
providers, upload results, parse raw traffic, read `.entroping` traffic state,
or include raw URLs, headers, bodies, cookies, prompts, provider outputs,
credentials, environment values, or source Hurl contents.

`entroping report notification-packet` writes a local read-only work-management
and chat notification packet at `reports/notification-packet.md` by default, or
`reports/notification-packet.json` with `--output json`. It converts sanitized
handoff/runtime evidence into value-free messages for Jira, Linear, monday.com,
Slack, Discord, Workato, and coding-agent surfaces. The packet records only
status/severity labels, counts, local artifact paths, and next-action text.
Missing source artifacts are non-blocking and become partial or insufficient
packet state; malformed, oversized, non-file, symlinked, wrong-schema, or
secret-like source artifacts are marked invalid or unsafe. The command does not
execute Hurl, run tests, call providers, upload results, call issue-tracker,
chat, automation, Claude, or Codex APIs, mutate tickets or chat, read traffic
state, or include raw URLs, headers, bodies, cookies, prompts, provider outputs,
credentials, environment values, webhook URLs, ticket mutation payloads, source
Hurl contents, or full report contents.

`entroping report team-evidence-readiness` writes a local read-only readiness
packet at `reports/team-evidence-readiness.md` by default, or
`reports/team-evidence-readiness.json` with `--output json`. It aggregates
value-free states from existing evidence-bundle, runtime-card, pilot-metrics,
design-partner-feedback, handoff, and notification-packet artifacts into team
evidence cloud readiness areas, explicit boundary controls, and next actions.
Missing source artifacts are non-blocking and become partial or insufficient
packet state; malformed, oversized, non-file, symlinked, wrong-schema, or
secret-like source artifacts are marked invalid or unsafe. The command does not
execute Hurl, run tests, call providers, upload results, create accounts, change
access control, call issue-tracker or chat APIs, read traffic state, or include
raw URLs, headers, bodies, cookies, prompts, provider outputs, credentials,
environment values, webhook URLs, ticket mutation payloads, source Hurl
contents, raw report contents, or full report contents.

`entroping report team-access-control-plan` writes a local read-only team
access-control and audit planning packet at `reports/team-access-control-plan.md`
by default, or `reports/team-access-control-plan.json` with `--output json`. It
reads the existing sanitized team-evidence-readiness, handoff,
notification-packet, and runtime-card artifacts, then emits role plans,
allowed and forbidden action lists, future audit event requirements, source
states, schema versions, bounded hashes, compact summaries, and next actions.
Missing source artifacts are non-blocking and become partial or insufficient
planning state; malformed, oversized, non-file, symlinked, wrong-schema, or
secret-like source artifacts are marked invalid or unsafe. The command does not
execute Hurl, run tests, call providers, upload results, create accounts,
implement access control, enforce RBAC or SSO, call issue-tracker or chat APIs,
write back to any external system, read traffic state, or include raw URLs,
headers, bodies, cookies, prompts, provider outputs, credentials, environment
values, webhook URLs, ticket mutation payloads, source Hurl contents, raw
report contents, or full report contents.

`entroping report integration-readiness` writes a local read-only integration
readiness packet at `reports/integration-readiness.md` by default, or
`reports/integration-readiness.json` with `--output json`. It reads existing
sanitized team-access-control-plan, notification-packet, handoff,
observability-packet, API-inventory, and runtime-card artifacts, then emits
source states, schema versions, bounded hashes, surface families, required
source IDs, link and event requirements, forbidden actions, blockers, and next
actions for issue trackers, chat, enterprise automation, cross-surface
continuity, observability, and API governance. Missing source artifacts are
non-blocking and become partial or insufficient planning state; malformed,
oversized, non-file, symlinked, wrong-schema, or secret-like source artifacts
are marked invalid or unsafe. The command does not execute Hurl, run tests,
call Jira, Linear, monday.com, Slack, Discord, Workato, Claude, Codex, OpenAI,
Datadog, Splunk, or other external APIs, upload results, create accounts,
configure SSO or RBAC, mutate tickets or chat, execute chat commands, read
provider keys, parse traffic state, sync repos or vaults, write back to any
external system, or include raw URLs, headers, bodies, cookies, prompts,
provider outputs, credentials, environment values, webhook URLs, ticket
mutation payloads, source Hurl contents, raw report contents, or full report
contents.

`entroping report devex-readiness` writes a local read-only developer
experience readiness packet at `reports/devex-readiness.md` by default, or
`reports/devex-readiness.json` with `--output json`. It reads existing
sanitized runtime-card, handoff, evidence-index, integration-readiness,
notification-packet, and team-access-control-plan artifacts, then emits source
states, schema versions, bounded hashes, surface families, required source IDs,
link and action requirements, forbidden actions, blockers, and next actions for
CLI, VS Code/editor, local workbench, PR runtime card, desktop, cloud, and
mobile surfaces. Missing source artifacts are non-blocking and become partial
or insufficient planning state; malformed, oversized, non-file, symlinked,
wrong-schema, or secret-like source artifacts are marked invalid or unsafe. The
command does not implement a VS Code extension, desktop app, web app, mobile
app, hosted sync, deep links, PR comments, ticket/chat writes, call external
APIs, execute Hurl, run tests, call providers or models, synchronize repos,
vaults, or worktrees, parse traffic state, configure SSO/RBAC, mutate external
systems, or include raw URLs, headers, bodies, cookies, prompts, provider
outputs, credentials, environment values, webhook URLs, ticket mutation
payloads, source Hurl contents, raw report contents, or full report contents.

`entroping report evidence-cloud-readiness` writes a local read-only Evidence
Cloud readiness packet at `reports/evidence-cloud-readiness.md` by default, or
`reports/evidence-cloud-readiness.json` with `--output json`. It reads existing
sanitized team-evidence-readiness, evidence-bundle, runtime-card,
artifact-manifest, design-partner-feedback, pilot-metrics,
integration-readiness, devex-readiness, connector-intent, and evidence-index
artifacts, then emits source states, schema versions, bounded SHA-256 hashes,
readiness areas, cloud-boundary controls, upload-candidate metadata, blockers,
and next-action rows. These are fixed optional local inputs; missing source
artifacts are non-blocking and become partial or insufficient packet state.
Malformed, oversized, non-file, symlinked, wrong-schema, unreadable, or
secret-like source artifacts are marked invalid or unsafe. The command does not
call Evidence Cloud hosted APIs, upload artifacts, sync remote state, call
providers, create accounts, configure SSO/RBAC, mutate tickets or chat, call
observability APIs, sync repos or vaults, execute Hurl, run tests, invoke
models, parse traffic state, change `entroping run`, or include raw URLs,
headers, bodies, cookies, prompts, provider outputs, credentials, environment
values, webhook URLs, ticket mutation payloads, design-partner free-form text,
source Hurl contents, raw report contents, raw traffic, or full report
contents.

`entroping report evidence-cloud-export` writes a local read-only Evidence
Cloud export manifest at `reports/evidence-cloud-export.md` by default, or
`reports/evidence-cloud-export.json` with `--output json`. It reads existing
sanitized evidence-portal, evidence-links, evidence-cloud-readiness,
team-evidence-readiness, evidence-bundle, artifact-manifest, runtime-card,
handoff, integration-readiness, devex-readiness, connector-intent,
observability-packet, and evidence-index artifacts, then emits source states,
schema versions, bounded SHA-256 hashes, local export references,
boundary-control rows, and next actions. These are fixed optional local inputs;
missing source artifacts are non-blocking and become partial or insufficient
manifest state. Malformed, oversized, non-file, symlinked, wrong-schema,
unreadable, or secret-like source artifacts are marked invalid or unsafe. The
command does not call Evidence Cloud hosted APIs, upload artifacts, sync remote
state, create accounts, configure SSO/RBAC, mutate tickets or chat, call
observability APIs, sync repos or vaults, execute Hurl, run tests, invoke
models, parse traffic state, change `entroping run`, or include raw URLs,
headers, bodies, cookies, prompts, provider outputs, credentials, environment
values, webhook URLs, ticket mutation payloads, source Hurl contents, raw
traffic, raw report contents, or full report payloads.

`entroping report evidence-cloud-workspace --manifest <path>` writes a local
read-only workspace packet at `reports/evidence-cloud-workspace.md` by default,
or JSON with schema `entroping.evidence-cloud-workspace.v1`. It reads only
explicit `entroping.evidence-cloud-export.v1` manifests, rejects unsafe or
invalid inputs as value-free rows, and emits repository counts, bounded hashes,
boundary-control rollups, local references, and next actions. It does not
upload, call hosted/model APIs, inspect raw artifacts beyond explicit
manifests, execute Hurl/tests, parse traffic, change `entroping run`, or render
raw traffic, secrets, prompts, provider output, source Hurl, env values, or full
report payloads.

`entroping report evidence-cloud-dashboard --manifest <path>` writes a static
local read-only dashboard at `reports/evidence-cloud-dashboard.html` by
default, or `reports/evidence-cloud-dashboard.json` with `--output json`. It
reuses the Evidence Cloud workspace packet semantics over explicit export
manifests, then emits value-free manifest state, repository cards,
boundary-control rollups, and next actions. The HTML is static and local-only,
with no external assets or scripts. The command does not call hosted APIs,
upload artifacts, execute Hurl/tests, invoke models, parse traffic state,
change `entroping run`, inspect raw artifacts beyond explicit export
manifests, or render secrets, source Hurl, env values, raw traffic, or full
report payloads.

`entroping report evidence-links` writes a local read-only cross-surface
evidence links packet at `reports/evidence-links.md` by default, or
`reports/evidence-links.json` with `--output json`. It reads existing
sanitized evidence-index, handoff, runtime-card, evidence-bundle,
evidence-cloud-readiness, notification-packet, connector-intent,
integration-readiness, and devex-readiness artifacts, then emits stable local
link tokens, `artifact_uri` anchors such as
`entroping://evidence/runtime-card-json`, source states, schema versions,
bounded SHA-256 hashes, surface applicability, blocked targets, and next-action
rows. These are fixed optional local inputs and value-free local metadata, not
registered protocol handlers or network endpoints; missing source artifacts are
non-blocking and become partial or insufficient packet state. Malformed,
oversized, non-file, symlinked, wrong-schema, unreadable, or secret-like source
artifacts are marked invalid or unsafe. The command does not register protocol
handlers, serve hosted pages, build UI surfaces, upload artifacts, sync remote
state, call external APIs, mutate tickets or chat, call observability APIs, sync
repos or vaults, execute Hurl, run tests, invoke models, parse traffic state,
change `entroping run`, or include raw URLs, headers, bodies, cookies, prompts,
provider outputs,
credentials, environment values, webhook URLs, ticket mutation payloads, source
Hurl contents, raw report contents, raw traffic, or full report contents.

`entroping report evidence-portal` writes a static local read-only evidence
dashboard at `reports/evidence-portal.html` by default, or
`reports/evidence-portal.json` with `--output json`. It reads existing
sanitized evidence-links, evidence-index, runtime-card, handoff,
evidence-cloud-readiness, devex-readiness, connector-intent,
observability-packet, and test-pyramid artifacts, then emits source states,
schema versions, bounded SHA-256 hashes, card readiness, target/surface counts,
and next-action rows. These are fixed optional local inputs; missing source
artifacts are non-blocking and become partial or insufficient portal state.
Malformed, oversized, non-file, symlinked, wrong-schema, unreadable, or
secret-like source artifacts are marked invalid or unsafe. The HTML is static
and local-only, with no external assets or scripts. The command does not host a
web app, upload artifacts, sync remote state, register protocol handlers, call
external APIs, mutate tickets or chat, call observability APIs, sync repos or
vaults, execute Hurl, run tests, invoke models, parse traffic state, change
`entroping run`, or include raw URLs, headers, bodies, cookies, prompts,
provider outputs, credentials, environment values, webhook URLs, ticket
mutation payloads, source Hurl contents, raw report contents, raw traffic, or
full report contents.

`entroping report pr-evidence-card` writes `reports/pr-evidence-card.md` by
default, or `reports/pr-evidence-card.json` with `--output json`. It reads
fixed sanitized artifacts through the evidence-index boundary and emits only
source states, schemas, bounded hashes, checklist rows, and next actions.
Missing, malformed, oversized, symlinked, wrong-schema, unreadable, or
secret-like sources stay value-free; the command does not mutate PRs, call
APIs, upload, execute Hurl/tests, invoke models, parse traffic, change
`entroping run`, or render raw report/source contents.

`entroping report evidence-action-plan` writes
`reports/evidence-action-plan.md` by default, or
`reports/evidence-action-plan.json` with `--output json`. It reads fixed
sanitized evidence-loop artifacts through the evidence-index boundary and emits
only source states, schemas, bounded hashes, summary status, and prioritized
generate, repair, or review actions. It does not mutate PRs, tickets, chat,
dashboards, or hosted state, call external APIs, upload artifacts, execute
Hurl/tests, invoke models, parse traffic, change `entroping run`, or render raw
artifact contents.

`entroping report work-item-draft` writes `reports/work-item-draft.md` by
default, or `reports/work-item-draft.json` with `--output json`. It reads fixed
sanitized evidence-action-plan, connector-intent, integration-readiness,
evidence-links, and notification-packet artifacts through the evidence-index
boundary and emits only source states, schemas, bounded hashes, target tracker
families, draft titles/summaries, priorities, source action IDs/counts, and
forbidden actions. Missing source artifacts become generation rows; malformed,
oversized, symlinked, unreadable, or secret-like source artifacts become repair
rows. It does not create or update tickets, PRs, chat, automation, hosted
state, labels, assignments, comments, uploads, external APIs, Hurl/tests, model
providers, traffic state, `entroping run`, source Hurl, raw report contents,
provider keys, credentials, cookies, tokens, webhooks, or prompts.

`entroping report work-item-import-bundle` writes
`reports/work-item-import-bundle.json` by default, or
`reports/work-item-import-bundle.csv` with `--output csv`. It reads only the
fixed optional `reports/work-item-draft.json` artifact through the
evidence-index boundary and emits source state, schema, bounded hash, tracker
family, external ID, title, body/description, priority, labels, source item
IDs, source action IDs/counts, and forbidden actions. Missing draft artifacts
become generation actions; malformed, oversized, symlinked, unreadable, or
secret-like source artifacts become repair actions. CSV output is
spreadsheet-safe and neutralizes formula-leading cells. The command does not
create, update, sync, import, upload, assign, label, comment on, or post to
tickets, PRs, chat, automation, hosted state, dashboards, external APIs,
Hurl/tests, model providers, traffic state, `entroping run`, source Hurl, raw
report contents, provider keys, credentials, cookies, tokens, webhooks, or
prompts.

`entroping report pilot-outcome` writes `reports/pilot-outcome.md` by default,
or `reports/pilot-outcome.json` with `--output json`. It reads only fixed
optional sanitized `design-partner-feedback`, `pilot-metrics`, `runtime-card`,
Evidence Cloud dashboard, and work-item import bundle artifacts through the
evidence-index safety path, then emits source states, schemas, bounded hashes,
readiness statuses, manual-input field names, monetization signal answers, and
next actions. Missing sources become generation actions; malformed, oversized,
symlinked, unreadable, wrong-schema, or secret-like sources become repair
actions. It does not create or update tickets, PRs, chat, automation, hosted
state, imports, uploads, external APIs, Hurl/tests, model providers, traffic
state, `entroping run`, source Hurl, raw report contents, design-partner
private notes, provider keys, credentials, cookies, tokens, webhooks, URLs, or
prompts.

`entroping report pilot-cohort --manifest <path>` writes
`reports/pilot-cohort.md` by default, or `reports/pilot-cohort.json` with
`--output json`. The manifest is explicit local JSON with schema version
`entroping.pilot-cohort-manifest.v1` and `outcomes[]` packet paths. The command
reads only those `entroping.pilot-outcome.v1` JSON packets through the
evidence-index safety path, then emits source states, schemas, bounded hashes,
cohort status counts, value-free monetization answer counts, readiness status
counts, manual-input gap counts, and next actions. Missing outcomes become
generation actions; malformed, oversized, symlinked, unreadable, wrong-schema,
forbidden-directory, outside-project, or secret-like outcomes become repair
actions. It does not discover cohorts, create or update tickets, PRs, chat,
automation, hosted state, imports, uploads, external APIs, Hurl/tests, model
providers, traffic state, `entroping run`, source Hurl, raw outcome contents,
design-partner private notes, provider keys, credentials, cookies, tokens,
webhooks, URLs, or prompts.

`entroping report connector-intent` writes a local read-only connector intent
packet at `reports/connector-intent.md` by default, or
`reports/connector-intent.json` with `--output json`. It reads existing
sanitized runtime-card, handoff, notification-packet, integration-readiness,
devex-readiness, observability-packet, and evidence-index artifacts, then emits
source states, schema versions, bounded hashes, target systems, intent kind,
minimum payload fields, required user action, audit fields, forbidden actions,
blockers, and next actions for future issue tracker, chat, enterprise
automation, enterprise AI, observability, and developer-experience connectors.
Missing source artifacts are non-blocking and become partial or insufficient
planning state; malformed, oversized, non-file, symlinked, wrong-schema, or
secret-like source artifacts are marked invalid or unsafe. The command does not
implement Jira, Linear, monday.com, Slack, Discord, Teams, Workato, Zapier,
Claude, Codex, OpenAI-compatible, Datadog, Splunk, OpenTelemetry, Grafana, VS
Code, desktop, web, cloud, or mobile adapters; call external APIs; invoke model
providers; execute Hurl; run tests; upload artifacts; mutate tickets, chat,
dashboards, monitors, workflows, repos, vaults, or worktrees; parse raw traffic
state; configure SSO/RBAC; or include raw URLs, headers, bodies, cookies,
prompts, provider outputs, credentials, environment values, webhook URLs,
ticket mutation payloads, source Hurl contents, raw report contents, raw
traffic, or full report contents.

`entroping report observability-packet` writes a local read-only observability
signal packet at `reports/observability-packet.md` by default, or
`reports/observability-packet.json` with `--output json`. It converts existing
structured diagnostics and runtime-card metadata into value-free signal
summaries for OpenTelemetry, Datadog, Splunk, Grafana, and generic
observability consumers. The packet records only source states, schema
versions, bounded SHA-256 hashes, diagnostic component/operation/code counts,
runtime-card status counts, local artifact paths, and next-action text. Missing
diagnostics or runtime-card evidence is non-blocking and becomes partial or
insufficient packet state; malformed, oversized, non-file, symlinked,
wrong-schema, or secret-like source artifacts are marked invalid or unsafe. The
command does not execute Hurl, run tests, call providers, upload results, call
observability vendor APIs, mutate dashboards or monitors, read traffic state, or
include raw URLs, headers, bodies, cookies, prompts, provider outputs,
credentials, environment values, raw report contents, source Hurl contents, or
full diagnostic attributes.

`entroping report otel-mapping` writes a local read-only OpenTelemetry evidence
mapping packet at `reports/otel-mapping.md` by default, or
`reports/otel-mapping.json` with `--output json`. It converts existing
sanitized observability-packet, runtime-card, test-pyramid, and external-test
evidence metadata into value-free resource, log, metric, and trace attribute
mapping rows for a future OTLP adapter. Missing source artifacts are
non-blocking and become partial or insufficient packet state; malformed,
oversized, non-file, symlinked, wrong-schema, unreadable, or secret-like source
artifacts are marked invalid or unsafe. The command does not export OTLP, call
OpenTelemetry collectors, Datadog, Splunk, Grafana, or other vendor APIs,
mutate dashboards, monitors, tickets, chat, PRs, or hosted state, read provider
keys, parse traffic state, execute Hurl, run tests, invoke models, change
`entroping run`, or include raw URLs, headers, bodies, cookies, prompts,
provider outputs, credentials, environment values, webhook URLs, ticket
mutation payloads, source Hurl contents, raw traffic, raw report contents, or
full report contents.

`entroping report otlp-preview` writes a local read-only OTLP-shaped preview at
`reports/otlp-preview.md` by default, or `reports/otlp-preview.json` with
`--output json`. It converts sanitized run/report evidence into aggregate
resource, log, metric, and span preview rows without exporting telemetry or
configuring collectors. Missing source artifacts become explicit readiness
states; malformed, oversized, non-file, symlinked, wrong-schema, unreadable, or
secret-like artifacts are marked invalid or unsafe. The command does not call
OpenTelemetry collectors, Datadog, Splunk, Grafana, or other vendor APIs,
mutate dashboards, monitors, tickets, chat, PRs, or hosted state, parse traffic
state, execute Hurl, run tests, invoke models, change `entroping run`, or
include raw test output, test paths, URLs, headers, bodies, cookies, prompts,
provider outputs, credentials, environment values, raw traffic, or full report
contents.

`entroping report observability-adapter-readiness` writes a local read-only
observability adapter readiness packet at
`reports/observability-adapter-readiness.md` by default, or
`reports/observability-adapter-readiness.json` with `--output json`. It reads
existing sanitized observability-packet, OpenTelemetry mapping, evidence-index,
and runtime-card metadata, then emits value-free readiness rows for future
OpenTelemetry, Datadog, Splunk, Grafana, and generic observability adapters.
Missing source artifacts are non-blocking and become partial or insufficient
packet state; malformed, oversized, non-file, symlinked, wrong-schema,
unreadable, or secret-like source artifacts are marked invalid or unsafe. The
command does not export OTLP, call collectors, Datadog, Splunk, Grafana, hosted
APIs, webhooks, dashboards, monitors, tickets, chat, PRs, or Evidence Cloud,
read provider keys or local secret stores, parse raw traffic or `.entroping/`
runtime state, execute Hurl, run tests, invoke models, mutate source Hurl,
change `entroping run`, or include raw URLs, headers, bodies, cookies,
prompts, provider outputs, credentials, environment values, webhook URLs,
dashboard payloads, monitor payloads, source Hurl contents, raw traffic, raw
report contents, or full report contents.

Troubleshooting posture:

- Datadog and Splunk should enter adapter implementation only after local
  packets are generated (especially observability packet and mapping packet).
- Grafana design should reference local packet metadata first, then wire to the
  vendor layer.
- Generic observability adapters consume the same local packet set and stay
  value-free by default.

`entroping report api-inventory` writes a local read-only API surface inventory
at `reports/api-inventory.md` by default, or `reports/api-inventory.json` with
`--output json`. It detects configured and conventional OpenAPI files,
committed Hurl tests with protocol tags, GraphQL/WSDL/proto schema files,
AsyncAPI specs, webhook/event-contract files, and WebSocket/realtime contract
files, then summarizes REST/OpenAPI, GraphQL, SOAP/XML, gRPC/proto, AsyncAPI,
webhook/event, WebSocket/realtime, and unknown HTTP signals without generating
tests. GraphQL SDL sources contribute counts for root `Query`, `Mutation`, and
`Subscription` fields without rendering field names; WSDL sources contribute
counts for `portType` operations without rendering operation names, service
names, addresses, or raw XML; proto sources contribute counts for `rpc`
declarations without rendering service or RPC names. The packet records only
source states, project-relative local paths, tags, operation/exchange counts,
SHA-256 hashes, and next-action text. Missing
sources are non-blocking; malformed, oversized, non-file, symlinked,
path-escaped, or secret-like source artifacts are marked invalid or unsafe. The
command does not execute Hurl, call providers, upload results, parse traffic
state, call registries, generate tests, mutate source files, or include raw
URLs, headers, bodies, cookies, prompts, credentials, environment values,
GraphQL field names, WSDL operation names, WSDL service names, WSDL addresses,
proto RPC names, proto service names, raw XML, or full file contents.

`entroping report mutation-readiness` writes a local read-only
mutation/fuzz-readiness packet at `reports/mutation-readiness.md` by default,
or `reports/mutation-readiness.json` with `--output json`. It reads committed
generated Hurl tests under `tests/generated/` or tests carrying generated
metadata, plus optional existing `reports/test-quality.json` and
`reports/test-pyramid.json` artifacts when present and schema-valid. It
summarizes only counts and local source states for generated corpus presence,
negative-path evidence, auth/security evidence, assertion strength, seed
metadata, and safe candidate categories such as status-code, schema, auth,
latency, request-shape, and response-shape. Candidate next actions flag
categories that still contain generated tests without deterministic seed
metadata, but seed values themselves are never rendered. Absent optional
test-quality and test-pyramid report inputs are surfaced as non-blocking
missing source evidence with relative paths only. Missing evidence is
non-blocking; malformed, oversized, non-file, symlinked, path-escaped,
wrong-schema, or secret-like source artifacts are marked invalid or unsafe. The
command does not execute Hurl, run mutation tests, run fuzzers, generate tests,
call providers, upload results, parse traffic state, mutate source files, or
include raw URLs, headers, bodies, cookies, prompts, credentials, environment
values, seed values, full report contents, or source Hurl contents. Direct
packet data and JSON serialization plus JSON and Markdown rendering reject
secret-like output before returning content to direct callers; secret-like local
project directory names are redacted before packet rendering.

`entroping report evidence-index` writes a local read-only evidence artifact
index at `reports/evidence-index.md` by default, or
`reports/evidence-index.json` with `--output json`. It reuses the existing
local evidence inventory and emits stable artifact IDs, labels,
project-relative paths, source states, schema versions, and compact value-free
summaries for local report artifacts. It includes
`reports/external-test-evidence.json` with schema
`entroping.external-test-evidence.v1` and
`reports/external-test-evidence.md`; the JSON summary is limited to status,
layer, test, failure, error, and skipped totals. Missing evidence is
non-blocking; invalid, unsafe, symlinked, non-file, oversized, malformed, or
unreadable source artifacts remain represented through evidence-index states
without embedding source contents. The command does not execute Hurl, run
tests, call providers, upload artifacts, parse traffic state, mutate files, or
render raw report contents, raw traffic, source Hurl, prompts, credentials,
cookies, environment values, or provider outputs.

`entroping report qa-brain-seed` writes a local read-only QA Brain seed packet
at `reports/qa-brain-seed.md` by default, or `reports/qa-brain-seed.json` with
`--output json`. It transforms value-free evidence-index rows into
seed-source categories, eval-slice readiness, and next-action rows for future
QA Brain retrieval and eval design. It is not a model, fine-tune, retrieval
engine, or provider integration, and it preserves LiteLLM/provider-neutral
boundaries. Missing evidence is non-blocking; invalid, unsafe, symlinked,
non-file, oversized, malformed, or unreadable source artifacts remain
represented through evidence-index states without embedding contents. The
command does not execute Hurl, run tests, call providers, fine-tune models,
upload artifacts, parse traffic state, mutate files, or render raw report
contents, raw traffic, source Hurl, prompts, credentials, cookies, environment
values, or provider outputs.

`entroping report qa-brain-eval-plan` writes a local read-only QA Brain eval
plan at `reports/qa-brain-eval-plan.md` by default, or
`reports/qa-brain-eval-plan.json` with `--output json`. It derives future eval
case metadata from deterministic QA-brain seed readiness: readiness state,
value-free source IDs and paths, input/output contracts, deterministic
acceptance signals, negative controls, value-free source-state catalog counts,
categories, schema versions, missing-evidence reasons, and next-action rows. It is not a
model, fine-tune, retrieval engine, eval runner, or provider integration, and
it preserves LiteLLM/provider-neutral boundaries. Missing evidence is
non-blocking; attention cases remain represented without embedding source
contents. The command does not execute Hurl, run tests, call providers,
fine-tune models, upload artifacts, retrieve documents, parse traffic state,
run mutations or fuzzers, or render raw report contents, raw traffic, source
Hurl, prompts, credentials, cookies, environment values, or provider outputs.

`entroping report qa-brain-retrieval-plan` writes a local read-only QA Brain
retrieval plan at `reports/qa-brain-retrieval-plan.md` by default, or
`reports/qa-brain-retrieval-plan.json` with `--output json`. It derives future
retrieval metadata from deterministic QA-brain eval-plan readiness: readiness
state, value-free source IDs and paths, retrieval categories, allowed fields,
forbidden fields, query hints, safety notes, and next-action rows. It is not a
model, embedding job, vector database, retrieval engine, fine-tune, eval
runner, hosted upload, or provider integration, and it preserves
LiteLLM/provider-neutral boundaries. Missing evidence is non-blocking;
attention cases remain represented without embedding source contents. The
command does not execute Hurl, run tests, call providers, create embeddings,
fine-tune models, upload artifacts, retrieve documents, parse traffic state,
run mutations or fuzzers, or render raw report contents, raw traffic, source
Hurl, prompts, credentials, cookies, environment values, or provider outputs.

`entroping report qa-brain-prompt-plan` writes a local read-only QA Brain
prompt plan at `reports/qa-brain-prompt-plan.md` by default, or
`reports/qa-brain-prompt-plan.json` with `--output json`. It derives future
prompt design metadata from deterministic QA-brain retrieval-plan readiness:
readiness state, value-free source IDs and paths, retrieval category, prompt
objective, allowed prompt inputs, forbidden prompt inputs, expected structured
output fields, deterministic acceptance signals, negative controls, safety
notes, and next-action rows. It is not a model, executable prompt, embedding
job, vector database, retrieval engine, fine-tune, eval runner, hosted upload,
or provider integration, and it preserves LiteLLM/provider-neutral boundaries.
Missing evidence is non-blocking; attention cases remain represented without
embedding source contents. The command does not execute Hurl, run tests, call
providers, create embeddings, fine-tune models, upload artifacts, retrieve
documents, parse traffic state, run mutations or fuzzers, execute prompts, or
render raw report contents, raw traffic, source Hurl, prompts for execution,
credentials, cookies, environment values, or provider outputs.

`entroping report qa-brain-fine-tune-readiness` writes a local read-only QA
Brain fine-tune readiness packet at
`reports/qa-brain-fine-tune-readiness.md` by default, or
`reports/qa-brain-fine-tune-readiness.json` with `--output json`. It derives
future proprietary-model experiment readiness metadata from deterministic
QA-brain prompt-plan readiness: readiness state, value-free source IDs and
paths, readiness stage, evidence coverage, prompt-plan completeness, safety
boundary, eval-case coverage, redaction boundary, deterministic acceptance
summary, blockers, and next-action rows. It is not a model, executable prompt,
embedding job, vector database, retrieval engine, dataset export, fine-tune,
training run, model package, hosted upload, or provider integration, and it
preserves LiteLLM/provider-neutral boundaries. Missing evidence is
non-blocking; attention cases remain represented without embedding source
contents. The command does not execute Hurl, run tests, call providers, create
embeddings, fine-tune models, train models, upload artifacts, retrieve
documents, export datasets, package models, parse traffic state, run mutations
or fuzzers, execute prompts, or render raw report contents, raw traffic,
source Hurl, prompts for execution, credentials, cookies, environment values,
or provider outputs.

`entroping report qa-brain-model-packaging-plan` writes a local read-only QA
Brain model-packaging plan packet at
`reports/qa-brain-model-packaging-plan.md` by default, or
`reports/qa-brain-model-packaging-plan.json` with `--output json`. It derives
future hosted, local, and enterprise QA Brain Pro packaging metadata from
deterministic QA-brain fine-tune readiness: readiness state, value-free source
IDs and paths, packaging stage, OpenAI-compatible endpoint boundary, LiteLLM
routing boundary, deployment modes, artifact boundary, access-control and audit
needs, blockers, and next-action rows. It is not a model server, endpoint
implementation, gateway, model package, container build, executable prompt,
embedding job, vector database, retrieval engine, dataset export, fine-tune,
training run, hosted upload, or provider integration, and it preserves
LiteLLM/provider-neutral boundaries. Missing evidence is non-blocking;
attention and blocked cases remain represented without embedding source
contents. The command does not execute Hurl, run tests, call providers, change
LiteLLM configuration, start endpoints, package models, build containers,
create embeddings, fine-tune or train models, upload artifacts, retrieve
documents, export datasets, parse traffic state, run mutations or fuzzers,
execute prompts, or render raw report contents, raw traffic, source Hurl,
prompts for execution, credentials, cookies, environment values, or provider
outputs.

`entroping report qa-brain-routing-plan` writes a local read-only QA Brain
routing-plan packet at `reports/qa-brain-routing-plan.md` by default, or
`reports/qa-brain-routing-plan.json` with `--output json`. It derives future
LiteLLM and OpenAI-compatible routing-readiness metadata from deterministic
QA-brain model-packaging plan metadata: readiness state, packaging stage,
value-free source IDs and paths, routing stage, LiteLLM boundary, endpoint
boundary, deployment modes, allowed future use cases, required
repair-proposal acceptance gates, forbidden pass/fail authority, access-control
and audit needs, blockers, and next-action rows. The acceptance gates are
value-free advisory routing metadata for parser validation, deterministic Hurl
execution, QAnstitution governance, deterministic evidence linkage, secret
redaction, and Codex/human review; a generated repair remains unaccepted until
those checks pass outside this report. It is not a provider adapter, LiteLLM
configuration writer, endpoint
implementation, gateway, SDK adapter, model package, container build,
executable prompt, embedding job, vector database, retrieval engine, dataset
export, fine-tune, training run, eval run, hosted upload, or provider
integration. Missing evidence is non-blocking; attention and blocked cases
remain represented without embedding source contents. The command does not
execute Hurl, run tests, call providers, read provider keys, change LiteLLM
configuration, start endpoints, select providers, invoke models, package
models, build containers, create embeddings, fine-tune or train models, upload
artifacts, retrieve documents, export datasets, parse traffic state, run
mutations or fuzzers, execute prompts, or render raw report contents, raw
traffic, source Hurl, prompts for execution, credentials, cookies, environment
values, or provider outputs.

`entroping report qa-brain-repair-plan` writes a local read-only QA Brain
repair-plan packet at `reports/qa-brain-repair-plan.md` by default, or
`reports/qa-brain-repair-plan.json` with `--output json`. It derives future
repair-proposal readiness metadata from value-free local generated-test quality,
mutation readiness, evidence action-plan, QA Brain routing-plan, and evidence
index states. Rows carry source states, repair intent, acceptance-gate IDs from
the routing-plan packet when present, blockers, and next actions. It is not a
repair generator, prompt executor, provider adapter, LiteLLM configuration
writer, Hurl executor, mutation/fuzz runner, source-Hurl or policy writer,
hosted upload, ticket/chat mutation, retrieval job, embedding job, fine-tune,
training run, or provider integration. Missing evidence is represented as
missing/insufficient; invalid, unsafe, oversized, unreadable, symlinked, or
secret-like evidence is represented as invalid/unsafe or rejected before output.
The command does not render raw report contents, raw Hurl, traffic, prompts,
credentials, cookies, environment values, provider output, URLs, headers,
bodies, examples, or model responses.

`entroping report sarif` writes SARIF 2.1.0 to `reports/entroping.sarif` by
default. It converts the same local JUnit, drift, and optional traceability
findings used by GitHub annotation output into stable SARIF rule IDs, severity,
message text, and best-effort file locations. The command does not execute
Hurl, call providers, or upload results; downstream CI remains responsible for
uploading the SARIF artifact to code scanning. Finding text and locations are
redacted before serialization, and absolute project-root paths are relativized.

### Report Artifact Contracts

Report commands that accept user-controlled output paths validate those paths
before resolving them. Direct symlink output files and symlinked parent
components are rejected before artifact writes, root escapes and local-state
directories remain blocked, and `safe_write_text` remains the final write
primitive for local report files.

| Command | Artifact | Stability note |
| --- | --- | --- |
| `entroping run` | `.entroping/latest-run.json` | Runtime state for follow-up report commands; uses `entroping.run-report.v1`; not committed. |
| `entroping run` | `.entroping/latest-run-events.jsonl` | Sanitized execution progress events using `entroping.run-events.v1`; not committed. |
| Headless/report/doctor diagnostics | `.entroping/latest-diagnostics.jsonl` | Vendor-neutral value-free component diagnostics using `entroping.diagnostics.v1`; local state, not committed, and separate from per-run execution events. |
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
| `entroping report redaction --fail-on-unsafe` | `reports/redaction-review.md` or `reports/redaction-review.html` | Optional CI guard over unredacted and low-confidence record evidence in the redaction review. |
| `entroping report capture-summary --output md` | `reports/capture-summary.md` | Counts-only captured-traffic session summary for freeze review. |
| `entroping report capture-summary --output json` | `reports/capture-summary.json` | Machine-readable capture summary using `entroping.capture-summary.v1`. |
| `entroping report capture-summary --fail-on-unredacted` | `reports/capture-summary.md` or `reports/capture-summary.json` | Optional CI guard over unredacted-record evidence in the capture summary. |
| `entroping report policy --output md` | `reports/effective-policy.md` | Human-readable resolved QAnstitution gate provenance. |
| `entroping report policy --output json` | `reports/effective-policy.json` | Machine-readable effective policy evidence using `entroping.effective-policy-report.v1`. |
| `entroping report policy-diff --output md|json` | `stdout Effective Policy Diff Markdown/JSON` | Import and gate differences between two effective-policy JSON artifacts using `entroping.effective-policy-diff.v1`; `--fail-on-change` exits `1` when the status is changed. |
| `entroping report gate-coverage --output md` | `reports/gate-coverage.md` | Human-readable policy gate coverage matrix for committed Hurl tests. |
| `entroping report gate-coverage --output json` | `reports/gate-coverage.json` | Machine-readable policy gate coverage matrix using `entroping.gate-coverage-report.v1`. |
| `entroping report gate-coverage --fail-under <0-100>` | `reports/gate-coverage.md` or `reports/gate-coverage.json` | Optional threshold gate over matched policy-gate coverage evidence. |
| `entroping report gate-injection --output md` | `reports/gate-injection.md` | Human-readable gate-injection explanation for selected Hurl files. |
| `entroping report gate-injection --output json` | `reports/gate-injection.json` | Machine-readable gate-injection explanation using `entroping.gate-injection-report.v1`. |
| `entroping report test-quality --output md` | `reports/test-quality.md` | Human-readable generated-Hurl quality score. |
| `entroping report test-quality --output json` | `reports/test-quality.json` | Machine-readable generated-Hurl quality score using `entroping.test-quality-report.v1`. |
| `entroping report test-quality --fail-under <0-100>` | `reports/test-quality.md` or `reports/test-quality.json` | Optional threshold gate over static generated-Hurl quality evidence. |
| `entroping report test-pyramid --output md` | `reports/test-pyramid.md` | Human-readable local test/evidence layer summary from existing artifacts. |
| `entroping report test-pyramid --output json` | `reports/test-pyramid.json` | Machine-readable local test/evidence layer summary using `entroping.test-pyramid-report.v1`. |
| `entroping report external-test-evidence --output md` | `reports/external-test-evidence.md` | Human-readable counts-only local external test evidence packet from fixed JUnit, coverage, LCOV, and SARIF artifact paths. |
| `entroping report external-test-evidence --output json` | `reports/external-test-evidence.json` | Machine-readable external test evidence packet using `entroping.external-test-evidence.v1`. |
| `entroping report artifact-manifest [--fail-on-incomplete]` | `reports/artifact-manifest.json` and `.entroping/report-audit-chain.jsonl` | Machine-readable checksum manifest using `entroping.report-artifact-manifest.v1` plus a local tamper-evident audit chain using `entroping.report-audit-event.v1`; the optional guard exits nonzero after writing when expected artifacts are missing or audit verification is broken, and the chain is local state and not committed. |
| `entroping report evidence-bundle` | `reports/evidence-bundle.json`, or Markdown when `--output` ends in `.md` or `.markdown` | Sanitized design-partner upload-readiness evidence using `entroping.evidence-bundle.v1`; references local artifacts by path, schema, size, checksum, readiness, diagnostics, and local remediation hints without embedding contents, executing fixes, or uploading. |
| `entroping report design-partner-feedback` | `reports/design-partner-feedback.json` | Schema-valid sanitized product-learning template using `entroping.design-partner-feedback.v1`; records value-free evidence statuses and leaves manual feedback fields for concise sanitized summaries. |
| `entroping report runtime-card --output md` | `reports/runtime-card.md` | Reviewer-facing PR/runtime evidence card from sanitized local reports, including design-partner pilot readiness and optional test-pyramid evidence. |
| `entroping report runtime-card --output json` | `reports/runtime-card.json` | Machine-readable PR/runtime evidence card using `entroping.runtime-card.v1`, including additive `pilot_readiness` and `test_pyramid` evidence. |
| `entroping report handoff --output md` | `reports/handoff.md` | Human-readable local cross-surface handoff packet from sanitized evidence artifacts. |
| `entroping report handoff --output json` | `reports/handoff.json` | Machine-readable local cross-surface handoff packet using `entroping.handoff.v1`. |
| `entroping report notification-packet --output md` | `reports/notification-packet.md` | Human-readable read-only notification packet for work-management, chat, automation, and agent surfaces. |
| `entroping report notification-packet --output json` | `reports/notification-packet.json` | Machine-readable notification packet using `entroping.notification-packet.v1`. |
| `entroping report team-evidence-readiness --output md` | `reports/team-evidence-readiness.md` | Human-readable read-only team evidence cloud readiness from sanitized local report artifacts. |
| `entroping report team-evidence-readiness --output json` | `reports/team-evidence-readiness.json` | Machine-readable team evidence readiness packet using `entroping.team-evidence-readiness.v1`. |
| `entroping report team-access-control-plan --output md` | `reports/team-access-control-plan.md` | Human-readable read-only team access-control and audit plan for future team evidence surfaces. |
| `entroping report team-access-control-plan --output json` | `reports/team-access-control-plan.json` | Machine-readable team access-control plan packet using `entroping.team-access-control-plan.v1`. |
| `entroping report integration-readiness --output md` | `reports/integration-readiness.md` | Human-readable read-only integration readiness packet for issue tracker, chat, enterprise automation, cross-surface continuity, observability, and API governance surfaces. |
| `entroping report integration-readiness --output json` | `reports/integration-readiness.json` | Machine-readable integration readiness packet using `entroping.integration-readiness.v1`. |
| `entroping report devex-readiness --output md` | `reports/devex-readiness.md` | Human-readable read-only developer experience readiness packet for CLI, VS Code/editor, local workbench, PR runtime card, desktop, cloud, and mobile surfaces. |
| `entroping report devex-readiness --output json` | `reports/devex-readiness.json` | Machine-readable developer experience readiness packet using `entroping.devex-readiness.v1`. |
| `entroping report evidence-cloud-readiness --output md` | `reports/evidence-cloud-readiness.md` | Human-readable read-only Evidence Cloud readiness packet from sanitized local report artifacts. |
| `entroping report evidence-cloud-readiness --output json` | `reports/evidence-cloud-readiness.json` | Machine-readable Evidence Cloud readiness packet using `entroping.evidence-cloud-readiness.v1`. |
| `entroping report evidence-cloud-export --output md` | `reports/evidence-cloud-export.md` | Human-readable local Evidence Cloud export manifest from sanitized report metadata. |
| `entroping report evidence-cloud-export --output json` | `reports/evidence-cloud-export.json` | Machine-readable Evidence Cloud export manifest using `entroping.evidence-cloud-export.v1`. |
| `entroping report evidence-cloud-workspace --manifest <path> --output md|json` | `reports/evidence-cloud-workspace.md`, `reports/evidence-cloud-workspace.json` | Local Evidence Cloud workspace packet using `entroping.evidence-cloud-workspace.v1`. |
| `entroping report evidence-cloud-dashboard --manifest <path> --output html|json` | `reports/evidence-cloud-dashboard.html`, `reports/evidence-cloud-dashboard.json` | Static local Evidence Cloud workspace dashboard using `entroping.evidence-cloud-dashboard.v1`. |
| `entroping report evidence-links --output md` | `reports/evidence-links.md` | Human-readable read-only cross-surface evidence links packet from sanitized local report artifacts. |
| `entroping report evidence-links --output json` | `reports/evidence-links.json` | Machine-readable evidence links packet using `entroping.evidence-links.v1`. |
| `entroping report evidence-portal --output html` | `reports/evidence-portal.html` | Static local read-only evidence portal dashboard from sanitized local report artifacts. |
| `entroping report evidence-portal --output json` | `reports/evidence-portal.json` | Machine-readable evidence portal packet using `entroping.evidence-portal.v1`. |
| `entroping report pr-evidence-card --output md` | `reports/pr-evidence-card.md` | Human-readable local PR evidence card. |
| `entroping report pr-evidence-card --output json` | `reports/pr-evidence-card.json` | Machine-readable PR evidence card using `entroping.pr-evidence-card.v1`. |
| `entroping report evidence-action-plan --output md` | `reports/evidence-action-plan.md` | Human-readable prioritized local evidence action plan. |
| `entroping report evidence-action-plan --output json` | `reports/evidence-action-plan.json` | Machine-readable evidence action-plan packet using `entroping.evidence-action-plan.v1`. |
| `entroping report work-item-draft --output md` | `reports/work-item-draft.md` | Human-readable read-only tracker draft rows from sanitized local evidence artifacts. |
| `entroping report work-item-draft --output json` | `reports/work-item-draft.json` | Machine-readable work item draft packet using `entroping.work-item-draft.v1`. |
| `entroping report work-item-import-bundle --output json` | `reports/work-item-import-bundle.json` | Machine-readable tracker import bundle using `entroping.work-item-import-bundle.v1`. |
| `entroping report work-item-import-bundle --output csv` | `reports/work-item-import-bundle.csv` | Spreadsheet-safe tracker import rows generated from the local work item draft packet. |
| `entroping report pilot-outcome --output md` | `reports/pilot-outcome.md` | Human-readable local design-partner pilot outcome packet from sanitized evidence artifacts. |
| `entroping report pilot-outcome --output json` | `reports/pilot-outcome.json` | Machine-readable pilot outcome packet using `entroping.pilot-outcome.v1`. |
| `entroping report pilot-cohort --manifest <path> --output md` | `reports/pilot-cohort.md` | Human-readable local design-partner cohort rollup from explicit pilot outcome packets. |
| `entroping report pilot-cohort --manifest <path> --output json` | `reports/pilot-cohort.json` | Machine-readable pilot cohort packet using `entroping.pilot-cohort.v1`. |
| `entroping report connector-intent --output md` | `reports/connector-intent.md` | Human-readable read-only connector intent packet for issue tracker, chat, enterprise automation, enterprise AI, observability, and developer-experience surfaces. |
| `entroping report connector-intent --output json` | `reports/connector-intent.json` | Machine-readable connector intent packet using `entroping.connector-intent.v1`. |
| `entroping report observability-packet --output md` | `reports/observability-packet.md` | Human-readable read-only observability signal packet for OpenTelemetry, Datadog, Splunk, Grafana, and generic surfaces. |
| `entroping report observability-packet --output json` | `reports/observability-packet.json` | Machine-readable observability packet using `entroping.observability-packet.v1`. |
| `entroping report otel-mapping --output md` | `reports/otel-mapping.md` | Human-readable OpenTelemetry evidence mapping packet for future OTLP adapters. |
| `entroping report otel-mapping --output json` | `reports/otel-mapping.json` | Machine-readable OpenTelemetry mapping packet using `entroping.otel-mapping.v1`. |
| `entroping report otlp-preview --output md` | `reports/otlp-preview.md` | Human-readable local OTLP-shaped preview fixture; not an exporter. |
| `entroping report otlp-preview --output json` | `reports/otlp-preview.json` | Machine-readable local OTLP preview packet using `entroping.otlp-preview.v1`. |
| `entroping report observability-adapter-readiness --output md` | `reports/observability-adapter-readiness.md` | Human-readable read-only observability adapter readiness packet. |
| `entroping report observability-adapter-readiness --output json` | `reports/observability-adapter-readiness.json` | Machine-readable observability adapter readiness packet using `entroping.observability-adapter-readiness.v1`. |
| `entroping report api-inventory --output md` | `reports/api-inventory.md` | Human-readable read-only API style inventory for REST/OpenAPI, GraphQL, SOAP/XML, gRPC/proto, AsyncAPI, webhook/event, WebSocket/realtime, and unknown HTTP signals. |
| `entroping report api-inventory --output json` | `reports/api-inventory.json` | Machine-readable API inventory packet using `entroping.api-inventory.v1`. |
| `entroping report mutation-readiness --output md` | `reports/mutation-readiness.md` | Human-readable read-only mutation/fuzz readiness summary from generated-Hurl and optional local report evidence. |
| `entroping report mutation-readiness --output json` | `reports/mutation-readiness.json` | Machine-readable mutation/fuzz readiness packet using `entroping.mutation-readiness.v1`. |
| `entroping report evidence-index --output md` | `reports/evidence-index.md` | Human-readable read-only local evidence artifact index from canonical report inventory states. |
| `entroping report evidence-index --output json` | `reports/evidence-index.json` | Machine-readable local evidence artifact index using `entroping.evidence-index.v1`. |
| `entroping report qa-brain-seed --output md` | `reports/qa-brain-seed.md` | Human-readable read-only QA Brain seed metadata from canonical evidence-index states. |
| `entroping report qa-brain-seed --output json` | `reports/qa-brain-seed.json` | Machine-readable QA Brain seed packet using `entroping.qa-brain-seed.v1`. |
| `entroping report qa-brain-eval-plan --output md` | `reports/qa-brain-eval-plan.md` | Human-readable read-only QA Brain eval-plan metadata derived from seed readiness. |
| `entroping report qa-brain-eval-plan --output json` | `reports/qa-brain-eval-plan.json` | Machine-readable QA Brain eval-plan packet using `entroping.qa-brain-eval-plan.v1`. |
| `entroping report qa-brain-retrieval-plan --output md` | `reports/qa-brain-retrieval-plan.md` | Human-readable read-only QA Brain retrieval-plan metadata derived from eval-plan readiness. |
| `entroping report qa-brain-retrieval-plan --output json` | `reports/qa-brain-retrieval-plan.json` | Machine-readable QA Brain retrieval-plan packet using `entroping.qa-brain-retrieval-plan.v1`. |
| `entroping report qa-brain-prompt-plan --output md` | `reports/qa-brain-prompt-plan.md` | Human-readable read-only QA Brain prompt-plan metadata derived from retrieval-plan readiness. |
| `entroping report qa-brain-prompt-plan --output json` | `reports/qa-brain-prompt-plan.json` | Machine-readable QA Brain prompt-plan packet using `entroping.qa-brain-prompt-plan.v1`. |
| `entroping report qa-brain-fine-tune-readiness --output md` | `reports/qa-brain-fine-tune-readiness.md` | Human-readable read-only QA Brain fine-tune readiness metadata derived from prompt-plan readiness. |
| `entroping report qa-brain-fine-tune-readiness --output json` | `reports/qa-brain-fine-tune-readiness.json` | Machine-readable QA Brain fine-tune readiness packet using `entroping.qa-brain-fine-tune-readiness.v1`. |
| `entroping report qa-brain-model-packaging-plan --output md` | `reports/qa-brain-model-packaging-plan.md` | Human-readable read-only QA Brain model-packaging plan metadata derived from fine-tune readiness. |
| `entroping report qa-brain-model-packaging-plan --output json` | `reports/qa-brain-model-packaging-plan.json` | Machine-readable QA Brain model-packaging plan packet using `entroping.qa-brain-model-packaging-plan.v1`. |
| `entroping report qa-brain-routing-plan --output md` | `reports/qa-brain-routing-plan.md` | Human-readable read-only QA Brain routing-plan metadata derived from model-packaging readiness. |
| `entroping report qa-brain-routing-plan --output json` | `reports/qa-brain-routing-plan.json` | Machine-readable QA Brain routing-plan packet using `entroping.qa-brain-routing-plan.v1`. |
| `entroping report qa-brain-repair-plan --output md` | `reports/qa-brain-repair-plan.md` | Human-readable read-only QA Brain repair-plan metadata from value-free local quality, mutation, action-plan, routing-plan, and evidence-index states. |
| `entroping report qa-brain-repair-plan --output json` | `reports/qa-brain-repair-plan.json` | Machine-readable QA Brain repair-plan packet using `entroping.qa-brain-repair-plan.v1`. |
| `entroping report pilot-metrics --output md` | `reports/pilot-metrics.md` | Human-readable local pilot metric inference from sanitized artifacts, with `unknown` and `manual_input_required` states for metrics Entroping cannot infer locally. |
| `entroping report pilot-metrics --output json` | `reports/pilot-metrics.json` | Machine-readable local pilot metric inference using `entroping.pilot-metrics.v1`. |
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

Entroping uses a local-first diagnostics boundary before any vendor-specific
observability adapter. `entroping.run-events.v1` remains the per-run execution
progress log for deterministic Hurl runs. `entroping.diagnostics.v1` is the
broader headless component-event contract for agents, reports, doctor checks,
and future observability adapters.

Structured diagnostics may include only value-free fields:

- Component, operation, severity, code, and short summary.
- Counts, durations, statuses, classifications, and relative artifact paths.
- Gate IDs, auth-chain flow IDs, Hurl variable names, and agent role/model
  metadata when they are names or classifications rather than values.
- Latency, token usage, and estimated cost where available.

Diagnostics must not include request secrets, API keys, cookies, raw traffic,
prompts, provider output, environment values, response bodies, request bodies,
headers, or full source Hurl contents. Value-bearing attribute names such as
`api_token`, `request_body`, `response_body`, `prompt`, `provider_output`,
`source_hurl`, and `env_value` fail closed before serialization. Secret-shaped
text is redacted through the shared credential redaction primitive, and completed
JSONL records must validate against `entroping.diagnostics.v1`. Datadog,
Splunk, OpenTelemetry, or other vendor adapters stay downstream of this local
contract and must not become prerequisites for deterministic local operation.

### 17.1 Factory Artifact Retention

The local software factory keeps operational artifacts only under ignored
`.entroping/` roots. A versioned policy defines independent terminal-state age
limits and aggregate byte ceilings for completed or failed job records,
accepted or rejected review bundles, rotated tick logs, finished-issue metrics
archives, and terminal retention receipts. Active tick logs are inventoried but
protected. Active factory metrics use a separate locked 64 MiB aggregate cap;
finished-issue archives do not consume that live allowance.

Retention is deterministic and provider-free. Planning is read-only. Explicit
apply takes an exclusive repo-local lock, rejects tracked targets, re-inventories
bounded descriptor-based roots without following symlinks, compares content
fingerprints, and stages selected entries into same-filesystem transaction
trash. A durable journal authorizes only the transaction that created it:
recovery rolls back an interrupted moving journal with pending operations, or
completes a fully staged or purging journal. Terminal journal receipts are
themselves subject to retention, so recovery evidence does not grow forever.
Both new and adopted journals are capped at 4,096 operations and use canonical
transaction-trash names, preventing recovery data from widening deletion or
unbounded rewrite work.

Traversal has finite per-directory, aggregate-entry, depth, metadata-read, and
hashed-byte limits. Policy ceilings total at most 4 GiB inside an 8 GiB
inventory budget, preserving bounded over-cap headroom. Malformed metadata,
control-bearing names, special files, unknown references, unresolved
settlements, legacy metrics archives without terminal provenance, or
fingerprint drift fail closed. Terminal metrics provenance binds each canonical
ledger path to its exact byte count and SHA-256 digest, which inventory
revalidates before retention eligibility. Archive creation verifies the fully
serialized provenance metadata fits the 64 KiB reader bound before copying any
destination ledger. Reports expose only artifact identifiers,
classes, states, timestamps, relative paths, reason codes, counts, and byte
totals; artifact contents are never rendered.

### 17.2 Factory Budget Ledger

Factory cash authority is isolated from the product traffic store in the
ignored `.entroping/factory-budget/ledger.sqlite3` database. The versioned
SQLite schema records UTC cash periods, their reviewed USD cap and positive
reserve, immutable reserve allocations, fixed subscription and provider debits,
charge-bound refunds, and explicit manual debit or credit adjustments. Raw
idempotency keys are never persisted: a globally unique SHA-256 digest is bound
to the normalized entry payload, so exact retries are harmless and conflicting
reuse fails closed.

Period initialization and entry recording open bounded connections and enclose
idempotency, reference, refund, period, entry-count, cash-cap, insert, and
cached-balance checks in `BEGIN IMMEDIATE`. One-time schema bootstrap uses
`BEGIN EXCLUSIVE`. SQLite therefore admits only one successful writer at the
decision boundary. `journal_mode=DELETE` with `synchronous=EXTRA`
supports crash-safe rollback-journal commits and genuinely read-only summary
connections without creating WAL state. A pre-connect, no-follow database-header
check rejects WAL-mode drift before SQLite can create sidecars. Initialization
publishes a fully validated temporary database by same-directory hard link and
directory sync;
unpublished partial initialization is discarded before retry.

Descriptor-based path validation walks every no-follow repository ancestor and
rejects parent rename authority unless the parent is root/user-owned and any
cross-account write bits are constrained by sticky-directory protection for a
root/user-owned child. The repository root and shared `.entroping` state are
effective-user-owned and non-group/other-writable; existing owner-controlled
0755 shared state is compatible, while the ledger directory is 0700. Stable
pre/post-open file identity checks, non-creating URI opens, shared retention
locking, 0600 owner-only files, strict tables, foreign keys, immutable-entry and
immutable-period-authority triggers, exact schema validation, integrity checks,
signed 64-bit arithmetic, a 512 MiB database ceiling, a 100,000-entry global
ceiling, a 600-period global ceiling, and a 100,000-entry period ceiling bound
the storage surface. Retry safely removes the reserved initialization name when
a crash leaves it hard-linked to the published validated inode.
Timestamp validation streams in fixed batches. Malformed, partial, future, or
drifted schemas are rejected and preserved for inspection. The local trust
boundary excludes noncooperating same-UID mutation; exact
descriptor-to-SQLite binding would require OS isolation or a custom/native VFS.
CLI access is read-only and value-bounded. Provider reservation, settlement,
quota observation, scheduler authorization, and provider calls stay outside
this component.

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

External integrations should be tested with small fixtures and deterministic subprocess stubs where possible. A smoke suite should exercise real Hurl when available. Bounded scalability evidence is generated through `uv run python scripts/performance_smoke.py`, which writes ignored JSON evidence under `reports/performance-smoke.json`; `scripts/audit_quality.sh` now runs that smoke so pull-request CI enforces the same local large-suite, report, and traffic-store guard.

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
`uv pip install --offline`, runs installed public CLI commands:
`entroping --version`, `entroping init --minimal`, and `entroping doctor`,
then exercises the installed demo path against the checkout fixture when Hurl
is available. When Hurl is missing, the demo portion is recorded as an explicit
skip. The smoke emits `entroping.local-wheel-install-smoke.v1` evidence and
remains separate from TestPyPI/PyPI package-index proof.

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
