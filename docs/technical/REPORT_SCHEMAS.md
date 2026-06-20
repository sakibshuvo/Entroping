---
title: Report Schemas
type: technical-reference
status: active
tags:
  - reports
  - schema
  - compatibility
---

# Report Schemas

Entroping report artifacts are downstream integration contracts. Dashboards, PR
annotation tools, hosted surfaces, and scripts should key off
`schema_version`, not incidental field ordering or prose.

## Current Versions

| Report | Schema version | Artifact or producer | Schema file |
| --- | --- | --- | --- |
| JSON run report | `entroping.run-report.v1` | `reports/run-latest.json`, `.entroping/latest-run.json` | [run-report.v1.schema.json](report-schemas/run-report.v1.schema.json) |
| Run execution plan | `entroping.run-plan.v1` | `reports/run-plan.json` from `entroping run --dry-run --report json` | [run-plan.v1.schema.json](report-schemas/run-plan.v1.schema.json) |
| Run delta report | `entroping.run-delta-report.v1` | `entroping report delta --output json` stdout | [run-delta-report.v1.schema.json](report-schemas/run-delta-report.v1.schema.json) |
| Structured diagnostics | `entroping.diagnostics.v1` | `.entroping/latest-diagnostics.jsonl` local state for headless/report/doctor diagnostics | [diagnostics.v1.schema.json](report-schemas/diagnostics.v1.schema.json) |
| Drift baseline | `entroping.drift-baseline.v1` | `reports/drift-baseline.candidate.json`, `.entroping/drift-baseline.json` | Inline contract |
| Drift report | `entroping.drift-report.v1` | `reports/drift.json` | [drift-report.v1.schema.json](report-schemas/drift-report.v1.schema.json) |
| Capture summary | `entroping.capture-summary.v1` | `reports/capture-summary.json` from `entroping report capture-summary --output json` | [capture-summary.v1.schema.json](report-schemas/capture-summary.v1.schema.json) |
| Effective policy report | `entroping.effective-policy-report.v1` | `reports/effective-policy.json` | [effective-policy-report.v1.schema.json](report-schemas/effective-policy-report.v1.schema.json) |
| Effective policy diff | `entroping.effective-policy-diff.v1` | `entroping report policy-diff --output json` stdout | [effective-policy-diff.v1.schema.json](report-schemas/effective-policy-diff.v1.schema.json) |
| Gate coverage report | `entroping.gate-coverage-report.v1` | `reports/gate-coverage.json` | [gate-coverage-report.v1.schema.json](report-schemas/gate-coverage-report.v1.schema.json) |
| Gate injection report | `entroping.gate-injection-report.v1` | `reports/gate-injection.json` | [gate-injection-report.v1.schema.json](report-schemas/gate-injection-report.v1.schema.json) |
| Generated-test quality report | `entroping.test-quality-report.v1` | `reports/test-quality.json` | [test-quality-report.v1.schema.json](report-schemas/test-quality-report.v1.schema.json) |
| Test pyramid report | `entroping.test-pyramid-report.v1` | `reports/test-pyramid.json` | [test-pyramid-report.v1.schema.json](report-schemas/test-pyramid-report.v1.schema.json) |
| Report artifact manifest | `entroping.report-artifact-manifest.v1` | `reports/artifact-manifest.json` | [report-artifact-manifest.v1.schema.json](report-schemas/report-artifact-manifest.v1.schema.json) |
| Evidence bundle | `entroping.evidence-bundle.v1` | `reports/evidence-bundle.json` | [evidence-bundle.v1.schema.json](report-schemas/evidence-bundle.v1.schema.json) |
| Runtime evidence card | `entroping.runtime-card.v1` | `reports/runtime-card.json` from `entroping report runtime-card --output json` | [runtime-card.v1.schema.json](report-schemas/runtime-card.v1.schema.json) |
| Pilot metrics | `entroping.pilot-metrics.v1` | `reports/pilot-metrics.json` from `entroping report pilot-metrics --output json` | [pilot-metrics.v1.schema.json](report-schemas/pilot-metrics.v1.schema.json) |
| Cross-surface handoff | `entroping.handoff.v1` | `reports/handoff.json` from `entroping report handoff --output json` | [handoff.v1.schema.json](report-schemas/handoff.v1.schema.json) |
| Notification packet | `entroping.notification-packet.v1` | `reports/notification-packet.json` from `entroping report notification-packet --output json` | [notification-packet.v1.schema.json](report-schemas/notification-packet.v1.schema.json) |
| Observability packet | `entroping.observability-packet.v1` | `reports/observability-packet.json` from `entroping report observability-packet --output json` | [observability-packet.v1.schema.json](report-schemas/observability-packet.v1.schema.json) |
| Design-partner feedback | `entroping.design-partner-feedback.v1` | `reports/design-partner-feedback.json` from `entroping report design-partner-feedback` | [design-partner-feedback.v1.schema.json](report-schemas/design-partner-feedback.v1.schema.json) |
| Failure bundle manifest | `entroping.failure-bundle.v1` | `reports/failure-bundle/manifest.json` | Inline contract |
| Coverage badges | Shields endpoint schema v1 | `reports/badges/*.json` | External Shields endpoint format |
| Agent run manifest | `entroping.agent-run-manifest.v1` | `.entroping/agent-runs/*.json` | [agent-run-manifest.v1.schema.json](report-schemas/agent-run-manifest.v1.schema.json) |
| Agent review bundle | `entroping.agent-review-bundle.v1` | `reports/agent-bundle.json` | [agent-review-bundle.v1.schema.json](report-schemas/agent-review-bundle.v1.schema.json) |
| Traffic artifact approval | `entroping.traffic-artifact-approval.v1` | `reports/approvals/*.json` | [traffic-artifact-approval.v1.schema.json](report-schemas/traffic-artifact-approval.v1.schema.json) |
| Architect OpenAPI audit | `entroping.openapi-audit.v1` | `architect audit --output json` stdout | Inline contract |
| Architect OpenAPI breaking diff | `entroping.openapi-breaking-diff.v1` | Optional nested `openapi_diff` in `architect audit --changed-from <ref> --output json` | Inline contract |
| Traceability report | `entroping.traceability-report.v1` | `entroping report traceability --output json` stdout | [traceability-report.v1.schema.json](report-schemas/traceability-report.v1.schema.json) |
| SARIF report | SARIF 2.1.0 | `reports/entroping.sarif` | External SARIF schema |

