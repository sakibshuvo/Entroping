# Entroping Product Specification

**Project:** Entroping
**Spec Version:** 4.1
**Implementation Maturity:** Alpha; stable-core readiness is blocked by `package_index_proof` and `real_downstream_feedback`.
**Status:** Current product contract, not a stable-core release claim
**Versioning Note:** v4.1 is the product/spec/CLI contract generation, not the Python package release version; package releases use alpha Git tags and PEP 440 package metadata tracked from `pyproject.toml`.
**Philosophy:** The QAnstitution is Law. Traffic is Truth. Hurl is the Enforcer.

## 1. Executive Summary

Entroping is an AI-first quality governance platform for API and backend systems. It protects high-velocity AI-assisted development by turning product intent, API specifications, live traffic, and governance rules into deterministic Hurl tests that can block unsafe changes in local development and CI.

The product is not a general chatbot, a static analyzer, or a replacement for all testing. Entroping is a local-first integrity agent for runtime behavior. It lets AI generate and maintain tests, but it relies on the Rust `hurl` binary to enforce the final pass/fail result.

In public positioning, Entroping is a runtime governance and compliance-evidence layer for AI-assisted backend/API changes. It is not an autonomous agent swarm, and it does not approve behavior through model judgment.

## 2. Product Thesis

AI coding tools can generate code faster than teams can manually validate it. Static review catches only part of the risk because many regressions are runtime problems: wrong status codes, broken auth flows, schema drift, latency breaches, missing headers, data exposure, and undocumented service dependencies.

Entroping closes that gap by making quality policy executable:

- Developers keep coding at AI speed.
- Architects define reusable quality law once.
- CI rejects behavior that violates the law.
- Live traffic becomes regression evidence instead of tribal knowledge.

## 3. Core Value Proposition

### For Developers

Write product code, not repetitive API tests. Entroping generates, updates, and refactors Hurl tests from specs, prompts, user stories, and recorded traffic.

### For Architects and Platform Teams

Define governance in `qanstitution.yaml`, import central policy, and enforce it across repos without depending on every team to remember every rule.

### For QA and SDET Teams

Move from manual script maintenance to quality governance: curate risk models, review generated tests, approve golden flows, and maintain known-failure policy.

### For Leadership

Get binary assurance. A build either passes the QAnstitution, or it fails with reproducible evidence.

## 4. Positioning

Entroping is best described as:

- An AI-native integrity agent.
- A runtime governance layer for AI-generated code.
- A CI/CD firewall for backend behavior.
- Git-native API quality infrastructure.
- A deterministic governor that coding agents and CI systems can invoke before code is allowed to merge.

It is not primarily:

- A browser E2E testing framework.
- A SaaS-only test recorder.
- A static code review tool.
- A generic prompt wrapper.
- A replacement for unit tests.

### Backend/API Integrity Position

Entroping's core positioning is to make backend/API behavior deterministic and testable through local execution evidence:

- **Backend/API integrity over generic AI output.** The CLI uses AI to scale test production, but merges only when executable governance and Hurl evidence pass.
- **Policy-backed API quality.** `qanstitution.yaml` captures local governance rules and can include security, latency, status-shape, and dependency expectations.
- **Traffic-informed governance.** Observed, redacted traffic is converted into reproducible test and mock artifacts when useful, while still requiring review before merge.
- **Evidence-first operations.** PRs and releases stay on explicit JSON/JUnit/HTML/sarif artifacts instead of implicit model confidence scores.
- **Runtime determinism first.** `entroping run` and report generation remain the enforcement boundary; provider calls do not alter pass/fail decisions.

QAnstitution enforcement is evaluated at the Hurl boundary: all matching gates
for a selected source are injected into one bounded temporary copy and share one
Hurl invocation per attempt; no enforcement mode adds a request sequence. JSON,
JUnit, and HTML preserve their
rule ID, enforcement, result, and exit evidence. A failed `block` gate makes the
run fail; failed `warn` and `audit_only` gates remain observable without changing
the run exit status.

