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
| External test evidence packet | `entroping.external-test-evidence.v1` | `reports/external-test-evidence.json` from `entroping report external-test-evidence --output json` | [external-test-evidence.v1.schema.json](report-schemas/external-test-evidence.v1.schema.json) |
| Report artifact manifest | `entroping.report-artifact-manifest.v1` | `reports/artifact-manifest.json` | [report-artifact-manifest.v1.schema.json](report-schemas/report-artifact-manifest.v1.schema.json) |
| Evidence bundle | `entroping.evidence-bundle.v1` | `reports/evidence-bundle.json` | [evidence-bundle.v1.schema.json](report-schemas/evidence-bundle.v1.schema.json) |
| Runtime evidence card | `entroping.runtime-card.v1` | `reports/runtime-card.json` from `entroping report runtime-card --output json` | [runtime-card.v1.schema.json](report-schemas/runtime-card.v1.schema.json) |
| Pilot metrics | `entroping.pilot-metrics.v1` | `reports/pilot-metrics.json` from `entroping report pilot-metrics --output json` | [pilot-metrics.v1.schema.json](report-schemas/pilot-metrics.v1.schema.json) |
| Cross-surface handoff | `entroping.handoff.v1` | `reports/handoff.json` from `entroping report handoff --output json` | [handoff.v1.schema.json](report-schemas/handoff.v1.schema.json) |
| Notification packet | `entroping.notification-packet.v1` | `reports/notification-packet.json` from `entroping report notification-packet --output json` | [notification-packet.v1.schema.json](report-schemas/notification-packet.v1.schema.json) |
| Team evidence readiness packet | `entroping.team-evidence-readiness.v1` | `reports/team-evidence-readiness.json` from `entroping report team-evidence-readiness --output json` | [team-evidence-readiness.v1.schema.json](report-schemas/team-evidence-readiness.v1.schema.json) |
| Team access-control plan packet | `entroping.team-access-control-plan.v1` | `reports/team-access-control-plan.json` from `entroping report team-access-control-plan --output json` | [team-access-control-plan.v1.schema.json](report-schemas/team-access-control-plan.v1.schema.json) |
| Integration readiness packet | `entroping.integration-readiness.v1` | `reports/integration-readiness.json` from `entroping report integration-readiness --output json` | [integration-readiness.v1.schema.json](report-schemas/integration-readiness.v1.schema.json) |
| Developer experience readiness packet | `entroping.devex-readiness.v1` | `reports/devex-readiness.json` from `entroping report devex-readiness --output json` | [devex-readiness.v1.schema.json](report-schemas/devex-readiness.v1.schema.json) |
| Evidence Cloud readiness packet | `entroping.evidence-cloud-readiness.v1` | `reports/evidence-cloud-readiness.json` from `entroping report evidence-cloud-readiness --output json` | [evidence-cloud-readiness.v1.schema.json](report-schemas/evidence-cloud-readiness.v1.schema.json) |
| Evidence Cloud export manifest | `entroping.evidence-cloud-export.v1` | `reports/evidence-cloud-export.json` from `entroping report evidence-cloud-export --output json` | [evidence-cloud-export.v1.schema.json](report-schemas/evidence-cloud-export.v1.schema.json) |
| Evidence Cloud workspace packet | `entroping.evidence-cloud-workspace.v1` | `reports/evidence-cloud-workspace.json` from `entroping report evidence-cloud-workspace --manifest <path> --output json` | [evidence-cloud-workspace.v1.schema.json](report-schemas/evidence-cloud-workspace.v1.schema.json) |
| Evidence Cloud dashboard packet | `entroping.evidence-cloud-dashboard.v1` | `reports/evidence-cloud-dashboard.json` from `entroping report evidence-cloud-dashboard --manifest <path> --output json` | [evidence-cloud-dashboard.v1.schema.json](report-schemas/evidence-cloud-dashboard.v1.schema.json) |
| Evidence links packet | `entroping.evidence-links.v1` | `reports/evidence-links.json` from `entroping report evidence-links --output json` | [evidence-links.v1.schema.json](report-schemas/evidence-links.v1.schema.json) |
| Evidence portal packet | `entroping.evidence-portal.v1` | `reports/evidence-portal.json` from `entroping report evidence-portal --output json` | [evidence-portal.v1.schema.json](report-schemas/evidence-portal.v1.schema.json) |
| PR evidence card packet | `entroping.pr-evidence-card.v1` | `reports/pr-evidence-card.json` from `entroping report pr-evidence-card --output json` | [pr-evidence-card.v1.schema.json](report-schemas/pr-evidence-card.v1.schema.json) |
| Evidence action-plan packet | `entroping.evidence-action-plan.v1` | `reports/evidence-action-plan.json` from `entroping report evidence-action-plan --output json` | [evidence-action-plan.v1.schema.json](report-schemas/evidence-action-plan.v1.schema.json) |
| Work item draft packet | `entroping.work-item-draft.v1` | `reports/work-item-draft.json` from `entroping report work-item-draft --output json` | [work-item-draft.v1.schema.json](report-schemas/work-item-draft.v1.schema.json) |
| Work item import bundle | `entroping.work-item-import-bundle.v1` | `reports/work-item-import-bundle.json` from `entroping report work-item-import-bundle --output json` | [work-item-import-bundle.v1.schema.json](report-schemas/work-item-import-bundle.v1.schema.json) |
| Pilot outcome packet | `entroping.pilot-outcome.v1` | `reports/pilot-outcome.json` from `entroping report pilot-outcome --output json` | [pilot-outcome.v1.schema.json](report-schemas/pilot-outcome.v1.schema.json) |
| Pilot cohort packet | `entroping.pilot-cohort.v1` | `reports/pilot-cohort.json` from `entroping report pilot-cohort --manifest <path> --output json` | [pilot-cohort.v1.schema.json](report-schemas/pilot-cohort.v1.schema.json) |
| Connector intent packet | `entroping.connector-intent.v1` | `reports/connector-intent.json` from `entroping report connector-intent --output json` | [connector-intent.v1.schema.json](report-schemas/connector-intent.v1.schema.json) |
| Observability packet | `entroping.observability-packet.v1` | `reports/observability-packet.json` from `entroping report observability-packet --output json` | [observability-packet.v1.schema.json](report-schemas/observability-packet.v1.schema.json) |
| OpenTelemetry mapping packet | `entroping.otel-mapping.v1` | `reports/otel-mapping.json` from `entroping report otel-mapping --output json` | [otel-mapping.v1.schema.json](report-schemas/otel-mapping.v1.schema.json) |
| Observability adapter readiness packet | `entroping.observability-adapter-readiness.v1` | `reports/observability-adapter-readiness.json` from `entroping report observability-adapter-readiness --output json` | [observability-adapter-readiness.v1.schema.json](report-schemas/observability-adapter-readiness.v1.schema.json) |
| API inventory packet | `entroping.api-inventory.v1` | `reports/api-inventory.json` from `entroping report api-inventory --output json` | [api-inventory.v1.schema.json](report-schemas/api-inventory.v1.schema.json) |
| Mutation readiness packet | `entroping.mutation-readiness.v1` | `reports/mutation-readiness.json` from `entroping report mutation-readiness --output json` | [mutation-readiness.v1.schema.json](report-schemas/mutation-readiness.v1.schema.json) |
| Evidence index packet | `entroping.evidence-index.v1` | `reports/evidence-index.json` from `entroping report evidence-index --output json` | [evidence-index.v1.schema.json](report-schemas/evidence-index.v1.schema.json) |
| QA brain seed packet | `entroping.qa-brain-seed.v1` | `reports/qa-brain-seed.json` from `entroping report qa-brain-seed --output json` | [qa-brain-seed.v1.schema.json](report-schemas/qa-brain-seed.v1.schema.json) |
| QA brain eval-plan packet | `entroping.qa-brain-eval-plan.v1` | `reports/qa-brain-eval-plan.json` from `entroping report qa-brain-eval-plan --output json` | [qa-brain-eval-plan.v1.schema.json](report-schemas/qa-brain-eval-plan.v1.schema.json) |
| QA brain retrieval-plan packet | `entroping.qa-brain-retrieval-plan.v1` | `reports/qa-brain-retrieval-plan.json` from `entroping report qa-brain-retrieval-plan --output json` | [qa-brain-retrieval-plan.v1.schema.json](report-schemas/qa-brain-retrieval-plan.v1.schema.json) |
| QA brain prompt-plan packet | `entroping.qa-brain-prompt-plan.v1` | `reports/qa-brain-prompt-plan.json` from `entroping report qa-brain-prompt-plan --output json` | [qa-brain-prompt-plan.v1.schema.json](report-schemas/qa-brain-prompt-plan.v1.schema.json) |
| QA brain fine-tune readiness packet | `entroping.qa-brain-fine-tune-readiness.v1` | `reports/qa-brain-fine-tune-readiness.json` from `entroping report qa-brain-fine-tune-readiness --output json` | [qa-brain-fine-tune-readiness.v1.schema.json](report-schemas/qa-brain-fine-tune-readiness.v1.schema.json) |
| QA brain model-packaging plan packet | `entroping.qa-brain-model-packaging-plan.v1` | `reports/qa-brain-model-packaging-plan.json` from `entroping report qa-brain-model-packaging-plan --output json` | [qa-brain-model-packaging-plan.v1.schema.json](report-schemas/qa-brain-model-packaging-plan.v1.schema.json) |
| QA brain routing-plan packet | `entroping.qa-brain-routing-plan.v1` | `reports/qa-brain-routing-plan.json` from `entroping report qa-brain-routing-plan --output json` | [qa-brain-routing-plan.v1.schema.json](report-schemas/qa-brain-routing-plan.v1.schema.json) |
| QA brain repair-plan packet | `entroping.qa-brain-repair-plan.v1` | `reports/qa-brain-repair-plan.json` from `entroping report qa-brain-repair-plan --output json` | [qa-brain-repair-plan.v1.schema.json](report-schemas/qa-brain-repair-plan.v1.schema.json) |
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
findings. When `reports/external-test-evidence.json` is present with schema
`entroping.external-test-evidence.v1`, the report adds an optional External
Test Evidence layer with counts-only status, layer, test, failure, error, and
skipped totals. Missing external evidence remains non-blocking and does not add
a layer or finding; invalid or unsafe external evidence appears only as
value-free layer evidence and does not become runtime-governance proof. The
report does not execute tests, run Hurl, call providers, upload artifacts, parse
source Hurl, include raw artifact contents, or expose raw traffic, prompts,
stdout/stderr, environment values, source coverage file names, or raw external
test artifact values.

