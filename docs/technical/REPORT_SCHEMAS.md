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
| Drift report | `entroping.drift-report.v1` | `reports/drift.json` | [drift-report.v1.schema.json](report-schemas/drift-report.v1.schema.json) |
| Effective policy report | `entroping.effective-policy-report.v1` | `reports/effective-policy.json` | [effective-policy-report.v1.schema.json](report-schemas/effective-policy-report.v1.schema.json) |
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
