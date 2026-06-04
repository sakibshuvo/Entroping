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
| Drift baseline | `entroping.drift-baseline.v1` | `reports/drift-baseline.candidate.json`, `.entroping/drift-baseline.json` | Inline contract |
| Drift report | `entroping.drift-report.v1` | `reports/drift.json` | [drift-report.v1.schema.json](report-schemas/drift-report.v1.schema.json) |
| Effective policy report | `entroping.effective-policy-report.v1` | `reports/effective-policy.json` | [effective-policy-report.v1.schema.json](report-schemas/effective-policy-report.v1.schema.json) |
| Failure bundle manifest | `entroping.failure-bundle.v1` | `reports/failure-bundle/manifest.json` | Inline contract |
| Architect OpenAPI audit | `entroping.openapi-audit.v1` | `architect audit --output json` stdout | Inline contract |
| Traceability report | `entroping.traceability-report.v1` | `story_traceability_report_to_dict` | [traceability-report.v1.schema.json](report-schemas/traceability-report.v1.schema.json) |
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

The Architect OpenAPI audit JSON is written to stdout:

```bash
entroping architect audit --focus logic --output json
```

Its v1 payload includes an `operation_matrix` array with covered, uncovered,
and ambiguous OpenAPI operation rows, and a `stale_references` array for
committed Hurl `operation_id` metadata that no longer exists in the configured
spec. Paths are project-relative when the CLI discovers tests from the current
project.

The traceability CLI currently emits Markdown only:

```bash
entroping report traceability --output md
```

The v1 traceability JSON contract exists so internal consumers, future PR
annotations, and a future compatibility-reviewed JSON output can share one
stable shape.

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

## Producer Rules

- Writers must include `schema_version` on versioned JSON report payloads.
- Loaders must tolerate older payloads without `schema_version` when those files
  predate the contract.
- Report payloads must remain redacted according to the report writer and traffic
  redaction rules.
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