The external test evidence packet is written by:

```bash
entroping report external-test-evidence
entroping report external-test-evidence --output json
```

It writes `reports/external-test-evidence.md` by default or
`reports/external-test-evidence.json` with schema
`entroping.external-test-evidence.v1` when `--output json` is selected. The
packet reads only fixed local artifacts under `reports/external-tests/`:
`unit-junit.xml`, `integration-junit.xml`, `component-junit.xml`,
`contract-junit.xml`, `e2e-junit.xml`, `coverage.xml`, `lcov.info`, and
`sarif.json`. It emits counts-only unit, integration, component, contract, and
end-to-end layer evidence plus coverage and SARIF result counts. Missing
artifacts are non-blocking; malformed, oversized, non-file, symlinked,
wrong-format, or secret-like artifacts are marked invalid or unsafe. The command
does not run tests, execute Hurl, call providers, call vendor APIs, upload
artifacts, mutate external systems, parse raw traffic state, or change
`entroping run`; it also does not render raw test names, stack traces, source
snippets, coverage file names, SARIF messages, raw stdout/stderr, prompts,
provider output, credentials, cookies, environment values, webhook URLs, or full
artifact contents.

The mutation-readiness report is written by:

```bash
entroping report mutation-readiness --output json
```

Its v1 payload summarizes bounded local evidence for future deterministic
mutation and seeded fuzz workflows. It reads committed generated Hurl tests
under `tests/generated/` or tests carrying generated metadata, plus optional
existing `reports/test-quality.json` and `reports/test-pyramid.json` artifacts
when present and schema-valid. It reports counts for generated corpus presence,
negative-path evidence, auth/security evidence, assertion strength, seed
metadata, and safe candidate categories such as status-code, schema, auth,
latency, request-shape, and response-shape. Candidate next actions flag
categories that still contain generated tests without deterministic seed
metadata, but seed values themselves are never rendered. Missing evidence is
non-blocking; malformed, oversized, path-escaped, non-file, symlinked,
wrong-schema, or secret-like artifacts are marked invalid or unsafe. The report
does not execute Hurl, mutate tests, generate tests, call providers, parse
traffic state, upload artifacts, or render raw URLs, headers, bodies, cookies,
prompts, credentials, environment values, seeds, full report contents, or
source Hurl contents.