## 5. Operating Principles

1. **QAnstitution is Law:** Governance rules live in versioned YAML and are injected into every relevant run.
2. **Traffic is Truth:** Observed runtime behavior is a first-class source for tests, mocks, and dependency maps.
3. **Hurl is the Enforcer:** Final execution is deterministic and external to the LLM.
4. **Git is the Memory:** Tests, rules, stories, agent personas, and reports are inspectable text artifacts.
5. **AI Suggests, Runtime Decides:** LLMs generate and refactor, but `hurl` and policy gates decide pass or fail.
6. **Local First:** The CLI works without a hosted control plane. Cloud features are optional future extensions.
7. **Human Intent Wins:** AI handles volume; humans own risk, policy, and review.
8. **Source-Bound Intelligence:** The Architect must ground generated tests in configured specs, stories, traffic, dependencies, or explicit user prompts. It must not silently invent unsupported endpoints.

## 6. Primary Personas

| Persona | Goal | Entroping Outcome |
| --- | --- | --- |
| AI-assisted developer | Ship quickly without silent regressions | Generate and run Hurl tests locally before PRs |
| Platform architect | Enforce shared quality rules | Federated QAnstitution imports and CI gates |
| QA/SDET lead | Scale test coverage without brittle maintenance | AI-assisted test generation, refactor, audit, and freeze |
| Engineering manager | Reduce release risk from AI-generated code | Deterministic reports, JUnit, drift findings, and bug templates |
| Legacy system owner | Create tests without complete specs | Record traffic, freeze flows, and generate mocks |
| Autonomous coding agent / CI system | Prove generated code before merge | Invoke `entroping run --ci` as a deterministic firewall |

## 7. The Four Pillars

### 7.1 Intelligence: The Architect

The Architect is an AI-assisted subsystem.

The Architect converts structured and unstructured intent into Hurl tests. It uses role-specific agents defined in `qanstitution.yaml`:

- **Builder:** Generates positive-path and contract tests from specs and stories.
- **Auditor:** Reviews coverage, traceability, policy gaps, and brittle assertions.
- **Breaker:** Generates hostile, boundary, security, and negative tests.

The Architect must preserve manual edits when updating existing tests. It validates generated Hurl with a parser-backed syntax validation step before writing files, stages AI output as reviewable file diffs, and must not auto-merge generated changes.

### 7.2 Observation: The Eye

The Eye records live HTTP/S traffic through `mitmproxy`. It stores normalized, redacted traffic in local SQLite state, then converts sessions into:

- Hurl regression tests.
- Golden master assertions.
- WireMock-compatible mocks for service dependencies.
- Service dependency maps.

Traffic capture is especially important for legacy APIs and AI-generated services with incomplete documentation. The Eye should filter low-value noise such as static assets and analytics calls, then stitch related requests into user-flow sessions.

### 7.3 Execution: The Enforcer

The Enforcer wraps the external Rust `hurl` binary. It does not execute HTTP requests through Python HTTP client libraries.

Runtime responsibilities:

- Resolve test files, tags, and environment variables.
- Load `qanstitution.yaml` and imported governance rules.
- Inject matching gates into execution copies of tests.
- Fail early on unresolved Hurl variables before subprocess execution.
- Run Hurl with deterministic subprocess calls.
- Emit local reports and strict CI exit codes.

### 7.4 Lifecycle Management

Entroping manages the QA lifecycle as Git-native assets:

- Tests are `.hurl` files.
- Tags define virtual suites.
- Markdown user stories under `docs/stories/*.md` link to tests through Entroping-readable Hurl comments such as `# entroping: story_id=CHK-001`; the shipped bridge compiles this local metadata into traceability reports and gap summaries without calling external business-system APIs.
- Known failures require issue IDs, reasons, and expiry dates.
- Reports provide machine-readable and human-readable evidence.

