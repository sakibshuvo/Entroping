---
title: Release Evidence
type: runbook
status: active
tags:
  - release
  - evidence
  - stable-core
---

# Release Evidence

Entroping can ship alpha releases only when the evidence stays concrete. This
note explains the committed release ledger and the local validation command that
keeps stable-core claims from becoming aspirational prose.

## Canonical Ledger

The machine-readable ledger lives at:

```text
docs/meta/release-evidence.json
```

The ledger records:

- published GitHub prerelease tags and release URLs;
- the release commits those tags point at;
- last reviewed `main` CI evidence as of the ledger update;
- last reviewed Pages deployment evidence as of the ledger update;
- maintainer-controlled local smoke evidence from `scripts/downstream_smoke.py`;
- package-index status;
- explicit blockers that keep `stable_core_ready` false.

The ledger is intentionally committed because it is release-owner evidence, not
runtime state. It should not contain secrets, tokens, raw local paths, or private
user data.

Committed CI evidence does not automatically prove the current `main` HEAD. A
new merge can trigger a newer successful run immediately after this file is
updated. Treat the ledger as reviewed release evidence, then refresh it when a
release or stable-core claim depends on a newer run.

## Validation

Run this before changing launch, release, package-index, or stable-core docs:

```bash
uv run python scripts/release_evidence.py --strict
```

For machine-readable output:

```bash
uv run python scripts/release_evidence.py --format json --strict
```

For a maintainer-only freshness check against the latest successful GitHub
Actions runs on `main`, use:

```bash
uv run python scripts/release_evidence.py --check-freshness --strict
```

That optional check uses `gh run list` when GitHub CLI is installed and
authenticated. If `gh` is missing, unauthenticated, or unavailable, the command
reports `freshness.status=unavailable` and leaves normal offline ledger
validation intact. It does not mutate the ledger; stale output names the exact
recorded fields to refresh, such as `latest_main_ci.run_id`,
`latest_main_ci.commit`, `latest_pages_ci.run_id`, and
`latest_pages_ci.commit`.

Tests and offline reviews can provide equivalent latest-run evidence through a
fixture:

```bash
uv run python scripts/release_evidence.py --check-freshness --freshness-input freshness.json --strict
```

The stable-core readiness gate also validates this ledger through:

```bash
uv run python scripts/stable_core_readiness.py --strict
```

For a machine-readable blocker-to-issue map, use:

```bash
uv run python scripts/stable_core_readiness.py --format json
```

The JSON payload includes `blocker_issue_map`, which links each stable-core
blocker name to the tracked GitHub issues that can advance it. Keep those
blocker names aligned with `docs/meta/release-evidence.json` so future agents
do not invent replacement work or overclaim stable readiness.

## Stable-Core Boundary

Passing release evidence does not make Entroping stable-core ready. It only
proves that the current alpha releases, recorded CI evidence, recorded Pages
evidence, and local downstream smoke evidence are recorded in a reviewed format.

`stable_core_ready` must remain `false` until the project has:

- repeated release evidence across real release cycles;
- package-index proof from TestPyPI/PyPI Trusted Publishing;
- a stable-core compatibility decision;
- real downstream user feedback from projects outside this repository.

The downstream smoke entry is maintainer-controlled local smoke evidence. It
does not replace real downstream user feedback, package-index proof, or a user
report from a project outside this repository.

## Update Workflow

1. Create or verify the release/tag/CI evidence from GitHub.
2. Update `docs/meta/release-evidence.json`.
3. Run `uv run python scripts/release_evidence.py --strict`.
4. Run `uv run python scripts/release_evidence.py --check-freshness --strict`
   when the release or stable-core claim depends on the latest successful
   `main` CI and Pages runs.
5. Run `uv run python scripts/stable_core_readiness.py --strict`.
6. Update `docs/meta/RELEASE_CHECKLIST.md` only if the release gate changes.
7. Update `docs/meta/PROJECT_PROGRESS.md` only for phase-level status changes.

## Non-Goals

This ledger does not replace GitHub Releases, GitHub Actions, package-index
provenance, or a changelog. It is a compact local index so maintainers and
agents can see what evidence exists without calling network APIs during normal
validation.