The evidence-index packet is written by:

```bash
entroping report evidence-index
entroping report evidence-index --output json
```

It writes `reports/evidence-index.md` by default or
`reports/evidence-index.json` with schema `entroping.evidence-index.v1` when
`--output json` is selected. The packet reuses the local
`build_local_evidence_index` artifact inventory and emits stable artifact IDs,
labels, project-relative paths, source states, schema versions, and compact
value-free summaries for local report artifacts. It includes
`reports/external-test-evidence.json` with schema
`entroping.external-test-evidence.v1` and
`reports/external-test-evidence.md`; the JSON summary is limited to status,
layer, test, failure, error, and skipped totals. Missing evidence is
non-blocking; invalid, unsafe, symlinked, non-file, oversized, malformed, or
unreadable source artifacts remain represented through evidence-index states
without embedding raw source contents. The command does not execute Hurl, run
tests, call providers, upload artifacts, parse traffic state, mutate files, or
render raw report contents, raw traffic, source Hurl, prompts, credentials,
cookies, environment values, or provider outputs.

The QA brain seed packet is written by:

```bash
entroping report qa-brain-seed
entroping report qa-brain-seed --output json
```

It writes `reports/qa-brain-seed.md` by default or
`reports/qa-brain-seed.json` with schema `entroping.qa-brain-seed.v1` when
`--output json` is selected. The packet prepares deterministic local seed
metadata for future QA Brain retrieval and eval design by transforming
value-free local evidence-index rows into seed-source categories, eval-slice
readiness, and next-action rows. It is not a model, fine-tune, retrieval
engine, or provider integration. Missing evidence is non-blocking; invalid,
unsafe, symlinked, non-file, oversized, malformed, or unreadable source
artifacts remain represented through evidence-index states without embedding
contents. The command does not execute Hurl, run tests, call providers,
fine-tune models, upload artifacts, parse traffic state, mutate files, or
render raw report contents, raw traffic, source Hurl, prompts, credentials,
cookies, environment values, or provider outputs.

The QA brain eval-plan packet is written by:

```bash
entroping report qa-brain-eval-plan
entroping report qa-brain-eval-plan --output json
```

It writes `reports/qa-brain-eval-plan.md` by default or
`reports/qa-brain-eval-plan.json` with schema
`entroping.qa-brain-eval-plan.v1` when `--output json` is selected. The packet
turns deterministic QA-brain seed readiness into future eval-case metadata:
readiness, value-free source IDs and paths, input/output contracts,
acceptance signals, negative controls, and next actions. It is not a model,
fine-tune, retrieval engine, eval runner, or provider integration. Missing
evidence is non-blocking; attention cases remain represented without embedding
source contents. The command does not execute Hurl, run tests, call providers,
fine-tune models, upload artifacts, retrieve documents, parse traffic state,
run mutations or fuzzers, or render raw report contents, raw traffic, source
Hurl, prompts, credentials, cookies, environment values, or provider outputs.

The QA brain retrieval-plan packet is written by:

```bash
entroping report qa-brain-retrieval-plan
entroping report qa-brain-retrieval-plan --output json
```

It writes `reports/qa-brain-retrieval-plan.md` by default or
`reports/qa-brain-retrieval-plan.json` with schema
`entroping.qa-brain-retrieval-plan.v1` when `--output json` is selected. The
packet turns deterministic QA-brain eval-plan readiness into future retrieval
metadata: readiness, value-free source IDs and paths, retrieval categories,
allowed fields, forbidden fields, query hints, safety notes, and next actions.
It is not a model, embedding job, vector database, retrieval engine, fine-tune,
eval runner, hosted upload, or provider integration. Missing evidence is
non-blocking; attention cases remain represented without embedding source
contents. The command does not execute Hurl, run tests, call providers, create
embeddings, fine-tune models, upload artifacts, retrieve documents, parse
traffic state, run mutations or fuzzers, or render raw report contents, raw
traffic, source Hurl, prompts, credentials, cookies, environment values, or
provider outputs.

The QA brain prompt-plan packet is written by:

```bash
entroping report qa-brain-prompt-plan
entroping report qa-brain-prompt-plan --output json
```

It writes `reports/qa-brain-prompt-plan.md` by default or
`reports/qa-brain-prompt-plan.json` with schema
`entroping.qa-brain-prompt-plan.v1` when `--output json` is selected. The
packet turns deterministic QA-brain retrieval-plan readiness into future prompt
design metadata: readiness, value-free source IDs and paths, retrieval
category, prompt objective, allowed prompt inputs, forbidden prompt inputs,
expected structured output fields, deterministic acceptance signals, negative
controls, safety notes, and next actions. It is not a model, executable prompt,
embedding job, vector database, retrieval engine, fine-tune, eval runner,
hosted upload, or provider integration. Missing evidence is non-blocking;
attention cases remain represented without embedding source contents. The
command does not execute Hurl, run tests, call providers, create embeddings,
fine-tune models, upload artifacts, retrieve documents, parse traffic state,
run mutations or fuzzers, execute prompts, or render raw report contents, raw
traffic, source Hurl, prompts for execution, credentials, cookies, environment
values, or provider outputs.

The QA brain fine-tune readiness packet is written by:

```bash
entroping report qa-brain-fine-tune-readiness
entroping report qa-brain-fine-tune-readiness --output json
```