AI-generated change quality is managed as a seeded evidence loop before any repair change is proposed:

- generated-test quality (`entroping report test-quality`) ->
  mutation/readiness (`entroping report mutation-readiness`) ->
  QA Brain packets (`qa-brain-seed`, `qa-brain-eval-plan`, `qa-brain-retrieval-plan`, `qa-brain-prompt-plan`, `qa-brain-routing-plan`) ->
  repair-plan (`entroping report qa-brain-repair-plan`).
- Every stage is advisory and read-only; deterministic Hurl execution (`entroping run --ci`) remains the release gate.
- Local product-learning artifacts, such as
  `reports/design-partner-feedback.json`, may preserve sanitized pilot feedback
  through explicit local report commands without claiming market validation.
  A GitHub issue may receive verified-user scheduling priority only when its
  closed `entroping.user-evidence.v1` metadata includes the matching digest of
  that sanitized local artifact and a maintainer has applied the
  `evidence:user-verified` label. After the complete fresh-state, issue contract,
  milestone, verification, autonomy, ownership, active unmerged branch, PR,
  lease, explicit-file-scope, overlap, and dependency gates implemented by
  issue #1567 pass, precedence is `priority:p0`, verified user blockers,
  verified user-evidence `priority:p1`, then other ready work. Raw feedback and
  private conversations never enter GitHub or provider prompts. This prioritization is
  product-learning policy, not proof of market validation; the exact
  issue-body contract, fail-closed rules, and non-quota work-mix receipt
  semantics live in `docs/meta/ISSUE_TRACKING.md`.

## 8. Locked Command Surface

The v4.1 command namespace is intentionally small and stable:

| Area | Commands |
| --- | --- |
| Setup | `init`, `doctor`, `config` |
| Intelligence | `architect build`, `architect refactor`, `architect audit` |
| Observation | `watch`, `freeze`, `map` |
| Execution | `run`, `studio` |
| Reporting | `report bug`, `report failure-bundle`, `report delta`, `report badges`, `report redaction`, `report capture-summary`, `report policy`, `report policy-diff`, `report gate-coverage`, `report gate-injection`, `report test-quality`, `report test-pyramid`, `report artifact-manifest`, `report evidence-bundle`, `report design-partner-feedback`, `report runtime-card`, `report agent-bundle`, `report traceability`, `report github-annotations`, `report sarif`, `report promote-drift-baseline`, `report review-summary` |

Deprecated or historical commands such as `gen`, `fix`, `ui`, `build`, `scan`, `verify`, `explain`, and `chaos` must not be treated as primary v4.1 commands. They can exist only as explicit backwards-compatible aliases or future roadmap items.

## 9. Functional Requirements

### 9.1 Setup and Configuration

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| SET-001 | Initialize a project with standard Entroping files | `entroping init` creates `qanstitution.yaml`, `tests/`, `envs/`, `agents/`, `rules/`, `.entroping/`, and starter docs |
| SET-002 | Support minimal initialization | `entroping init --minimal` creates only required runtime files |
| SET-003 | Validate local and CI toolchain readiness | `entroping doctor` checks Python runtime, Hurl binary availability and version compatibility, mitmproxy, SQLite state, config, readable rules, configured agent persona safety, and non-secret provider env readiness; `--ci` adds strict Hurl compatibility, report-path, suite-manifest, Hurl-variable, and provider-free run checks for PR gates; `--output json` emits schema version `entroping.doctor.v1` for automation |
| SET-004 | Configure agent model routing | `entroping config set --agent auditor --model <id>` updates local configuration without printing secrets |
| SET-005 | List effective config | `entroping config list` shows resolved non-secret configuration and imported rules |
| SET-006 | Support local-first brain setup | AI commands can use an Ollama-backed local model by default and cloud models only through explicit configuration |
| SET-007 | Store credentials safely | API keys are read from environment variables; plaintext config files must not contain secrets, and OS credential storage is future work |
| SET-008 | Vendor reviewed local policy packs | `entroping config vendor-policy-pack --pack <path> [--name <dir>]` copies a local pack under `policy-packs/`, validates the manifest and QAnstitution entrypoint, preserves final-gate behavior, and appends a local import without remote registry behavior |
| SET-009 | Self-test local policy packs | `entroping config test-policy-pack --pack <path> [--output text|json]` validates a local pack before vendoring or publishing without network access, provider keys, or project mutation |
| SET-010 | Install an optional CI starter workflow | `entroping init --github-actions` writes the reviewed starter to `.github/workflows/entroping.yml`, refuses existing workflows, keeps Hurl pinned, and adds no secrets, provider credentials, hosted-service coupling, or package-index readiness claims |

