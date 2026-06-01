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

This is the daily dashboard. GitHub Issues track individual tasks; this note
keeps the current direction, next queue, and release evidence easy to scan.

## Daily Dashboard

1. Open this note first in Obsidian or GitHub.
2. Use the GitHub Project board for issue status.
3. Use [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]] for
   each implementation slice.
4. Use [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] before changing roadmap,
   progress, public docs, specs, ADRs, or context files.
5. Keep this note short. Completed issue history belongs in GitHub, release
   evidence, and `.context/changelog.md`.

## Current Target

**Goal:** finish the v0.4 integration path without reopening completed
onboarding/product-depth work, while keeping stable-core readiness tied to
external evidence instead of green local tests alone.

Current issue: [#344 Centralize symlink component rejection](https://github.com/sakibshuvo/Entroping/issues/344)

Current public board: [Entroping Public Roadmap](https://github.com/users/sakibshuvo/projects/1)

Current deterministic loop:

```text
init -> doctor -> load QAnstitution -> discover Hurl tests -> inject gates -> run Hurl -> JSON/JUnit/HTML/review evidence
```

## Next Three Issues

| Order | Issue | Why next |
| --- | --- | --- |
| 1 | [#345 Optimize traffic-store retention pruning](https://github.com/sakibshuvo/Entroping/issues/345) | Keep Eye state bounded and predictable as capture sessions grow. |
| 2 | [#346 Add no-Hurl CLI smoke script](https://github.com/sakibshuvo/Entroping/issues/346) | Give downstream users a fast CLI sanity check before Hurl is installed. |
| 3 | [#347 Mention Typer shell completion in onboarding](https://github.com/sakibshuvo/Entroping/issues/347) | Improve CLI ergonomics without expanding the locked command surface. |

If one of these closes, promote the next highest-value ready issue from GitHub.
Do not expand this table beyond three rows.

## External Stable-Core Blockers

Stable-core readiness remains blocked by evidence that cannot be manufactured
entirely inside this repo.

| Blocker | Tracking | Needed proof |
| --- | --- | --- |
| Package-index proof | #303, #304, #305 | TestPyPI/PyPI publish, install, and smoke evidence from the package index. |
| Real downstream feedback | #306 | At least one sanitized external project feedback artifact. |
| Compatibility discipline | #308 | Explicit compatibility policy and repeated evidence across supported versions. |
| Non-GitHub CI proof | #309, #310 | Real GitLab/Buildkite/CircleCI runner proof before provider-native templates. |

## Latest Evidence

| Evidence | Status | Anchor |
| --- | --- | --- |
| [Open-source license and package metadata](https://github.com/sakibshuvo/Entroping/issues/58) | Done | Apache-2.0 public core and package metadata are explicit. |
| [Public clean-checkout onboarding smoke](https://github.com/sakibshuvo/Entroping/issues/185) | Done | `scripts/release_check.sh --require-live-demo` passed from a fresh public clone. |
| Public docs site decision | Done | MkDocs Material publishes existing canonical docs without duplicating the tree. |
| PyPI/TestPyPI trusted publishing workflow | Done | Manual protected workflow exists; package-index proof is still separate. |
| Homebrew tap prototype | Done | Prototype stays blocked until PyPI alpha proof exists. |
| Distribution path recommendation | Done | `uv tool install` first, PyPI next, Homebrew after PyPI, standalone later. |
| Standalone binary distribution decision | Deferred | Nuitka/PyInstaller automation waits for demand and signing runbooks. |
| Non-GitHub CI provider recipes | Done | Provider docs exist; native templates wait for real runner evidence. |
| Organization QAnstitution import controls | Done | ADR-0011 defines local-first import provenance and final-gate behavior. |
| [OpenAPI-generated Hurl pre-write validation](https://github.com/sakibshuvo/Entroping/issues/342) | Done | `architect build --new` validates every compiled Hurl file before writing and leaves no partial files on parser failure. |
| [HTML run-summary escaping](https://github.com/sakibshuvo/Entroping/issues/343) | Done | `run --report html` escapes the summary header consistently with other rendered report fields. |
| [Slim public launch docs path](https://github.com/sakibshuvo/Entroping/issues/348) | Done | README and MkDocs lead with demo/user/policy/CI paths while vault/internal memory stays preserved behind project context. |
| [Brand terminology and QAnstitution naming decision](https://github.com/sakibshuvo/Entroping/issues/349) | Done | ADR-0012 keeps `qanstitution.yaml` canonical, preserves the core philosophy, and rejects unplanned aliases or autonomous-swarm positioning. |
| [Practical watch TLS and proxy limits](https://github.com/sakibshuvo/Entroping/issues/350) | Done | User docs now set expectations for mitmproxy CA setup, corporate VPN/proxy conflicts, certificate pinning, proxy bypass, session headers, and capture authorization. |
| [OWASP API Top 10 starter policy pack](https://github.com/sakibshuvo/Entroping/issues/351) | Done | A local OWASP API Security Top 10-inspired starter pack now proves the policy-pack path without claiming endorsement, certification, or complete compliance. |
| [Shared symlink component path-safety helper](https://github.com/sakibshuvo/Entroping/issues/344) | Done | Common symlink component traversal is centralized while config imports now reject symlinked local imports and adapters keep domain-specific errors. |
| [Read-only Studio applied-gate drilldowns](https://github.com/sakibshuvo/Entroping/issues/192) | Done | Studio links latest-run report rule IDs to QAnstitution gate definitions. |
| Read-only Studio traffic session browser | Done | The read-only traffic session browser uses redacted SQLModel-backed state, target/dependency grouping, and safe redaction categories and counts. It does not start `watch` and does not expose raw URLs with query values, headers, bodies, cookies, tokens, or secrets. |

## Source Of Truth

| Question | Source |
| --- | --- |
| What work is next? | GitHub Issues, milestones, and Project board. |
| What is public direction? | `ROADMAP.md`. |
| What shipped and why? | `.context/changelog.md`, release evidence, PRs, and ADRs. |
| What is product history? | `docs/meta/VAULT_INDEX.md`, `docs/evolution/`, and curated source exports. |
| What should agents read first? | `AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, and `scripts/context_pack.sh`. |

## Update Rules

- Update this file only for current target, next queue, stable-core blockers,
  or durable evidence anchors.
- Do not duplicate the completed issue table here.
- Do not use this file as the backlog; GitHub Issues remain the backlog.
- Keep roadmap edits behind the roadmap change gate in
  [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]].
- Keep historical context in the vault and `.context/changelog.md`, not in the
  daily dashboard.