It writes `reports/qa-brain-fine-tune-readiness.md` by default or
`reports/qa-brain-fine-tune-readiness.json` with schema
`entroping.qa-brain-fine-tune-readiness.v1` when `--output json` is selected.
The packet turns deterministic QA-brain prompt-plan readiness into future
fine-tune experiment readiness metadata: readiness state, value-free source
IDs and paths, readiness stage, evidence coverage, prompt-plan completeness,
safety boundary, eval-case coverage, redaction boundary, deterministic
acceptance summary, blockers, and next actions. It is not a model, executable
prompt, embedding job, vector database, retrieval engine, dataset export,
fine-tune, training run, model package, hosted upload, or provider
integration. Missing evidence is non-blocking; attention cases remain
represented without embedding source contents. The command does not execute
Hurl, run tests, call providers, create embeddings, fine-tune models, train
models, upload artifacts, retrieve documents, export datasets, package models,
parse traffic state, run mutations or fuzzers, execute prompts, or render raw
report contents, raw traffic, source Hurl, prompts for execution, credentials,
cookies, environment values, or provider outputs.

The QA brain model-packaging plan packet is written by:

```bash
entroping report qa-brain-model-packaging-plan
entroping report qa-brain-model-packaging-plan --output json
```

It writes `reports/qa-brain-model-packaging-plan.md` by default or
`reports/qa-brain-model-packaging-plan.json` with schema
`entroping.qa-brain-model-packaging-plan.v1` when `--output json` is selected.
The packet turns deterministic QA-brain fine-tune readiness metadata into
future hosted, local, and enterprise model-packaging plan metadata: readiness
state, value-free source IDs and paths, packaging stage, OpenAI-compatible
endpoint boundary, LiteLLM routing boundary, deployment modes, artifact
boundary, access-control and audit needs, blockers, and next actions. It is
not a model server, endpoint implementation, gateway, model package, container
build, executable prompt, embedding job, vector database, retrieval engine,
dataset export, fine-tune, training run, hosted upload, or provider
integration. Missing evidence is non-blocking; attention and blocked cases
remain represented without embedding source contents. The command does not
execute Hurl, run tests, call providers, change LiteLLM configuration, start
endpoints, package models, build containers, create embeddings, fine-tune or
train models, upload artifacts, retrieve documents, export datasets, parse
traffic state, run mutations or fuzzers, execute prompts, or render raw report
contents, raw traffic, source Hurl, prompts for execution, credentials,
cookies, environment values, or provider outputs.

The QA brain routing-plan packet is written by:

```bash
entroping report qa-brain-routing-plan
entroping report qa-brain-routing-plan --output json
```

It writes `reports/qa-brain-routing-plan.md` by default or
`reports/qa-brain-routing-plan.json` with schema
`entroping.qa-brain-routing-plan.v1` when `--output json` is selected. The
packet turns deterministic QA-brain model-packaging plan metadata into future
LiteLLM/OpenAI-compatible routing-readiness metadata: readiness state,
packaging stage, value-free source IDs and paths, routing stage, LiteLLM
boundary, endpoint boundary, deployment modes, allowed future use cases,
required repair-proposal acceptance gates, forbidden pass/fail authority,
access-control and audit needs, blockers, and next actions. The acceptance
gates are value-free advisory routing metadata for parser validation,
deterministic Hurl execution, QAnstitution governance, deterministic evidence
linkage, secret redaction, and Codex/human review; a generated repair remains
unaccepted until those checks pass outside this report. It is not a provider
adapter, LiteLLM configuration writer,
endpoint implementation, gateway, SDK adapter, model package, container build,
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

The QA brain repair-plan packet is written by:

```bash
entroping report qa-brain-repair-plan
entroping report qa-brain-repair-plan --output json
```

It writes `reports/qa-brain-repair-plan.md` by default or
`reports/qa-brain-repair-plan.json` with schema
`entroping.qa-brain-repair-plan.v1` when `--output json` is selected. The
packet turns value-free local source states from generated-test quality,
mutation readiness, evidence action-plan, QA Brain routing-plan, and evidence
index artifacts into future QA Brain repair-proposal readiness rows. It carries
source states, repair intent, accepted acceptance-gate IDs from the routing-plan
packet when present, blockers, and next actions. It is not a repair generator,
prompt executor, model adapter, LiteLLM configuration writer, Hurl executor,
mutation/fuzz runner, source-Hurl or policy writer, hosted upload, ticket/chat
mutation, retrieval job, embedding job, fine-tune, training run, or provider
integration. Missing evidence is represented as missing/insufficient; invalid,
unsafe, oversized, unreadable, symlinked, or secret-like evidence is represented
as invalid/unsafe or rejected before output. The command does not render raw
report contents, raw Hurl, traffic, prompts, credentials, cookies, environment
values, provider output, URLs, headers, bodies, examples, or model responses.

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

The team evidence readiness packet is written by:

```bash
entroping report team-evidence-readiness
entroping report team-evidence-readiness --output json
```

It writes `reports/team-evidence-readiness.md` by default or
`reports/team-evidence-readiness.json` with schema
`entroping.team-evidence-readiness.v1` when `--output json` is selected. The
packet aggregates value-free states from existing evidence-bundle,
runtime-card, pilot-metrics, design-partner-feedback, handoff, and
notification-packet artifacts into team evidence cloud readiness areas, explicit
cloud-boundary controls, and next-action rows. It reads bounded local artifacts
only and records source states, schema versions, SHA-256 hashes, local artifact
paths, compact summaries, and readiness labels. Missing source artifacts are
non-blocking and become partial or insufficient packet state; malformed,
oversized, non-file, symlinked, wrong-schema, or secret-like source artifacts
are marked invalid or unsafe. The command does not execute Hurl, run tests, call
providers, upload results, create accounts, change access control, call
issue-tracker or chat APIs, read traffic state, or include raw URLs, headers,
bodies, cookies, prompts, provider outputs, credentials, environment values,
webhook URLs, ticket mutation payloads, source Hurl contents, raw report
contents, or full report contents.