### 9.2 QAnstitution Governance

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| GOV-001 | Load `qanstitution.yaml` with schema validation | Invalid files fail fast with actionable line/path errors |
| GOV-002 | Support local-file imports | Local imported gates merge before execution; HTTP(S) imports are rejected and remain future work |
| GOV-003 | Support local overrides | Local gates with the same ID override imported gates unless the imported gate is marked `final: true` |
| GOV-004 | Support gate matching conditions | Conditions can match tags, method, path, URL, metadata, and a global `true` condition |
| GOV-005 | Support enforcement levels | `block`, `warn`, and `audit_only` are represented in reports and exit behavior |
| GOV-006 | Support known-failure exceptions | Exceptions require test ID, rule ID, issue ID, reason, and expiry |
| GOV-007 | Preserve auditability | Effective policy, skipped gates, warnings, and overrides are visible in run output and reports |
| GOV-008 | Support reusable local gate groups | `gate_groups` expand predictably into ordinary gates, reject missing references and cycles, preserve import/final semantics, and expose source group provenance in effective-policy reports |

### 9.3 Architect Intelligence

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| INT-001 | Generate tests from OpenAPI | `architect build --new` creates valid Hurl tests for operations, common parameters, schemas, and supported OpenAPI auth-negative coverage; `--changed-from <ref>` focuses regeneration to current added, modified, or renamed OpenAPI operations relative to a Git base ref |
| INT-002 | Generate directed tests from prompts | `architect build --prompt "<intent>"` creates scoped Builder Hurl changes; `--agent breaker` routes hostile/security generation through Breaker |
| INT-003 | Support merge strategy | `architect build --strategy merge` updates generated regions without overwriting manual regions |
| INT-004 | Tag generated tests | `architect build --tag smoke` writes Entroping metadata comments that Hurl ignores safely; Breaker output is additionally tagged `breaker` |
| INT-005 | Refactor existing Hurl tests | `architect refactor --target "tests/**/*.hurl" --prompt "<change>"` preserves comments and validates output |
| INT-005A | Preview Hurl refactors | `architect refactor --target "tests/**/*.hurl" --prompt "<change>" --preview` renders a validated unified diff without writing target files; preview is review evidence, not execution proof |
| INT-005B | Keep self-healing maintenance review-first | Architect may propose Hurl updates from an explicit prompt, OpenAPI diff, failing deterministic run evidence, or drift report; proposals stay diff/manifest-backed, never auto-commit or merge, and agent manifests record value-free source evidence |
| INT-006 | Audit gaps | `architect audit --focus logic --output md|json` reports deterministic OpenAPI coverage gaps with an operation-to-Hurl matrix, stale operation references, and optional redacted traffic-vs-OpenAPI route findings when captured traffic state exists; `--changed-from <ref>` adds deterministic OpenAPI breaking-change diff findings without generating or deleting tests; `--focus auditor` runs an explicit Auditor review with validated Markdown or JSON findings |
| INT-007 | Validate generated Hurl | Generated or refactored files must pass parser-backed syntax validation before being accepted |
| INT-008 | Use configured model routing | Builder and Breaker load persona files and models for prompt builds; Auditor loads persona/model routing for explicit audit reviews |
| INT-009 | Enforce source grounding | Generated endpoints and assertions must be traceable to OpenAPI, GraphQL schema, stories, observed traffic, dependencies, or explicit prompt context |
| INT-010 | Keep AI out of deterministic runs | `entroping run` must not call the LLM; Breaker output is generated through Architect commands and committed as tests before execution |
| INT-011 | Record sanitized AI budget and source evidence | Prompt-backed Architect build, refactor, and Auditor review outputs expose provider, latency, token counts when available, estimated cost when local rate hints are configured, and value-free source evidence without storing prompts, secrets, target Hurl contents, or raw provider responses |