The effective policy CLI can emit Markdown or JSON:

```bash
entroping report policy --output md
entroping report policy --output json
```

The JSON report is local-only policy provenance. It records config/import/gate
paths and effective assertions, not traffic values, prompts, credentials, or
provider data.
New writers include optional per-gate `group` provenance when a gate was
expanded from a local `gate_groups` reference.
The v1 schema also accepts additive source provenance: new writers emit
`sources[]` entries with source paths, SHA-256 content digests, and import
chains, plus per-gate import chains. Older v1 artifacts without these additive
fields remain readable; consumers that need byte-level audit evidence should
prefer the new fields when present.

The capture summary report is written by:

```bash
entroping report capture-summary --output json
```

Its v1 payload summarizes existing redacted traffic state by derived capture
session, method, host, dependency target, status family, and redaction category.
It never renders raw URLs, query values, headers, cookies, request bodies,
response bodies, tokens, prompts, provider data, or Hurl output.

The effective policy diff report compares two existing effective-policy JSON
artifacts:

```bash
entroping report policy-diff \
  --base reports/base-effective-policy.json \
  --current reports/effective-policy.json \
  --output json
```

Its v1 payload records added and removed imports, added and removed gates, and
changed gate fields. It does not reload QAnstitution files, fetch registries,
call providers, execute Hurl, or fail simply because valid policy evidence
changed.

The run execution plan is written only by dry-run mode:

```bash
entroping run --dry-run --tag smoke --report json
```