The team access-control plan packet is written by:

```bash
entroping report team-access-control-plan
entroping report team-access-control-plan --output json
```

It writes `reports/team-access-control-plan.md` by default or
`reports/team-access-control-plan.json` with schema
`entroping.team-access-control-plan.v1` when `--output json` is selected. The
packet turns existing sanitized team-evidence-readiness, handoff,
notification-packet, and runtime-card artifacts into value-free role plans,
allowed and forbidden actions, boundary controls, future audit event
requirements, source states, schema versions, bounded SHA-256 hashes, compact
summaries, and next-action rows. Missing source artifacts are non-blocking and
become partial or insufficient planning state; malformed, oversized, non-file,
symlinked, wrong-schema, or secret-like source artifacts are marked invalid or
unsafe. The command does not execute Hurl, run tests, call providers, upload
results, create accounts, implement access control, enforce RBAC or SSO, call
issue-tracker or chat APIs, write back to external systems, read traffic state,
or include raw URLs, headers, bodies, cookies, prompts, provider outputs,
credentials, environment values, webhook URLs, ticket mutation payloads, source
Hurl contents, raw report contents, or full report contents.

The integration readiness packet is written by:

```bash
entroping report integration-readiness
entroping report integration-readiness --output json
```

It writes `reports/integration-readiness.md` by default or
`reports/integration-readiness.json` with schema
`entroping.integration-readiness.v1` when `--output json` is selected. The
packet turns existing sanitized team-access-control-plan, notification-packet,
handoff, observability-packet, API-inventory, and runtime-card artifacts into
value-free readiness rows for issue trackers, chat, enterprise automation,
cross-surface continuity, observability, and API governance surfaces. It records
source states, schema versions, bounded SHA-256 hashes, local artifact paths,
surface IDs, link/event requirements, forbidden actions, blockers, and
next-action rows. Missing source artifacts are non-blocking and become partial
or insufficient packet state; malformed, oversized, non-file, symlinked,
wrong-schema, or secret-like source artifacts are marked invalid or unsafe. The
command does not execute Hurl, run tests, call Jira, Linear, monday.com, Slack,
Discord, Workato, Claude, Codex, OpenAI, Datadog, Splunk, or other external
APIs, upload results, create accounts, configure SSO or RBAC, mutate tickets or
chat, execute chat commands, read provider keys, parse traffic state, sync repos
or vaults, or include raw URLs, headers, bodies, cookies, prompts, provider
outputs, credentials, environment values, webhook URLs, ticket mutation payloads,
source Hurl contents, raw report contents, or full report contents.

The developer experience readiness packet is written by:

```bash
entroping report devex-readiness
entroping report devex-readiness --output json
```

It writes `reports/devex-readiness.md` by default or
`reports/devex-readiness.json` with schema `entroping.devex-readiness.v1` when
`--output json` is selected. The packet turns existing sanitized runtime-card,
handoff, evidence-index, integration-readiness, notification-packet, and
team-access-control-plan artifacts into value-free readiness rows for CLI,
VS Code/editor, local workbench, PR runtime card, desktop, cloud, and mobile
surfaces. It records source states, schema versions, bounded SHA-256 hashes,
local artifact paths, surface IDs, link/action requirements, forbidden
actions, blockers, and next-action rows. Missing source artifacts are
non-blocking and become partial or insufficient packet state; malformed,
oversized, non-file, symlinked, wrong-schema, or secret-like source artifacts
are marked invalid or unsafe. The command does not implement a VS Code
extension, desktop app, web app, mobile app, hosted sync, deep links, PR
comments, ticket/chat writes, external API calls, Hurl execution, test
execution, provider/model calls, repo/vault/worktree synchronization, traffic
parsing, SSO/RBAC, or mutation of any external system, and it does not include
raw URLs, headers, bodies, cookies, prompts, provider outputs, credentials,
environment values, webhook URLs, ticket mutation payloads, source Hurl
contents, raw report contents, or full report contents.

The Evidence Cloud readiness packet is written by:

```bash
entroping report evidence-cloud-readiness
entroping report evidence-cloud-readiness --output json
```

It writes `reports/evidence-cloud-readiness.md` by default or
`reports/evidence-cloud-readiness.json` with schema
`entroping.evidence-cloud-readiness.v1` when `--output json` is selected. The
packet turns existing sanitized team-evidence-readiness, evidence-bundle,
runtime-card, artifact-manifest, design-partner-feedback, pilot-metrics,
integration-readiness, devex-readiness, connector-intent, and evidence-index
artifacts into value-free source states, schema versions, bounded SHA-256
hashes, readiness areas, Evidence Cloud boundary controls, upload-candidate
metadata, blockers, and next-action rows. These are fixed optional local
inputs; the command has no input-selector flags, and missing source artifacts
are non-blocking and become partial or insufficient packet state. Malformed,
oversized, non-file, symlinked, wrong-schema, unreadable, or secret-like source
artifacts are marked invalid or unsafe. The command does not call Evidence
Cloud hosted APIs, upload artifacts, sync remote state, call providers, create
accounts, configure SSO or RBAC, mutate tickets or chat, call observability
APIs, sync repos or vaults, execute Hurl, run tests, invoke models, parse
traffic state, change `entroping run`, or include raw URLs, headers, bodies,
cookies, prompts, provider outputs, credentials, environment values, webhook
URLs, ticket mutation payloads, design-partner free-form text, source Hurl
contents, raw report contents, raw traffic, or full report contents.

The Evidence Cloud export manifest is written by:

```bash
entroping report evidence-cloud-export
entroping report evidence-cloud-export --output json
```