### 9.4 Traffic Observation

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| OBS-001 | Start local proxy | `entroping watch --port 8080 --target http://localhost:3000` records proxied traffic |
| OBS-002 | Record traffic safely | Requests and responses are normalized and redacted before SQLite persistence |
| OBS-003 | Freeze sessions into tests | `entroping freeze --name checkout_flow` writes parameterized Hurl files |
| OBS-004 | Support golden masters | `entroping freeze --golden` captures stable body/header/status assertions for regression |
| OBS-005 | Generate mocks | `entroping freeze --mock payments` emits WireMock-compatible mappings for external services |
| OBS-006 | Map dependencies | `entroping map --export mermaid` creates service dependency graph artifacts |
| OBS-007 | Avoid hidden SaaS state | Captured data remains local unless the user explicitly exports or uploads it |
| OBS-008 | Filter capture noise | Static assets, analytics beacons, and irrelevant hosts can be excluded from traffic sessions |
| OBS-009 | Stitch sessions | Related captured calls are grouped into named or recent user-flow sessions before `freeze` |
| OBS-010 | Control state growth | Local state has retention or rotation settings so traffic capture cannot grow without bound |
| OBS-011 | Review generated traffic artifacts | `freeze`, `freeze --mock`, and `map --export png` write value-free approval manifests with generated paths, checksums, deterministic source fingerprints, and redaction summaries without raw traffic values |

### 9.5 Execution and Reporting

