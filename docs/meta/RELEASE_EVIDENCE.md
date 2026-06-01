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

The stable-core readiness gate also validates this ledger through:

```bash
uv run python scripts/stable_core_readiness.py --strict
```

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
4. Run `uv run python scripts/stable_core_readiness.py --strict`.
5. Update `docs/meta/RELEASE_CHECKLIST.md` only if the release gate changes.
6. Update `docs/meta/PROJECT_PROGRESS.md` only for phase-level status changes.

## Non-Goals

This ledger does not replace GitHub Releases, GitHub Actions, package-index
provenance, or a changelog. It is a compact local index so maintainers and
agents can see what evidence exists without calling network APIs during normal
validation.
