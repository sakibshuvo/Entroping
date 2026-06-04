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
| Run delta report | `entroping.run-delta-report.v1` | `entroping report delta --output json` stdout | [run-delta-report.v1.schema.json](report-schemas/run-delta-report.v1.schema.json) |
| Drift baseline | `entroping.drift-baseline.v1` | `reports/drift-baseline.candidate.json`, `.entroping/drift-baseline.json` | Inline contract |
| Drift report | `entroping.drift-report.v1` | `reports/drift.json` | [drift-report.v1.schema.json](report-schemas/drift-report.v1.schema.json) |
| Effective policy report | `entroping.effective-policy-report.v1` | `reports/effective-policy.json` | [effective-policy-report.v1.schema.json](report-schemas/effective-policy-report.v1.schema.json) |
| Failure bundle manifest | `entroping.failure-bundle.v1` | `reports/failure-bundle/manifest.json` | Inline contract |
| Coverage badges | Shields endpoint schema v1 | `reports/badges/*.json` | External Shields endpoint format |
| Agent run manifest | `entroping.agent-run-manifest.v1` | `.entroping/agent-runs/*.json` | [agent-run-manifest.v1.schema.json](report-schemas/agent-run-manifest.v1.schema.json) |
| Architect OpenAPI audit | `entroping.openapi-audit.v1` | `architect audit --output json` stdout | Inline contract |
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
output paths, tags, validation status, latency, and token usage. They do not
store raw prompts, persona content, provider keys, environment values, raw
traffic, raw Hurl contents, provider output, or approval decisions. A manifest
proves an AI-assisted command ran through validation; it does not mean the model
approved the change or that generated tests are correct without review.

The Architect OpenAPI audit JSON is written to stdout:

```bash
entroping architect audit --focus logic --output json
```

Its v1 payload includes an `operation_matrix` array with covered, uncovered,
and ambiguous OpenAPI operation rows, and a `stale_references` array for
committed Hurl `operation_id` metadata that no longer exists in the configured
spec. Paths are project-relative when the CLI discovers tests from the current
project.

When redacted Eye traffic state is available, the same payload includes an
optional `traffic_routes` object with schema version
`entroping.traffic-openapi-audit.v1`. It compares captured route summaries to
OpenAPI operations and reports documented observed routes, undocumented
observed routes, and spec-only operations. It records only method,
path-template, count, failure-count, and operation identifiers; it must not
include raw query strings, headers, cookies, bodies, host userinfo, credentials,
or captured values.

The traceability CLI emits Markdown or JSON:

```bash
entroping report traceability --output md
entroping report traceability --output json > reports/traceability.json
```

The v1 traceability JSON contract lets coverage badges, internal consumers,
future PR annotations, and downstream tools share one stable shape.

The SARIF report follows the external SARIF 2.1.0 contract:

```bash
entroping report sarif
```

It is generated from local JUnit, drift, and optional traceability findings. It
uses SARIF's `version` and `$schema` fields instead of an Entroping
`schema_version`.

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
policy exception, not a general pass/fail override.

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