| ID | Requirement | Acceptance Criteria |
| --- | --- | --- |
| EXE-001 | Run suites by environment | `entroping run --env local` loads `envs/local.env` and environment variables |
| EXE-001A | Model local auth chains | Hurl files can declare value-free `auth_flow`, `auth_requires`, and `auth_produces` metadata so dry-run plans and JSON/JUnit/HTML reports show auth variable names only; secret values still come from env vars, shell `HURL_VARIABLE_*`, secret managers, or gitignored env files and are passed to Hurl through the existing variables-file boundary |
| EXE-002 | Filter by tags | `entroping run --tag smoke` runs matching tests across folders; `--tag-expression "smoke and not slow"` supports deterministic ad hoc boolean selection |
| EXE-003 | Run in CI mode | `entroping run --ci` emits strict exit codes and CI-friendly logs |
| EXE-004 | Run in parallel | `entroping run --parallel` uses bounded workers and deterministic aggregation |
| EXE-004A | Stop early on failure | `entroping run --fail-fast` stops scheduling additional tests after the first failing Hurl result and reports selected, executed, and not-scheduled counts |
| EXE-005 | Inject gates | Matching QAnstitution gates are injected into execution copies without mutating source tests |
| EXE-006 | Emit reports | Repeatable `--report html`, `--report junit`, `--report json`, and `--report drift` flags write reports under `reports/` |
| EXE-007 | Detect drift | `--drift-check` compares current behavior against baselines and reports breaking changes |
| EXE-008 | Generate bug reports | `entroping report bug` creates a Markdown bug template with exact Hurl/curl repro details |
| EXE-009 | Generate failure bundles | `entroping report failure-bundle` creates a sanitized local bundle with a versioned manifest, latest failed run evidence, bug Markdown, failed-test Hurl metadata, and reviewed local report artifacts without raw traffic, env files, uploads, or source Hurl contents |
| EXE-010 | Generate redaction review reports | `entroping report redaction --output md` and `--output html` summarize captured traffic redaction categories and counts without raw secrets |
| EXE-010 | Generate capture session summaries | `entroping report capture-summary --output md|json` summarizes redacted local traffic by derived session, method, host, dependency target, status family, and redaction category without rendering raw URLs, query values, headers, cookies, request bodies, response bodies, or tokens |
| EXE-011 | Run changed Hurl tests locally | `entroping run --changed-from <ref>` selects existing changed `.hurl` files from Git diff for fast feedback while full-suite `run` remains the default |
| EXE-011A | Rerun latest failures locally | `entroping run --rerun-failures` selects failed source `.hurl` files from the latest local run report, reuses the report environment unless `--env` overrides it, and keeps full-suite `run --ci` as the release gate |
| EXE-012 | Generate traceability reports | `entroping report traceability --output md|json` maps local Hurl metadata and `docs/stories/*.md` story files to stories, owners, docs, tests, tags, local story paths, and gap findings |
| EXE-013 | Generate SARIF reports | `entroping report sarif` writes SARIF 2.1.0 from local JUnit, drift, and optional traceability findings without uploading results |
| EXE-014 | Promote reviewed drift baselines | `entroping report promote-drift-baseline` validates a reviewed candidate before atomically writing `.entroping/drift-baseline.json` |
| EXE-015 | Provide read-only TUI workflow | `entroping studio --env local` opens optional Textual/Rich local inspection over sanitized reports and redacted state, including a read-only evidence viewer with stable evidence IDs for local report artifacts and a read-only pilot readiness panel for evidence-bundle schema, status, required artifact counts, diagnostics, checksum mismatch count, and artifact-manifest audit-chain status |
| EXE-016 | Preserve execution reproducibility | All blocking CI behavior must be explainable from committed Hurl files, env data, effective QAnstitution, and Hurl output |
| EXE-017 | Run named committed suites | `entroping run --suite smoke` loads `suites/smoke.yaml`, validates schema `entroping.suite.v1`, resolves root-bounded local path globs, and applies suite-defined env, tags, reports, parallel, fail-fast, and drift settings without changing default `run` behavior |
| EXE-018 | Report timeout evidence | JSON, JUnit, HTML, and review-summary artifacts show effective per-test `timeout_ms` and distinguish subprocess timeouts from Hurl assertion failures |
| EXE-019 | Compare run reports | `entroping report delta --base <path> --current <path> --output md|json` compares two local JSON run reports without executing Hurl, emits schema-versioned added/resolved/changed/unchanged failure, latency, and policy-gate deltas, and omits raw stdout/stderr |
| EXE-020 | Generate coverage badges | `entroping report badges` reads local run, effective-policy, OpenAPI audit, and traceability JSON reports and writes Shields-compatible badge JSON under `reports/badges/` without calling a hosted badge service |
| EXE-021 | Explain gate injection | `entroping report gate-injection --target <path> --output md|json` reports which effective QAnstitution gates would be injected into selected local Hurl files without running Hurl or mutating source `.hurl` files |
| EXE-022 | Preview run execution plans | `entroping run --dry-run` resolves selected Hurl files, filters, env names, requested reports, gate injection counts, and missing variable names without invoking Hurl, writing executed-run reports, or mutating source `.hurl` files; `--report json` writes `reports/run-plan.json` with schema `entroping.run-plan.v1` |
| EXE-022 | Map policy gate coverage | `entroping report gate-coverage --output md|json` reports which effective QAnstitution gates match committed Hurl tests, tags, methods, and paths, including unmatched gates, without executing Hurl or calling providers |
| EXE-022 | Diff effective policy evidence | `entroping report policy-diff --base <path> --current <path> --output md|json` compares two existing effective-policy JSON artifacts, reports import/gate additions, removals, and changed fields, and does not load policy files, call providers, execute Hurl, or fail just because valid evidence changed |
| EXE-023 | Manifest report artifacts | `entroping report artifact-manifest` writes local checksum evidence for standard report artifacts plus a tamper-evident `.entroping/report-audit-chain.jsonl` event with previous-hash linkage, verification status, and broken-chain diagnostics, rejecting oversized report artifacts before full reads or schema sniffing and without embedding artifact contents, secrets, raw traffic, provider prompts, provider outputs, env values, uploads, or signing/attestation claims |
| EXE-024 | Verify sanitized evidence bundles | `entroping report evidence-bundle` writes `reports/evidence-bundle.json` with required local run, effective-policy, and artifact-manifest readiness diagnostics, checksum references, full v1 artifact-contract validation, supported schema evidence, and artifact-manifest audit status without embedding artifact contents, raw traffic, source Hurl contents, stdout/stderr, prompts, provider outputs, credentials, env values, or uploading anything |
| EXE-025 | Summarize PR runtime evidence | `entroping report runtime-card` writes `reports/runtime-card.md` or `reports/runtime-card.json` from existing sanitized local report artifacts, requiring run JSON evidence and marking missing artifact-manifest or evidence-bundle release anchors as reviewer attention before a card can pass, while summarizing drift, redaction, release anchors, and agent provenance when present without executing Hurl, calling providers, uploading artifacts, or rendering raw Hurl output, raw traffic, prompts, provider responses, credentials, or env values |
| EXE-026 | Score generated-test quality | `entroping report test-quality --output md|json` writes static generated-Hurl quality evidence for assertion strength, brittle selectors, negative-path metadata, auth/security metadata, shallow schema checks, overfitted examples, and traceability gaps without executing Hurl, calling providers, uploading artifacts, rendering raw Hurl values, or replacing QAnstitution/Hurl pass-fail authority |
| EXE-028 | Summarize test-pyramid evidence | `entroping report test-pyramid --output md|json` classifies existing local report artifacts by code coverage, runtime API proof, policy governance, drift/contract, static/security, and generated-test quality, highlighting missing runtime-governance proof without executing Hurl or pytest, calling providers, uploading artifacts, parsing source Hurl, rendering raw artifact contents, or exposing raw traffic, stdout/stderr, prompts, env values, or source coverage file names |
| EXE-027 | Write design-partner feedback templates | `entroping report design-partner-feedback` writes `reports/design-partner-feedback.json` as a schema-valid sanitized local template with value-free evidence statuses from existing report artifacts and manual command-history or feedback fields set to `null` or `manual input required`, without executing Hurl, calling providers, reading raw traffic, uploading artifacts, or claiming validated demand |