Its v1 payload records the selectors, selected test paths, requested report
formats, would-write executed report paths, worker/timeout/retry settings,
effective and injected gate rule IDs, and missing variable names. It does not
prove Hurl pass/fail, does not include stdout/stderr, and must not be treated as
an executed run report.

The gate coverage report is written by:

```bash
entroping report gate-coverage --output json
```

It maps each effective QAnstitution gate to committed Hurl tests discovered
under `tests/`, including matched test paths, tags, operation IDs, request
methods, and redacted request paths. It is local-only coverage evidence: it
does not execute Hurl, inject temporary assertions, call providers, or include
full URLs, query strings, headers, bodies, variables, raw traffic, prompts, or
provider data. Use it with `entroping report policy` to prove which gates exist
and with `entroping run` artifacts to prove whether those gates passed.

The gate-injection report is written by:

```bash
entroping report gate-injection --target tests/health.hurl --output json
```

It explains which effective gates would be injected into selected local Hurl
files without running Hurl or mutating source files. The report includes gate
ID, source policy path, condition, assertion, enforcement, final/group
provenance, target file, and known-failure skips. It does not include raw
traffic, environment variable values, provider data, or captured bodies.

The test-pyramid report is written by:

```bash
entroping report test-pyramid --output json
```

Its v1 payload classifies existing local report artifacts into code coverage,
runtime API proof, policy governance, drift/contract, static/security, and
generated-test quality layers. Missing, invalid, or unsafe run JSON, JUnit XML,
and gate-coverage JSON artifacts appear as high-severity runtime-governance
findings. The report does not execute tests, run Hurl, call providers, upload
artifacts, parse source Hurl, include raw artifact contents, or expose raw
traffic, prompts, stdout/stderr, environment values, or source coverage file
names.

The report artifact manifest is written by:

```bash
entroping report artifact-manifest
```

It records project-relative paths, schema versions when available, byte sizes,
and SHA-256 checksums for standard local report artifacts: JSON run report,
run-plan JSON, JUnit XML, HTML report, drift JSON, generated-test quality JSON,
agent review bundle JSON, SARIF, and review-summary Markdown.
Missing expected artifacts are listed in `missing_artifacts` rather than
failing the command. The `audit` block embeds the latest local
`entroping.report-audit-event.v1` event from
`.entroping/report-audit-chain.jsonl`, including previous-hash linkage,
artifact checksums, command metadata, verification status, and broken-chain
diagnostics. The manifest is integrity evidence for CI upload and release
review; it is not a signing, notarization, or attestation system and it never
stores artifact contents, raw traffic, provider responses, prompts,
credentials, or environment values.

The evidence bundle is written by:

```bash
entroping report evidence-bundle
entroping report evidence-bundle --output reports/evidence-bundle.md
```

It writes `reports/evidence-bundle.json` with schema
`entroping.evidence-bundle.v1` by default. A `.md` or `.markdown` output path
writes a reviewer-facing Markdown summary from the same data model without
creating a second schema. The bundle verifies design-partner upload readiness
from existing local report evidence: `reports/run-latest.json`,
`reports/effective-policy.json`, and `reports/artifact-manifest.json`. Required
JSON artifacts must validate against their full v1 contracts; a matching
`schema_version` string alone is not enough to count an artifact as valid. The
bundle records only project-relative artifact references, schema versions, byte
sizes, SHA-256 checksums, missing-artifact diagnostics,
malformed/unsupported-schema or invalid-contract diagnostics, checksum
mismatches against the artifact manifest, artifact-manifest audit-chain status,
and deterministic local remediation hints. Markdown output renders those hints
as local next commands for reviewers. Hints are not executed automatically. The
report does not embed artifact contents, raw traffic, source Hurl contents,
stdout/stderr, prompts, provider outputs, credentials, environment values, or
upload anything to a hosted service. A `not_ready` bundle is still reviewable
evidence; it means required local evidence is missing or inconsistent.

The runtime evidence card is written by:

```bash
entroping report runtime-card
entroping report runtime-card --output json
```

