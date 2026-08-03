---
title: Project Progress
type: dashboard
status: active
tags:
  - progress
  - roadmap
  - obsidian
  - alpha
---

# Project Progress

This short daily dashboard points to current direction and durable release
evidence. GitHub Issues and the Project board remain the work tracker.

## Daily Dashboard

1. Use the Project board for issue state and dependencies.
2. Use [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]] for delivery.
3. Use [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] before changing governed docs.
4. Put completed history in GitHub and `.context/changelog.md`.

## Current Target

**Goal:** finish the v0.4 integration path without reopening completed
onboarding or product-depth work. The review-derived launch-hardening sweep through #957-#961
is done; the factory roadmap now hardens affordable 24x7 operation while
stable-core external proof remains independently blocked.

`entroping run` remains deterministic, Hurl-backed, QAnstitution-governed, and
provider-free:

```text
init -> doctor -> load QAnstitution -> discover Hurl -> inject gates -> run Hurl -> evidence
```

## Next Three Issues

| Order | Issue | Why next |
| --- | --- | --- |
| 1 | #303-#305 | Package-index proof for TestPyPI/PyPI publish, install, and smoke evidence. |
| 2 | #306 | Sanitized real downstream user feedback from an external project. |
| 3 | #309-#310 | Non-GitHub CI proof on real runners. |

## External Stable-Core Blockers

Stable-core readiness remains blocked by evidence that cannot be manufactured
inside this repository: package-index publish/install proof (#303-#305), real
downstream feedback (#306), and non-GitHub runner proof (#309-#310).

## Latest Evidence

| Evidence | Status | Anchor |
| --- | --- | --- |
| [Provider quota and dispatch authorization](https://github.com/sakibshuvo/Entroping/issues/1570) | Pending merge | Ledger schema v3 atomically binds cash thresholds, every quota dimension, a protected HMAC-authenticated provider-evidence envelope, immutable authority, exact terminal usage replay, and reset-aware accounting where timestamp order never proves provider coverage and only signed explicit included-authorization ids prevent settlement double counting; scheduler persistence and threshold-aware single-use launch complete the boundary. |
| [Atomic scheduler lease and concurrency authority](https://github.com/sakibshuvo/Entroping/issues/1569) | Done | Shared Git-root SQLite authority serializes lease, capacity, and assignment evidence; paid ticks hold the separate ledger writer guard through scheduler commit, while PID/start-token and epoch fencing block duplicate or unsafe takeover without dispatching providers. |
| [Paid cost reservation and settlement](https://github.com/sakibshuvo/Entroping/issues/1568) | Done | Metered direct work reserves worst-case cash before launch, settles from strict identity-bound receipts, and preserves interrupted or ambiguous holds for evidence-backed reconciliation. |
| [Unattended OpenCode isolation](https://github.com/sakibshuvo/Entroping/issues/1566) | Pending merge | Pure fixed-agent workers use private ephemeral HOME/XDG roots, typed deny-first effective-config preflight, executable/profile binding, tool-free explicit-attachment review/patch profiles, and value-free capability receipts. |
| [Live factory issue selection](https://github.com/sakibshuvo/Entroping/issues/1567) | Done | Read-only deterministic selection fails closed on stale GitHub, ownership, lease, overlap, dependency, or ambiguous issue-contract state and never authorizes paid work. |
| [Factory budget ledger](https://github.com/sakibshuvo/Entroping/issues/1565) | Done | Transactional SQLite cash authority, immutable reviewed policy, global idempotency and resource caps, serialized spend enforcement, bounded refunds, and read-only reporting. |
| [Factory control-plane protection](https://github.com/sakibshuvo/Entroping/issues/1561) | Done | Maintainer autonomy labels and one protected-surface policy gate Tier A dispatch, patch review, and PR readiness across aliases, renames, symlinks, and multi-file changes. |
| [OpenCode usage receipts](https://github.com/sakibshuvo/Entroping/issues/1560) | Done | Bounded JSONL parsing emits sanitized, deduplicated token/cost evidence or an explicit unaccounted state without persisting raw events. |
| [Provider capability registry](https://github.com/sakibshuvo/Entroping/issues/1558) | Done | One typed source governs maintainer-factory provider evidence and queue routes; unknown paid combinations fail closed without changing the product LiteLLM boundary. |
| [Factory artifact retention](https://github.com/sakibshuvo/Entroping/issues/1562) | Done | Five-class plan-first retention, bounded live metrics and logs, tracked-path protection, crash recovery, and metadata-only reporting without artifact contents. |
| Roadmap and docs inventory curation / Docs-prune candidate report | Done | Roadmap stays directional; GitHub owns work and the vault/changelog own history. |
| Tier A cheap-worker defaults / Four-gate factory readiness | Done | Cheap workers remain bounded evidence producers; Codex owns quality, security, context, cost, and merge truth. |
| [Stable-core compatibility decision](https://github.com/sakibshuvo/Entroping/issues/308) | Done | The v1 change policy is recorded without claiming stable-core proof. |
| Policy-diff CI failure mode / traffic approval manifest redaction confidence | Done | Effective-policy drift has an explicit CI gate and approval manifests stay value-free. |
| [Changed Hurl test runs](https://github.com/sakibshuvo/Entroping/issues/397) | Done | `entroping run --changed-from <ref>` selects changed committed Hurl tests. |
| [Open-source license and package metadata](https://github.com/sakibshuvo/Entroping/issues/58) | Done | Apache-2.0 public core and package metadata are explicit. |
| [Public clean-checkout onboarding smoke](https://github.com/sakibshuvo/Entroping/issues/185) | Done | `scripts/release_check.sh --require-live-demo` passed from a fresh public clone. |
| [Public launch and docs site](https://github.com/sakibshuvo/Entroping/issues/1508) | Done | The branded Astro/Starlight site deploys through GitHub Pages. |
| PyPI/TestPyPI trusted publishing workflow | Done | Protected manual publishing exists; package-index proof remains external. |
| Homebrew tap prototype | Done | The prototype waits for PyPI alpha proof. |
| Distribution path recommendation | Done | `uv tool install` first, PyPI next, Homebrew after proof. |
| Standalone binary distribution decision | Deferred | Signing and packaging automation wait for demonstrated demand. |
| Non-GitHub CI provider recipes | Done | Portable recipes exist; native templates await runner proof. |
| Organization QAnstitution import controls | Done | ADR-0011 preserves local-first provenance and final-gate authority. |
| [Read-only Studio applied-gate drilldowns](https://github.com/sakibshuvo/Entroping/issues/192) | Done | Studio remains read-only and report-backed. |

## Source Of Truth

| Question | Source |
| --- | --- |
| What work is next? | GitHub Issues, milestones, and Project board. |
| What is public direction? | `ROADMAP.md`. |
| What shipped and why? | `.context/changelog.md`, release evidence, PRs, and ADRs. |
| What is product history? | `docs/meta/VAULT_INDEX.md`, `docs/evolution/`, and curated source exports. |
| What should agents read first? | `AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, and `scripts/context_pack.sh`. |

## Update Rules

- Update this file only for current target, next queue, stable-core blockers, or durable evidence anchors.
- Do not duplicate completed issue history or use this file as the backlog; GitHub Issues remain the backlog.
- Keep roadmap edits behind the roadmap change gate in [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]].
- Keep historical context in the vault and `.context/changelog.md`, not here.
