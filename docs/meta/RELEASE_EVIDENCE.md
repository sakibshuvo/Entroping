---
title: Release Evidence
description: "Interpret the committed release ledger and validate stable-core claims against concrete evidence."
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
- local alpha release-candidate rehearsal evidence from the release gate;
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

`scripts/release_check.sh` runs this freshness check by default for the release
gate. The check uses `gh run list` when GitHub CLI is installed and
authenticated. If `gh` is missing, unauthenticated, or unavailable, the command
reports `freshness.status=unavailable` and leaves normal offline ledger
validation intact. It does not mutate the ledger; stale output names the exact
recorded fields to refresh, such as `latest_main_ci.run_id`,
`latest_main_ci.commit`, `latest_pages_ci.run_id`, and
`latest_pages_ci.commit`.

For a deliberately offline/local diagnostic, `scripts/release_check.sh
--skip-release-evidence-freshness` validates the committed ledger without the
GitHub freshness comparison. Do not use that form for release-candidate signoff,
package-index proof, or stable-core claims.

If the latest successful `main` runs are newer only because the
release-evidence refresh commit itself merged, the freshness check treats that
as current only when Git proves the diff is limited to the ledger, its pinned
test, and `.context/changelog.md`. Any unrelated file change remains stale.

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

Readiness JSON distinguishes `structural` checks from `recorded_execution`.
Recorded execution entries expose their reviewed commit and timestamp plus a
`freshness` state; `not_checked` means the committed ledger has not been
compared with the latest successful `main` runs in that invocation.

## Stable-Core Boundary

Passing release evidence does not make Entroping stable-core ready. It only
proves that the current alpha releases, release-candidate rehearsals, recorded
CI evidence, recorded Pages evidence, and local downstream smoke evidence are
recorded in a reviewed format.

`stable_core_ready` must remain `false` until the project has:

| Blocker ID | Required proof |
| --- | --- |
| `package_index_proof` | Package-index proof from TestPyPI/PyPI Trusted Publishing. |
| `real_downstream_feedback` | Real downstream user feedback from projects outside this repository. |

The downstream smoke entry is maintainer-controlled local smoke evidence. It
does not replace real downstream user feedback, package-index proof, or a user
report from a project outside this repository.

When real users or external repositories try Entroping, collect sanitized
evidence with [DOWNSTREAM_FEEDBACK_KIT.md](DOWNSTREAM_FEEDBACK_KIT.md) before
using it to reduce the real downstream user feedback blocker.

## Update Workflow

1. Create or verify the release/tag/CI evidence from GitHub.
2. Update `docs/meta/release-evidence.json`.
3. Run `uv run python scripts/release_evidence.py --strict`.
4. Run `uv run python scripts/release_evidence.py --check-freshness --strict`
   when the release or stable-core claim depends on the latest successful
   `main` CI and Pages runs. A self-refresh-only merge is accepted; unrelated
   newer changes still require a ledger refresh before claims depend on them.
5. Run `uv run python scripts/stable_core_readiness.py --strict`.
6. Update `docs/meta/RELEASE_CHECKLIST.md` only if the release gate changes.
7. Update `docs/meta/PROJECT_PROGRESS.md` only for phase-level status changes.

## Non-Goals

This ledger does not replace GitHub Releases, GitHub Actions, package-index
provenance, or a changelog. It is a compact local index so maintainers and
agents can see what evidence exists without calling network APIs during normal
validation.