It writes a concise reviewer-facing card from existing local sanitized evidence:
`reports/run-latest.json` is the required deterministic runtime source, while
drift, `reports/capture-summary.json`, artifact manifest, evidence bundle,
agent bundle, and test-pyramid artifacts are summarized when present. The card
also emits a `pilot_readiness` object from `reports/evidence-bundle.json` with
the design-partner evidence status, missing-artifact count, invalid-artifact
count, checksum-mismatch count, diagnostic count, and artifact-manifest audit
status. When `reports/test-pyramid.json` is present, the additive
`test_pyramid` object summarizes runtime-governance status, layer counts, and
finding count without embedding artifact contents. Missing test-pyramid evidence
is non-blocking; incomplete test-pyramid evidence marks the card for reviewer
attention.
Missing required run evidence writes a failed card, and missing redaction
evidence marks the card for reviewer attention. Malformed or unsafe
evidence-bundle artifacts are summarized as `invalid` or `unsafe` pilot
readiness without rendering raw contents; other present malformed artifacts fail
closed before output is written.
The card records only summary counts, schema evidence, project-relative local
artifact links, failed gate IDs, and value-free findings. It does not execute
Hurl, call providers, upload results, render raw Hurl output, raw traffic,
prompts, provider responses, credentials, or environment values.

The cross-surface handoff packet is written by:

```bash
entroping report handoff
entroping report handoff --output json
entroping report handoff --fail-on-insufficient
```

It writes `reports/handoff.md` by default or `reports/handoff.json` with schema
`entroping.handoff.v1` when `--output json` is selected. The packet ties
existing local evidence together for CLI, PR, desktop, cloud, mobile, and
agent surfaces without copying report contents. It records best-effort local
Git branch/commit metadata, runtime-card summary counts, pilot-readiness and
test-pyramid statuses, canonical report artifact paths, the actual generated
handoff packet path, schema versions, SHA-256 hashes for present bounded
artifacts, and value-free next-action text. Missing source artifacts are
non-blocking unless `--fail-on-insufficient` is set and no source evidence
artifacts are present. Present malformed, unsupported, oversized, non-file,
symlinked, or secret-like artifacts are marked invalid or unsafe rather than
rendered. The command does not execute Hurl, call providers, upload results,
parse raw traffic, read traffic state, or include raw URLs, headers, bodies,
cookies, prompts, provider outputs, credentials, environment values, or source
Hurl contents.

The pilot metrics report is written by:

```bash
entroping report pilot-metrics
entroping report pilot-metrics --output json
```

It writes `reports/pilot-metrics.md` by default or
`reports/pilot-metrics.json` with schema `entroping.pilot-metrics.v1` when
`--output json` is selected. The report reads existing sanitized local
artifacts only: run report, runtime card, evidence bundle, artifact manifest,
and agent bundle. It records which metrics are locally `known`, which are
`unknown` because supporting artifacts are absent or invalid, and which are
`manual_input_required` because they depend on design-partner feedback. The
command does not execute Hurl, call providers, parse raw traffic, read private
notes, upload artifacts, or render raw report contents.

The notification packet is written by:

```bash
entroping report notification-packet
entroping report notification-packet --output json
```

It writes `reports/notification-packet.md` by default or
`reports/notification-packet.json` with schema
`entroping.notification-packet.v1` when `--output json` is selected. The packet
turns existing sanitized handoff/runtime evidence into value-free messages for
Jira, Linear, monday.com, Slack, Discord, Workato, and agent surfaces. It reads
bounded local artifacts only, prefers `reports/handoff.json` when present, and
falls back to local report metadata when the handoff packet is missing or
invalid. Message payloads contain status/severity labels, counts, local artifact
paths, and next-action text only. The command does not execute Hurl, run tests,
call providers, upload results, call issue-tracker, chat, automation, Claude, or
Codex APIs, mutate tickets or chat, read traffic state, or include raw URLs,
headers, bodies, cookies, prompts, provider outputs, credentials, environment
values, webhook URLs, ticket mutation payloads, source Hurl contents, or full
report contents.