It writes `reports/evidence-cloud-export.md` by default or
`reports/evidence-cloud-export.json` with schema
`entroping.evidence-cloud-export.v1` when `--output json` is selected. The
manifest turns existing sanitized evidence-portal, evidence-links,
evidence-cloud-readiness, team-evidence-readiness, evidence-bundle,
artifact-manifest, runtime-card, handoff, integration-readiness,
devex-readiness, connector-intent, observability-packet, and evidence-index
artifacts into value-free source states, schema versions, bounded SHA-256
hashes, local export references, boundary controls, and next-action rows.
These are fixed optional local inputs; the command has no input-selector flags,
and missing source artifacts are non-blocking and become partial or
insufficient manifest state. Malformed, oversized, non-file, symlinked,
wrong-schema, unreadable, or secret-like source artifacts are marked invalid or
unsafe. The command does not call Evidence Cloud hosted APIs, upload artifacts,
sync remote state, create accounts, configure SSO or RBAC, mutate tickets or
chat, call observability APIs, sync repos or vaults, execute Hurl, run tests,
invoke models, parse traffic state, change `entroping run`, or include raw
URLs, headers, bodies, cookies, prompts, provider outputs, credentials,
environment values, webhook URLs, ticket mutation payloads, source Hurl
contents, raw traffic, raw report contents, or full report payloads.

The Evidence Cloud workspace packet is written by:

```bash
entroping report evidence-cloud-workspace --manifest reports/evidence-cloud-export.json
entroping report evidence-cloud-workspace --manifest reports/evidence-cloud-export.json --output json
```

It writes `reports/evidence-cloud-workspace.md` by default or
`reports/evidence-cloud-workspace.json` with schema
`entroping.evidence-cloud-workspace.v1` when `--output json` is selected. The
packet reads only explicit `entroping.evidence-cloud-export.v1` JSON manifests
provided through repeatable `--manifest` options, validates their schema, and
aggregates value-free manifest identity, repository status, source/export-item
counts, boundary-control rollups, bounded SHA-256 hashes, local references, and
next-action rows. Missing, malformed, oversized, non-file, symlinked,
wrong-schema, unreadable, or secret-like manifests are marked missing, invalid,
or unsafe without rendering source contents. The command does not call Evidence
Cloud hosted APIs, upload artifacts, sync remote state, create accounts,
configure SSO or RBAC, mutate tickets or chat, call observability APIs, inspect
raw report artifacts beyond the explicit export manifest files, execute Hurl,
run tests, invoke models, parse traffic state, change `entroping run`, or
include raw URLs, headers, bodies, cookies, prompts, provider outputs,
credentials, environment values, webhook URLs, ticket mutation payloads, source
Hurl contents, raw traffic, raw report contents, or full report payloads.

The Evidence Cloud dashboard packet is written by:

```bash
entroping report evidence-cloud-dashboard --manifest reports/evidence-cloud-export.json
entroping report evidence-cloud-dashboard --manifest reports/evidence-cloud-export.json --output json
```

It writes `reports/evidence-cloud-dashboard.html` by default or
`reports/evidence-cloud-dashboard.json` with schema
`entroping.evidence-cloud-dashboard.v1` when `--output json` is selected. The
dashboard reuses Evidence Cloud workspace packet semantics over explicit export
manifests, emits value-free manifest state, repository cards,
boundary-control rollups, and next actions, and keeps HTML static and
local-only. It does not upload artifacts, call hosted APIs, execute Hurl/tests,
invoke models, parse traffic state, change `entroping run`, or render raw
artifact payloads, source Hurl, secrets, prompts, provider outputs, env values,
raw traffic, or full report contents.

The evidence links packet is written by:

```bash
entroping report evidence-links
entroping report evidence-links --output json
```

It writes `reports/evidence-links.md` by default or
`reports/evidence-links.json` with schema `entroping.evidence-links.v1` when
`--output json` is selected. The packet turns existing sanitized
evidence-index, handoff, runtime-card, evidence-bundle,
evidence-cloud-readiness, notification-packet, connector-intent,
integration-readiness, and devex-readiness artifacts into value-free source
states, schema versions, bounded SHA-256 hashes, stable local link tokens,
surface applicability, blocked targets, and next-action rows. These are fixed
optional local inputs; the command has no input-selector flags, and missing
source artifacts are non-blocking and become partial or insufficient packet
state. Malformed, oversized, non-file, symlinked, wrong-schema, unreadable, or
secret-like source artifacts are marked invalid or unsafe. The command does not
register protocol handlers, serve hosted pages, build UI surfaces, upload
artifacts, sync remote state, call external APIs, mutate tickets or chat, call
observability APIs, sync repos or vaults, execute Hurl, run tests, invoke
models, parse traffic state, change `entroping run`, or include raw URLs,
headers, bodies, cookies, prompts, provider outputs, credentials, environment
values, webhook URLs, ticket mutation payloads, source Hurl contents, raw report
contents, raw traffic, or full report contents.

The evidence portal packet is written by:

```bash
entroping report evidence-portal
entroping report evidence-portal --output json
```

It writes `reports/evidence-portal.html` by default or
`reports/evidence-portal.json` with schema `entroping.evidence-portal.v1`
when `--output json` is selected. The packet turns existing sanitized
evidence-links, evidence-index, runtime-card, handoff,
evidence-cloud-readiness, devex-readiness, connector-intent,
observability-packet, and test-pyramid artifacts into a static local dashboard
with value-free source states, schema versions, bounded SHA-256 hashes, card
readiness, target/surface counts, and next-action rows. These are fixed
optional local inputs; the command has no input-selector flags, and missing
source artifacts are non-blocking and become partial or insufficient portal
state. Malformed, oversized, non-file, symlinked, wrong-schema, unreadable, or
secret-like source artifacts are marked invalid or unsafe. The HTML output is
static and local-only, with no external assets or scripts. The command does not
host a web app, upload artifacts, sync remote state, register protocol
handlers, call external APIs, mutate tickets or chat, call observability APIs,
sync repos or vaults, execute Hurl, run tests, invoke models, parse traffic
state, change `entroping run`, or include raw URLs, headers, bodies, cookies,
prompts, provider outputs, credentials, environment values, webhook URLs,
ticket mutation payloads, source Hurl contents, raw report contents, raw
traffic, or full report contents.

The PR evidence card packet is written by:

```bash
entroping report pr-evidence-card
entroping report pr-evidence-card --output json
```

