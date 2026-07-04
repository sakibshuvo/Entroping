---
title: Zero Config Demo Entrypoint
type: decision
status: active
tags:
  - onboarding
  - demo
  - command-surface
---

# Zero Config Demo Entrypoint

## Current Outcome

Current checkout outcome: `scripts/demo.sh` remains the implemented checkout
demo entrypoint.

Current package-installed decision: approve `entroping demo --project <path>` as
the next Aha command shape. Implementation is tracked by #1385 and must preserve
the local-only deterministic demo boundary.

## Problem

First-time users need one obvious way to see Entroping prove runtime governance
from a clean checkout. The repository already has a hardened live smoke script,
checked-in launch assets, and a README demo, but the public entrypoint should be
easier to remember than `scripts/live_demo_smoke.sh`.

At the same time, the v4.1 CLI surface is intentionally locked. A package-level
demo command needs an explicit compatibility decision before implementation.

## Decision

Use `scripts/demo.sh` as the public checkout demo entrypoint for v0.2. Approve
`entroping demo --project <path>` as the package-installed Aha entrypoint shape
for #1385.

`scripts/demo.sh` performs friendly local preflight checks for `uv` and `hurl`,
prints what it is about to prove, and then delegates to
`scripts/live_demo_smoke.sh`. The smoke script remains the deterministic
release-gate primitive for CI, release checks, and reproducible launch assets.

Do not add `init --demo` in v0.2.

## Why

| Option | Decision | Reason |
| --- | --- | --- |
| `scripts/demo.sh` | Chosen now | Gives a one-command checkout path without changing the CLI contract. |
| `entroping demo --project <path>` | Approved next | Gives package-installed users the same local deterministic Aha path once #1385 implements the package-owned fixture flow. |
| `entroping init --demo` | Deferred | It changes setup semantics and could blur the minimal-project path. |
| Keep only `scripts/live_demo_smoke.sh` | Superseded for users | It remains valuable for automation, but it reads like an internal smoke gate. |

## Guardrails

- Keep the demo local-only: no model calls, no provider credentials, and no
  external API traffic.
- Keep `scripts/live_demo_smoke.sh` reproducible and automation-friendly.
- Keep `scripts/demo.sh` a thin wrapper; do not duplicate demo logic.
- Implement the product-level demo command only through #1385 or a successor
  compatibility issue.

## Current Commands

```bash
scripts/demo.sh
```

## Package-installed entrypoint decision

The package-installed Aha entrypoint shape is approved:

`entroping demo --project <path>`

Approve `entroping demo --project <path>` as a local-only command that prepares
or copies the reviewed checkout demo fixture into the selected project, runs the
same deterministic Hurl-backed proof as the checkout demo, and does not call
model providers or external APIs.

Until #1385 lands, `scripts/demo.sh` continues to be the only implemented public
Aha entrypoint. This decision approves the command surface; it does not claim
package-index proof, stable-core readiness, or downstream adoption.

For persistent report artifacts:

```bash
ENTROPING_LIVE_DEMO_ARTIFACT_DIR="$PWD/.demo-artifacts" scripts/demo.sh
```

For release automation and launch-asset regeneration, continue to use
`scripts/live_demo_smoke.sh` directly.