The observability packet is written by:

```bash
entroping report observability-packet
entroping report observability-packet --output json
```

It writes `reports/observability-packet.md` by default or
`reports/observability-packet.json` with schema
`entroping.observability-packet.v1` when `--output json` is selected. The
packet turns existing local structured diagnostics and runtime-card metadata
into value-free signal summaries for OpenTelemetry, Datadog, Splunk, Grafana,
and generic observability consumers. It records source states, schema versions,
bounded SHA-256 hashes, diagnostic component/operation/code counts,
runtime-card status counts, local artifact paths, and next-action text only.
Missing diagnostics or runtime-card evidence is non-blocking and becomes
partial or insufficient packet state; malformed, oversized, non-file,
symlinked, wrong-schema, or secret-like source artifacts are marked invalid or
unsafe. The command does not execute Hurl, run tests, call providers, upload
results, call observability vendor APIs, mutate dashboards or monitors, read
traffic state, or include raw URLs, headers, bodies, cookies, prompts, provider
outputs, credentials, environment values, raw report contents, source Hurl
contents, or full diagnostic attributes.

The design-partner feedback artifact is written by:

```bash
entroping report design-partner-feedback
```

It writes `reports/design-partner-feedback.json` with schema
`entroping.design-partner-feedback.v1` by default. The command creates a
schema-valid sanitized template from local report metadata: evidence-bundle
status, runtime-card status, pilot-metrics status when present, concise manual
feedback fields, command-history placeholders, pay-signal answers, and a
follow-up GitHub issue pointer. It is product-learning evidence, not proof of
validated demand, and it must not contain customer secrets, raw traffic,
credentials, environment values, prompts, provider outputs, source Hurl
contents, or private conversation dumps. Treat free-text fields as sanitized
summaries, not notes or transcripts. Required feedback dimensions may be
`null` when there is nothing to report for that category. Template placeholders
such as `manual input required` are not customer feedback; replace them only
with concise sanitized summaries.

The drift baseline candidate and active drift baseline share
`entroping.drift-baseline.v1`. Candidates are written by `run --report drift`;
the active baseline is written only by `entroping report promote-drift-baseline`
after human review.

The run delta report is written to stdout:

```bash
entroping report delta --base reports/run-base.json --current reports/run-latest.json --output json
```

Its v1 payload compares two existing JSON run reports and records added,
resolved, changed, and unchanged failures; latency deltas; and policy-gate
deltas. It is intended for PR comments, CI logs, or downstream automation. It
does not execute Hurl, call providers, upload results, or include raw stdout,
stderr, headers, bodies, prompts, provider data, or secrets.

Coverage badges are written by:

```bash
entroping report badges
```

They use the Shields endpoint JSON shape with `schemaVersion: 1`, `label`,
`message`, and `color`. Entroping generates three local files by default:
`reports/badges/policy-gates.json`, `reports/badges/openapi-operations.json`,
and `reports/badges/story-traceability.json`. Badge generation reads existing
local report files and fails before writing if any required source report is
missing or malformed. It does not call shields.io or host a badge service.

The failure bundle manifest is written by:

```bash
entroping report failure-bundle
```

Its v1 payload records project/environment/summary, failed-test metadata, and a
list of included sanitized artifacts with bundle path, source path, schema
version, size, and SHA-256 hash. The bundle may include sanitized run JSON, bug
Markdown, failed-test Hurl metadata, JUnit, HTML, effective-policy, and
redaction-review artifacts. It must not include raw traffic state, local env
files, raw source Hurl contents, provider credentials, or unredacted secrets.

Traffic artifact approval manifests are written by artifact-generating Eye
commands:

```bash
entroping freeze --name checkout_flow --golden
entroping freeze --name refund_flow --mock payments
entroping map --export png
```

They live under `reports/approvals/` and record workflow, deterministic source
session fingerprint, source record fingerprints, generated artifact paths,
sizes, SHA-256 checksums, and counts-only redaction summaries. They do not store
raw traffic state, URLs, headers, query values, request/response bodies, local
env files, source artifact contents, provider credentials, or approval
decisions. A manifest proves generated artifacts can be reviewed against
redaction and checksum evidence; it does not mean the artifacts are safe to
commit without human review.