It writes `reports/pr-evidence-card.md` by default or
`reports/pr-evidence-card.json` with schema
`entroping.pr-evidence-card.v1` when `--output json` is selected. The packet
turns existing sanitized runtime-card, evidence-bundle, test-pyramid,
mutation-readiness, observability-packet, integration-readiness,
devex-readiness, connector-intent, handoff, evidence-cloud-dashboard, and
evidence-index artifacts into a local value-free PR review card with source
states, schema versions, bounded SHA-256 hashes, checklist rows, and next
actions. These are fixed optional local inputs; the command has no
input-selector flags, and missing source artifacts are non-blocking and become
partial or insufficient card state. Malformed, oversized, non-file, symlinked,
wrong-schema, unreadable, or secret-like source artifacts are marked invalid
or unsafe. The Markdown output is static and local-only. The command does not
create or update pull requests, call GitHub APIs, host a web app, upload
artifacts, sync remote state, register protocol handlers, call external APIs,
mutate tickets or chat, call observability APIs, sync repos or vaults, execute
Hurl, run tests, invoke models, parse traffic state, change `entroping run`,
or include raw URLs, headers, bodies, cookies, prompts, provider outputs,
credentials, environment values, webhook URLs, ticket mutation payloads,
source Hurl contents, raw report contents, raw traffic, or full report
contents.

The evidence action-plan packet is written by:

```bash
entroping report evidence-action-plan
entroping report evidence-action-plan --output json
```

It writes `reports/evidence-action-plan.md` by default or
`reports/evidence-action-plan.json` with schema
`entroping.evidence-action-plan.v1` when `--output json` is selected. The
packet turns existing sanitized PR evidence-card, evidence-portal,
evidence-links, Evidence Cloud dashboard, devex-readiness,
integration-readiness, connector-intent, observability-packet,
mutation-readiness, and test-pyramid artifacts into value-free prioritized
generate, repair, and review actions. Missing source artifacts become medium
generate actions; malformed, unreadable, oversized, symlinked, or secret-like
source artifacts become high repair actions. The command does not create or
update PRs, tickets, chat, or hosted dashboards, call external APIs, upload
artifacts, execute Hurl/tests, invoke models, parse traffic state, change
`entroping run`, or render raw report contents.

The work item draft packet is written by:

```bash
entroping report work-item-draft
entroping report work-item-draft --output json
```

It writes `reports/work-item-draft.md` by default or
`reports/work-item-draft.json` with schema `entroping.work-item-draft.v1` when
`--output json` is selected. The packet reads fixed optional sanitized
evidence-action-plan, connector-intent, integration-readiness, evidence-links,
and notification-packet artifacts through the evidence-index boundary, then
emits source states, schema versions, bounded SHA-256 hashes, target tracker
families, draft titles/summaries, priorities, source action IDs/counts, and
explicit forbidden actions. Missing source artifacts become generation rows;
malformed, unreadable, oversized, symlinked, or secret-like source artifacts
become high-priority repair rows. The command does not create or update tickets,
PRs, chat, automation, hosted state, labels, assignments, comments, uploads,
external APIs, Hurl/tests, model providers, traffic state, `entroping run`,
source Hurl, raw report contents, provider keys, credentials, cookies, tokens,
webhooks, or prompts.

The work item import bundle is written by:

```bash
entroping report work-item-import-bundle
entroping report work-item-import-bundle --output csv
```

It writes `reports/work-item-import-bundle.json` with schema
`entroping.work-item-import-bundle.v1` by default or
`reports/work-item-import-bundle.csv` when `--output csv` is selected. The
packet reads only the fixed optional `reports/work-item-draft.json` artifact
through the evidence-index boundary, then emits source state, schema version,
bounded SHA-256 hash, tracker family, external ID, title, body/description,
priority, labels, source item IDs, source action IDs/counts, and explicit
forbidden actions. Missing draft artifacts become generation actions;
malformed, unreadable, oversized, symlinked, or secret-like source artifacts
become high-priority repair actions. CSV output is spreadsheet-safe and
neutralizes formula-leading cells. The command does not create, import, update,
sync, assign, label, comment on, or post to tickets, PRs, chat, automation,
hosted state, dashboards, uploads, external APIs, Hurl/tests, model providers,
traffic state, `entroping run`, source Hurl, raw report contents, provider
keys, credentials, cookies, tokens, webhooks, or prompts.

The pilot outcome packet is written by:

```bash
entroping report pilot-outcome
entroping report pilot-outcome --output json
```

It writes `reports/pilot-outcome.md` by default or
`reports/pilot-outcome.json` with schema `entroping.pilot-outcome.v1` when
`--output json` is selected. The packet reads only fixed optional sanitized
local artifacts: `reports/design-partner-feedback.json`,
`reports/pilot-metrics.json`, `reports/runtime-card.json`,
`reports/evidence-cloud-dashboard.json`, and
`reports/work-item-import-bundle.json`. It emits source states, schema
versions, bounded SHA-256 hashes, value-free pilot readiness statuses, manual
input gap field names, monetization signal answers, and next actions. Missing
source artifacts become generation actions; malformed, unreadable, oversized,
symlinked, wrong-schema, or secret-like source artifacts become high-priority
repair actions. The command does not create, import, update, sync, assign,
label, comment on, or post to tickets, PRs, chat, automation, hosted state,
dashboards, uploads, external APIs, Hurl/tests, model providers, traffic state,
`entroping run`, source Hurl, raw report contents, design-partner private
notes, provider keys, credentials, cookies, tokens, webhooks, URLs, or prompts.

The pilot cohort packet is written by:

```bash
entroping report pilot-cohort --manifest reports/pilot-cohort-manifest.json
entroping report pilot-cohort --manifest reports/pilot-cohort-manifest.json --output json
```