## 10. Supported Test Types

| Test Type | Entroping Support | Notes |
| --- | --- | --- |
| Unit tests | Not owned | Codebase frameworks remain responsible |
| API contract tests | First-class for REST/OpenAPI | Generated from OpenAPI; GraphQL-over-HTTP remains an internal scaffold/hidden example |
| Functional API tests | First-class | Hurl workflows with captures and assertions |
| Integration tests | First-class | Multi-service chains and real dependencies |
| Component tests | Supported | Service under test plus generated mocks |
| API-driven E2E tests | Supported | Backend flows without browser UI dependency |
| Smoke tests | First-class | Tagged, prod-safe, strict QAnstitution gates |
| Visual UI tests | Out of scope | Use browser-specific tools |

## 11. Protocol Support

| Protocol | Contract 4.1 support level | Product behavior |
| --- | --- | --- |
| REST/OpenAPI | Shipped core | Mainline Hurl execution and OpenAPI compiler path |
| GraphQL-over-HTTP | Internal scaffold | Hidden example and local SDL scaffold only; no public schema command or native runtime guarantee |
| SOAP/XML-over-HTTP | Internal scaffold | Hidden example and local WSDL scaffold only; no public schema command or SOAP runtime |
| HTTP callback observation | Shipped advanced | Generic redacted traffic observation/freeze can preserve reviewed HTTP callback evidence |
| AsyncAPI webhooks | Internal scaffold | Local contract scaffold only; no broker, delivery, or webhook-specific runtime |
| Proto HTTP transcoding | Internal scaffold | Local HTTP-transcoding scaffold only; native gRPC and streaming are future work |
| WebSockets | Future | No handshake/message state-machine runtime is shipped |
| MCP | Future/advanced | Governance for agent tool access and prompt-injection-sensitive integrations |