Agent run manifests are written by prompt-backed Architect commands:

```bash
entroping architect build --prompt "Generate checkout smoke coverage"
entroping architect build --agent breaker --prompt "Generate invalid-token tests"
entroping architect build --strategy merge --prompt "Update checkout coverage"
entroping architect refactor --target "tests/**/*.hurl" --prompt "Add auth header variables"
entroping architect audit --focus auditor --output md
```

They live under `.entroping/agent-runs/` and record value-free evidence: agent
role, model ID, persona source path plus digest, prompt intent/package hashes,
output paths, tags, validation status, provider name, latency, token usage, and
estimated cost when QAnstitution rate hints and provider usage metadata are
available. They do not store raw prompts, persona content, provider keys,
environment values, raw traffic, raw Hurl contents, provider output, or approval
decisions. A manifest proves an AI-assisted command ran through validation; it
does not mean the model approved the change or that generated tests are correct
without review.

Agent review bundles are written by:

```bash
entroping report agent-bundle --output json
```

They live at `reports/agent-bundle.json` and summarize sanitized local
`.entroping/agent-runs/*.json` evidence for configured Builder, Breaker, and
Auditor roles. The bundle records role configuration, model/persona metadata,
matching manifest paths, output paths, validation flags, usage, cost estimates,
and review findings for missing role config, missing role evidence, malformed
or secret-like manifests, invalid structured-output validation, missing Hurl
validation, and multi-role output-path conflicts. It does not call providers,
execute Hurl, read raw provider responses, store prompts, replay traffic,
include cookies, include environment values, or resolve conflicts with an LLM.

The Architect OpenAPI audit JSON is written to stdout:

```bash
entroping architect audit --focus logic --output json
```

Its v1 payload includes an `operation_matrix` array with covered, uncovered,
and ambiguous OpenAPI operation rows. Each row keeps positive/non-negative Hurl
coverage paths in `tests` and matching generated negative-path evidence in
`negative_tests`, so negative coverage does not satisfy positive operation
coverage. The payload also includes a `stale_references` array for committed
Hurl `operation_id` metadata that no longer exists in the configured spec.
Paths are project-relative when the CLI discovers tests from the current
project.

When redacted Eye traffic state is available, the same payload includes an
optional `traffic_routes` object with schema version
`entroping.traffic-openapi-audit.v1`. It compares captured route summaries to
OpenAPI operations and reports documented observed routes, undocumented
observed routes, ambiguous observed routes with candidate operation IDs, and
spec-only operations. Ambiguous observed routes do not mark candidate
operations as observed. The payload records only method, path-template, count,
failure-count, and operation identifiers; it must not include raw query
strings, headers, cookies, bodies, host userinfo, credentials, or captured
values.

When `architect audit --focus logic --changed-from <ref> --output json` is used,
the same payload includes an optional `openapi_diff` object with schema version
`entroping.openapi-breaking-diff.v1`. It reports deterministic OpenAPI
evolution findings for removed and added operations, method/path moves, response
status changes, newly required request inputs, and practical top-level JSON
response-shape changes. Findings include operation IDs, methods, paths, stable
codes/severities, evidence strings, and project-relative Hurl test paths when
committed OpenAPI metadata links exist. The diff report does not contain raw
traffic, prompts, provider output, or generated Hurl content.

The traceability CLI emits Markdown or JSON:

```bash
entroping report traceability --output md
entroping report traceability --output json > reports/traceability.json
```

The v1 traceability JSON contract includes linked Hurl test paths, local
`docs/stories/*.md` paths, optional story titles, owners, external doc URLs,
tags, and finding locations. It lets coverage badges, internal consumers,
future PR annotations, and downstream tools share one stable shape.

The SARIF report follows the external SARIF 2.1.0 contract:

```bash
entroping report sarif
```