It writes `reports/pilot-cohort.md` by default or
`reports/pilot-cohort.json` with schema `entroping.pilot-cohort.v1` when
`--output json` is selected. The manifest is local JSON with schema version
`entroping.pilot-cohort-manifest.v1` and an explicit `outcomes[]` list of
pilot outcome packet paths. The command reads only those explicit
`entroping.pilot-outcome.v1` JSON packets through the evidence-index safety
path, then emits source states, schema versions, bounded SHA-256 hashes,
cohort status counts, value-free monetization answer counts, readiness status
counts, manual-input gap counts, and next actions. Missing outcome packets
become generation actions; malformed, unreadable, oversized, symlinked,
wrong-schema, forbidden-directory, outside-project, or secret-like outcome
packets become repair actions. The command does not discover cohorts, create,
import, update, sync, assign, label, comment on, or post to tickets, PRs, chat,
automation, hosted state, dashboards, uploads, external APIs, Hurl/tests,
model providers, traffic state, `entroping run`, source Hurl, raw outcome
contents, design-partner private notes, provider keys, credentials, cookies,
tokens, webhooks, URLs, or prompts.

The connector intent packet is written by:

```bash
entroping report connector-intent
entroping report connector-intent --output json
```

It writes `reports/connector-intent.md` by default or
`reports/connector-intent.json` with schema `entroping.connector-intent.v1` when
`--output json` is selected. The packet turns existing sanitized runtime-card,
handoff, notification-packet, integration-readiness, devex-readiness,
observability-packet, and evidence-index artifacts into reviewable future
connector intents for issue trackers, chat, enterprise automation, enterprise
AI handoff, observability, and developer-experience surfaces. It records source
states, schema versions, bounded SHA-256 hashes, target systems, intent kind,
minimum payload fields, required user action, audit fields, forbidden actions,
blockers, and next-action rows. Missing source artifacts are non-blocking and
become partial or insufficient packet state; malformed, oversized, non-file,
symlinked, wrong-schema, or secret-like source artifacts are marked invalid or
unsafe. The command does not implement Jira, Linear, monday.com, Slack,
Discord, Teams, Workato, Zapier, Claude, Codex, OpenAI-compatible, Datadog,
Splunk, OpenTelemetry, Grafana, VS Code, desktop, web, cloud, or mobile
adapters; call external APIs; invoke model providers; execute Hurl; run tests;
upload artifacts; mutate tickets, chat, dashboards, monitors, workflows, repos,
vaults, or worktrees; parse raw traffic state; configure SSO/RBAC; or include
raw URLs, headers, bodies, cookies, prompts, provider outputs, credentials,
environment values, webhook URLs, ticket mutation payloads, source Hurl
contents, raw report contents, raw traffic, or full report contents.

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

The OpenTelemetry mapping packet is written by:

```bash
entroping report otel-mapping
entroping report otel-mapping --output json
```

It writes `reports/otel-mapping.md` by default or
`reports/otel-mapping.json` with schema `entroping.otel-mapping.v1` when
`--output json` is selected. The packet turns existing sanitized
observability-packet, runtime-card, test-pyramid, and external-test evidence
metadata into value-free OpenTelemetry resource, log, metric, and trace
attribute mapping rows. It records source states, schema versions, bounded
SHA-256 hashes, local artifact paths, mapping requirements, forbidden value
fields, boundary controls, and next-action rows. Missing source artifacts are
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

The observability adapter readiness packet is written by:

```bash
entroping report observability-adapter-readiness
entroping report observability-adapter-readiness --output json
```

It writes `reports/observability-adapter-readiness.md` by default or
`reports/observability-adapter-readiness.json` with schema
`entroping.observability-adapter-readiness.v1` when `--output json` is
selected. The packet reads existing sanitized observability-packet,
OpenTelemetry mapping, evidence-index, and runtime-card metadata, then emits
value-free readiness rows for future OpenTelemetry, Datadog, Splunk, Grafana,
and generic observability adapters. It records source states, schema versions,
bounded SHA-256 hashes, local artifact paths, adapter readiness statuses,
forbidden value fields, boundary controls, and next-action rows. Missing
source artifacts are non-blocking and become partial or insufficient packet
state; malformed, oversized, non-file, symlinked, wrong-schema, unreadable, or
secret-like source artifacts are marked invalid or unsafe. The command does
not export OTLP, call OpenTelemetry collectors, Datadog, Splunk, Grafana,
hosted APIs, webhooks, dashboards, monitors, tickets, chat, PRs, or Evidence
Cloud, read provider keys or local secret stores, parse raw traffic or
`.entroping/` runtime state, execute Hurl, run tests, invoke models, mutate
source Hurl, change `entroping run`, or include raw URLs, headers, bodies,
cookies, prompts, provider outputs, credentials, environment values, webhook
URLs, dashboard payloads, monitor payloads, source Hurl contents, raw traffic,
raw report contents, or full report contents.

The API inventory packet is written by:

```bash
entroping report api-inventory
entroping report api-inventory --output json
```

It writes `reports/api-inventory.md` by default or
`reports/api-inventory.json` with schema `entroping.api-inventory.v1` when
`--output json` is selected. The packet inventories local API-style signals
before protocol-specific compilers are added: configured and conventional
OpenAPI files, committed Hurl tests with protocol tags, GraphQL/WSDL/proto
schema files, AsyncAPI specs, webhook/event-contract files, and
WebSocket/realtime contract files. GraphQL SDL sources contribute counts for
root `Query`, `Mutation`, and `Subscription` fields without rendering field
names; WSDL sources contribute counts for `portType` operations without
rendering operation names, service names, addresses, or raw XML; proto sources
contribute counts for `rpc` declarations without rendering service or RPC
names. It summarizes counts for REST/OpenAPI, GraphQL, SOAP/XML, gRPC/proto,
AsyncAPI, webhook/event, WebSocket/realtime, and unknown HTTP surfaces. The
report records source states, project-relative local paths, tags,
operation/exchange counts, SHA-256 hashes, and next-action text only. Missing
sources are non-blocking; malformed, oversized, non-file, symlinked,
path-escaped, or secret-like source artifacts are marked invalid or unsafe
without rendering contents. The command does not execute Hurl, call providers,
upload results, parse traffic state, call registries, generate tests, mutate
source files, or include raw URLs, headers, bodies, cookies, prompts,
credentials, environment values, GraphQL field names, WSDL operation names,
WSDL service names, WSDL addresses, proto RPC names, proto service names, raw
XML, or full file contents.

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
