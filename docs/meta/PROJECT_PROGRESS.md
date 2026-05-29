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

This is the simple human dashboard. GitHub Issues track individual work items; this note tracks phase-level progress and the current marathon target.

## Daily Use

1. Open this note first in Obsidian.
2. Pick the one **Current** issue.
3. Run the feature through [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]].
4. Update this note only when phase-level status changes.

Do not duplicate every issue here. The detailed queue lives in GitHub.

## Status Key

- **Done:** committed, pushed, and CI green.
- **Current:** active implementation target.
- **Next:** queued after the current target.
- **Later:** planned after deterministic alpha.
- **Deferred:** intentionally out of scope for alpha.

## Current Target

**Goal:** start the first LLM-backed Architect slice after deterministic audit and
non-secret agent routing.

GitHub Project: [Entroping Alpha](https://github.com/users/sakibshuvo/projects/1)

GitHub milestones:

- [Alpha: deterministic core](https://github.com/sakibshuvo/Entroping/milestone/1)
- [MVP: Architect build](https://github.com/sakibshuvo/Entroping/milestone/2)
- [MVP: Runner usability](https://github.com/sakibshuvo/Entroping/milestone/3)
- [MVP: Reporting polish](https://github.com/sakibshuvo/Entroping/milestone/4)
- [MVP: CI proof](https://github.com/sakibshuvo/Entroping/milestone/5)
- [MVP: Architect minimal](https://github.com/sakibshuvo/Entroping/milestone/7)

```text
init -> doctor -> load QAnstitution -> discover Hurl tests -> inject gates -> run Hurl -> JSON/JUnit report
```

## Milestone Progress

| Slice | Status | Evidence | Next proof |
| --- | --- | --- | --- |
| Repo and context scaffold | Done | CI, docs, Obsidian vault, `scripts/feature_gate.sh` | Keep context docs current |
| Issue tracking and progress system | Done | Issue templates, regression script, progress dashboard, CI regression command, issue session launcher | Keep the queue and dashboard current |
| [`init`, `doctor`, and QAnstitution loading](https://github.com/sakibshuvo/Entroping/issues/1) | Done | Minimal init, doctor config validation, local import loading, and tests | Keep docs and examples aligned |
| [Hurl discovery and metadata](https://github.com/sakibshuvo/Entroping/issues/2) | Done | Metadata parsing, recursive discovery, generated-state ignores, tag-filter validation, and tests | Feed discovery into gate injection |
| [Gate matching and injection](https://github.com/sakibshuvo/Entroping/issues/3) | Done | Policy compiler, request metadata parsing, temporary execution copies, source-immutability regression tests | Feed injected copies into Hurl subprocess runner |
| [Hurl subprocess runner](https://github.com/sakibshuvo/Entroping/issues/4) | Done | Argument-array subprocess runner, timeout handling, bounded/redacted output, temp cleanup, CLI run integration, and tests | Feed run results into reports |
| [JSON/JUnit reports](https://github.com/sakibshuvo/Entroping/issues/5) | Done | Redacted JSON, JUnit XML, latest-run state, `report bug`, and tests | Wire reports into the demo quickstart |
| [README demo quickstart](https://github.com/sakibshuvo/Entroping/issues/6) | Done | Local checkout demo server, literal Hurl fixture, README quickstart, fixture docs, and tests | Keep quickstart aligned with runner/report changes |
| [OpenAPI Architect build](https://github.com/sakibshuvo/Entroping/issues/11) | Done | Deterministic local `sources.spec` to `tests/generated/*.hurl` generation | Use `--env` to run generated variable-based tests |
| [Environment file loading](https://github.com/sakibshuvo/Entroping/issues/13) | Done | `run --env` loads `envs/<name>.env` and passes variables to Hurl | Keep variable passing hardened |
| [Hurl variable argv hardening](https://github.com/sakibshuvo/Entroping/issues/15) | Done | Hurl variables are passed through a temp `--variables-file` instead of secret-bearing argv | Keep env handling redacted |
| [HTML run reports](https://github.com/sakibshuvo/Entroping/issues/17) | Done | `run --report html` writes escaped human-readable reports | Use in demo and CI proof |
| [Live Hurl demo smoke in CI](https://github.com/sakibshuvo/Entroping/issues/19) | Done | Live smoke script and GitHub Actions job added | Keep demo path green |
| [OpenAPI parameters and schema examples](https://github.com/sakibshuvo/Entroping/issues/23) | Done | Path/query/header/cookie parameters and request examples/defaults are supported | Keep generated demo path green |
| [Deterministic Architect audit coverage](https://github.com/sakibshuvo/Entroping/issues/25) | Done | OpenAPI coverage audit for committed executable Hurl tests is supported | Keep audit output machine-readable |
| [Non-secret agent config commands](https://github.com/sakibshuvo/Entroping/issues/29) | Done | `config list` / `config set` manage non-secret agent model routing | Keep credentials out of config |

## Later Roadmap

| Phase | Status | Notes |
| --- | --- | --- |
| OpenAPI Build | Done | Dedicated bridge compiler, local loader, and `architect build --new` |
| Runner Usability | Done | Local env-file loading for generated Hurl variables |
| Reporting Polish | Done | Dependency-free HTML run reports |
| CI Proof | Done | Live demo smoke with real Hurl in GitHub Actions |
| OpenAPI Depth | Done | Path/query/header/cookie parameters plus schema examples/defaults |
| Architect Minimal | Current | Next slice is LiteLLM wrapper, persona loading, and structured-output validation |
| Eye Capture Spike | Later | mitmproxy capture-only with redaction before persistence |
| Freeze and Map | Later | Traffic-to-Hurl compiler and dependency maps |
| Studio | Deferred | Useful after deterministic core and reports are real |

## Update Rules

- Update this file after every meaningful feature, bug fix, or roadmap change.
- Keep this file phase-level; do not duplicate every GitHub issue.
- Link durable decisions to ADRs.
- Keep `.context/changelog.md` as the chronological handoff log.
- Keep `.context/lessons-learned.md` for durable pitfalls only.