## 12. Artifact Model

An Entroping-enabled repo should normally contain:

```text
qanstitution.yaml
tests/
  auth/login.hurl
  checkout/checkout_flow.hurl
envs/
  local.env
  ci.env
agents/
  builder.md
  auditor.md
  breaker.md
rules/
  security.yaml
  performance.yaml
docs/
  stories/
.entroping/
  state.db
  baselines/
reports/
```

Files under `.entroping/` and secret-bearing env files must be gitignored unless explicitly sanitized.

## 13. Success Metrics

| Metric | Target Signal |
| --- | --- |
| Time to first enforced test | New repo can initialize, generate, and run in under 10 minutes |
| Test maintainability | Refactors preserve manual edits and pass Hurl syntax validation |
| CI reliability | Deterministic exit codes and stable JUnit output |
| Governance adoption | Central rules imported by multiple services |
| Legacy rescue | Useful Hurl tests generated from traffic without existing specs |
| Defect evidence | Failures include exact repro commands and policy rule IDs |

## 14. Non-Goals for v4.1 MVP

- Replacing all unit, visual, and browser E2E testing.
- Hosted SaaS as a required dependency.
- Full native gRPC streaming test engine.
- Full browser automation.
- A custom HTTP execution engine that bypasses Hurl.
- Direct provider-specific LLM SDK integration.
- Hidden mutation of source Hurl files during `run`.
- Unbounded autonomous production traffic testing.

## 15. Product Risks and Controls

| Risk | Control |
| --- | --- |
| AI produces invalid tests | Always validate with parser-backed Hurl syntax checks and schema checks |
| AI overwrites human work | Merge-aware updates, manual regions, and diff review |
| Captured traffic contains secrets | Redaction pipeline before persistence and export |
| Central rules break many repos | Versioned imports, local dry runs, clear override/final semantics |
| CI becomes noisy | Known-failure expiry, `warn` vs `block`, and stable report formats |
| Developers bypass governance | Make local run fast, CI mandatory, and reports actionable |
| Auth and seed data are hard to infer | Prefer explicit env data, setup flows, Hurl captures, and documented seed fixtures over AI guessing |
| OpenAPI specs drift from implementation | Use traffic observation and drift reports to reveal stale specs rather than hiding failures |
| Local model setup feels heavy | Lazy-load the Brain, show Rich progress, and offer cloud fallback only through explicit configuration |

## 16. Creator Intent Reconciliation

The old v1 direction optimized for a solo developer exploring a local CLI quickly. The final v4.1 direction keeps that constraint while tightening the product around governance:

- **Development path:** `uv tool install -e .` and source-level debugging first; Nuitka, Homebrew, Docker, and PyPI later.
- **Execution path:** Hurl-native, deterministic, and CI-first.
- **AI path:** local-first with optional cloud fallback, never dependent on external Gemini or Claude CLIs.
- **Business path:** open-core CLI first, future Cloud only for centralized rules, audit logs, SSO, and team dashboards.
- **UX path:** the CLI and reports are the real product core; Studio is an optional read-only local inspector, and richer GUI/Bruno-like management is future product vision.

## 17. Final Product Definition

Entroping v4.1 is a local-first CLI system with an optional read-only Studio TUI. It uses AI to create and maintain Hurl tests, observes real traffic through mitmproxy, enforces policy from `qanstitution.yaml`, and reports deterministic runtime evidence for developers and CI.

The final product promise is simple:

**Keep AI-assisted coding fast, but make backend behavior prove itself before it ships.**