It is generated from local JUnit, drift, and optional traceability findings. It
uses SARIF's `version` and `$schema` fields instead of an Entroping
`schema_version`.

`entroping.diagnostics.v1` is a local-first component diagnostics contract, not
a vendor telemetry payload. Events are JSONL objects with component, operation,
severity, code, summary, and sorted value-free attributes. Allowed attributes
are names, counts, durations, statuses, classifications, and relative artifact
paths. Value-bearing names such as raw traffic, prompts, provider output,
environment values, headers, bodies, cookies, and full source Hurl contents
fail closed before serialization; secret-shaped text is redacted through the
shared credential redaction primitive. Datadog, Splunk, OpenTelemetry, or other
exporters must adapt from this local contract instead of changing it.

## Compatibility Policy

Within a v1 schema:

- Adding an optional field is compatible.
- Adding a required field is breaking.
- Removing or renaming a field is breaking.
- Changing a field type is breaking.
- Changing enum meaning is breaking even if the string value stays the same.
- Reordering arrays that are documented as sorted is breaking.
- Reducing redaction or adding raw sensitive data is a security regression.

Breaking changes require a new schema version, a migration note, and an issue
that names downstream consumers affected by the change.

`entroping.run-report.v1` includes optional `known_failures` entries per test
when an active QAnstitution exception skipped an injected gate. These entries
must stay issue-linked, expiring, and value-free; they are evidence of a scoped
policy exception, not a general pass/fail override. Unmatched known-failure
entries for selected tests fail before Hurl execution and before run-report
creation; they are configuration errors, not serialized run evidence.

`entroping.run-report.v1` also includes a per-test `retry` object. It records
`retry_count`, whether the test was `unstable`, and a value-free `attempts`
array with attempt number, status, exit code, duration, and truncation flags.
The retry block must not include raw per-attempt stdout, stderr, headers,
bodies, prompts, provider data, or secrets.

`entroping.run-report.v1` includes optional per-test `timeout_ms` evidence for
the effective Hurl subprocess timeout. New writers emit it on every test row;
loaders keep treating missing or malformed values from older local reports as
`0`. Timeout failures use status `timeout`, exit code `124`, and distinct JUnit
failure type `entroping.hurl.timeout`.

Run report summary scheduling fields (`selected`, `executed`,
`not_scheduled`, and `fail_fast`) are optional evidence across JSON, JUnit, and
HTML. Writers emit them only when fail-fast stopped scheduling or selected tests
were otherwise not scheduled; normal full runs omit the suite-level scheduling
block while still recording ordinary totals.

`entroping.run-report.v1` includes optional per-test `operation_id` evidence
when the source Hurl file has safe `# entroping: operation_id=<id>` metadata.
Writers include it in JSON, JUnit properties, and HTML output; loaders ignore
missing, empty, or control-character values from older or malformed local
reports.

Generated negative tests can also expose optional `source`, `negative_category`,
and `severity` fields from safe Hurl metadata. This lets JSON, JUnit, and HTML
reports distinguish committed OpenAPI negative-path tests from spec-derived
happy-path tests without serializing arbitrary metadata or raw request values.

## Producer Rules

- Writers must include `schema_version` on versioned JSON report payloads.
- Loaders must tolerate older payloads without `schema_version` when those files
  predate the contract.
- Report payloads must remain redacted according to the report writer and traffic
  redaction rules.
- Agent run manifests must stay value-free; adding raw prompt text, provider
  output, source Hurl content, or captured traffic is a schema-breaking security
  regression.
- Markdown and HTML reports are human-readable views, not schema contracts.
- JUnit XML follows the external JUnit ecosystem contract and is not versioned by
  Entroping.
- SARIF follows the external SARIF 2.1.0 ecosystem contract and is not versioned
  by Entroping.

## Test Coverage

`tests/test_report_schema_contracts.py` freezes representative v1 payloads and
checks that each schema file declares the matching `schema_version`. Report
shape changes should update the schema, the compatibility policy notes, and the
contract tests together.
