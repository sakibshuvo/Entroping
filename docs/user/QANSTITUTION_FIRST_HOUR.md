---
title: QAnstitution First Hour
description: "Create and understand a minimal QAnstitution policy before exploring the full reference."
type: guide
status: active
tags:
  - qanstitution
  - onboarding
  - policy
---

# QAnstitution First Hour

`qanstitution.yaml` is the runtime policy Entroping injects into Hurl tests.
Start with three rules you can understand without reading the full reference:

- reject server errors.
- reject slow responses.
- warn when responses do not include a request ID header.

Those gates cover status, latency, and a basic security/operability header. They
are enough for a first demo and small enough to edit safely.

## Starter Policy

This is the same starter policy created by `entroping init --minimal` and used
by the checkout demo fixture.

<!-- first-hour-policy:start -->
```yaml
project: "entroping-project"
version: "4.1"
description: "Minimal Entroping governance policy"

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

settings:
  timeout: 30000
  parallel_workers: 2
  follow_redirects: true
  retry: 0
```
<!-- first-hour-policy:end -->

## Version Marker

Use `version: "4.1"` for new QAnstitution files. Existing files with no
`version` marker are still accepted when they match the current v4.1 policy
shape, but old or future markers fail during `entroping doctor` and config load
with migration guidance instead of being guessed.

## How To Read One Gate

```yaml
- id: "global_latency"
  description: "Every endpoint should respond within two seconds"
  condition: "true"
  gate: "duration < 2000"
  enforcement: "block"
```

Plain meaning:

- `id` is the stable name shown in reports.
- `description` is for humans reviewing the policy.
- `condition: "true"` means this applies to every Hurl response.
- `gate` is the Hurl assertion Entroping injects into one temporary execution
  copy per selected source file; all matching gates run with that source once.
- `enforcement: "block"` means a failure makes the run fail.

`enforcement: "warn"` still records the result, but it does not fail the run.
That is useful while introducing a new policy such as `X-Request-Id` headers.

`enforcement: "audit_only"` also executes its Hurl assertion and records the
result without affecting the run exit code. JSON, JUnit, and HTML reports show
the rule ID, enforcement level, result, and Hurl exit evidence for all three
levels. The starter policy above keeps its two reliability rules blocking and
its request-ID rule warning, so a missing request ID is visible without making
the first-hour run fail.

## Safe First Edits

Common edits that keep the policy understandable:

```yaml
gate: "duration < 1000"
```

Use this when local endpoints should respond within one second.

```yaml
condition: "tags contains 'smoke'"
```

Use this when a gate should apply only to tests tagged with
`# entroping: tags=smoke`.

```yaml
enforcement: "warn"
```

Use this to introduce a rule without blocking every run on day one.

## Do Not Start Here

Avoid these during the first hour:

- compound conditions with `and` or `or`.
- provider model settings.
- central imports.
- redaction tuning.
- known-failure exceptions.

Those are useful later, but the first proof should be:

```bash
entroping demo --project ./entroping-checkout-demo
```

That provider-free command prepares reviewed local fixture inputs, executes
deterministic Hurl tests, and writes `reports/run-latest.json`,
`reports/junit.xml`, and `reports/run-latest.html`. A freshly initialized
project with no reviewed Hurl test is setup state, not proof of governed
behavior.

For the full schema and advanced examples, read
[QANSTITUTION_REFERENCE.md](../technical/QANSTITUTION_REFERENCE.md).

If your editor supports YAML schemas, Entroping also publishes
[qanstitution.schema.json](../technical/qanstitution.schema.json) for
autocomplete and early feedback while editing. The editor schema helps you catch
shape mistakes quickly; `entroping doctor` still performs the authoritative
runtime validation.

For JetBrains users, add the same schema file to your YAML schema mapping
for `qanstitution.yaml`; no plugin or custom Entroping service is required for
this workflow.
