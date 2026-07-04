---
title: Zero Config Demo Entrypoint
type: decision
status: archival
tags:
  - onboarding
  - demo
  - command-surface
---

# Zero Config Demo Entrypoint

## Archived Outcome

Archived outcome: `scripts/demo.sh` is the checkout demo entrypoint.

This is a completed v0.2 decision note retained for traceability. The durable
current guidance lives in `README.md`, `docs/user/USER_GUIDE.md`, and
`scripts/demo.sh`; do not treat this note as an active roadmap or command
proposal.

## Problem

First-time users need one obvious way to see Entroping prove runtime governance
from a clean checkout. The repository already has a hardened live smoke script,
checked-in launch assets, and a README demo, but the public entrypoint should be
easier to remember than `scripts/live_demo_smoke.sh`.

At the same time, the v4.1 CLI surface is intentionally locked. Adding a new
product command or flag before packaging and demo-asset ownership are settled
would create command drift.

## Decision

Use `scripts/demo.sh` as the public checkout demo entrypoint for v0.2.

`scripts/demo.sh` performs friendly local preflight checks for `uv` and `hurl`,
prints what it is about to prove, and then delegates to
`scripts/live_demo_smoke.sh`. The smoke script remains the deterministic
release-gate primitive for CI, release checks, and reproducible launch assets.

Do not add `entroping demo` in v0.2. Do not add `init --demo` in v0.2.

## Why

| Option | Decision | Reason |
| --- | --- | --- |
| `scripts/demo.sh` | Chosen now | Gives a one-command checkout path without changing the CLI contract. |
| `entroping demo` | Deferred | It expands the locked command surface and needs package-data rules for demo fixtures. |
| `entroping init --demo` | Deferred | It changes setup semantics and could blur the minimal-project path. |
| Keep only `scripts/live_demo_smoke.sh` | Superseded for users | It remains valuable for automation, but it reads like an internal smoke gate. |

## Guardrails

- Keep the demo local-only: no model calls, no provider credentials, and no
  external API traffic.
- Keep `scripts/live_demo_smoke.sh` reproducible and automation-friendly.
- Keep `scripts/demo.sh` a thin wrapper; do not duplicate demo logic.
- Revisit a product-level demo command only after PyPI/TestPyPI packaging and
  demo fixture distribution are settled.

## Current Commands

```bash
scripts/demo.sh
```

## Package-installed entrypoint decision

The next package-installed Aha entrypoint shape is deferred until fixture
distribution and command-surface review are complete.

When those prerequisites are accepted, the deterministic package-installed shape is:

`entroping demo --project <path>`

Current blocked prerequisites include:

- package-owned fixture distribution for demo targets
- install-time parity checks that match release smoke behavior
- a locked command-surface change through a compatibility decision
- release-only `entroping` command packaging proof

Until all prerequisites are satisfied, this issue remains a checkout-only public
path and `scripts/demo.sh` continues to be the only public Aha entrypoint in this
release cycle.

For persistent report artifacts:

```bash
ENTROPING_LIVE_DEMO_ARTIFACT_DIR="$PWD/.demo-artifacts" scripts/demo.sh
```

For release automation and launch-asset regeneration, continue to use
`scripts/live_demo_smoke.sh` directly.
