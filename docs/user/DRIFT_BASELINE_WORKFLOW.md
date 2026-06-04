---
title: Drift Baseline Workflow
type: guide
status: active
tags:
  - entroping
  - drift
  - baseline
---

# Drift Baseline Workflow

Drift baselines are reviewed local evidence, not automatic approval of whatever
the API did most recently.

The active baseline lives at `.entroping/drift-baseline.json`. Entroping does not
write that file during `run`. Instead, `--report drift` writes a sanitized
candidate at `reports/drift-baseline.candidate.json` whenever the Hurl suite
itself passed. Review the candidate, compare it with the current baseline, then
promote it only when the behavior is accepted.

## Create The First Baseline

Run the suite in the environment you want to anchor:

```bash
entroping run --env staging --report drift
```

Review the candidate:

```bash
python -m json.tool reports/drift-baseline.candidate.json
```

Promote it after review:

```bash
entroping report promote-drift-baseline
```

The first run also writes `reports/drift.json` with a `missing_baseline` finding.
That finding is a prompt to review, not proof that current behavior is correct.

## Update An Existing Baseline

Run drift against the current baseline:

```bash
entroping run --env staging --drift-check --report drift
```

Review the drift findings:

```bash
python -m json.tool reports/drift.json
```

Compare the accepted candidate against the active baseline:

```bash
git diff --no-index -- .entroping/drift-baseline.json reports/drift-baseline.candidate.json
```

If the behavior change is intentional, promote the candidate:

```bash
entroping report promote-drift-baseline
```

If the behavior change is not intentional, fix the API or Hurl test and rerun
the suite instead of updating the baseline.

## What The Candidate Stores

The candidate is intentionally value-free. It includes only:

- Project and environment.
- Test path, status, exit code, duration, and injected QAnstitution rule IDs.
- Optional response status code.
- Selected stable response headers such as `content-type`, `cache-control`, and
  `vary`.
- JSON body shape paths, not response values.

It does not include stdout, stderr, execution paths, cookies, authorization
headers, request IDs, volatile headers, full response bodies, or raw secrets.

Promotion validates the candidate schema before writing the active baseline. It
rejects missing, malformed, stale, future-version, symlinked, or outside-project
candidate paths and writes the active baseline atomically.

## Git Policy

`.entroping/` is local runtime state by default. Keep baselines local unless your
team deliberately decides that shared drift baselines belong in version control.
If you do commit baselines later, add a separate policy issue first so the review
and redaction expectations are explicit.
