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

**Goal:** resolve the final public-release blocker, then start the Eye capture
foundation.

GitHub Project: [Entroping Alpha](https://github.com/users/sakibshuvo/projects/1)

GitHub milestones:

- [Alpha: deterministic core](https://github.com/sakibshuvo/Entroping/milestone/1)
- [MVP: Architect build](https://github.com/sakibshuvo/Entroping/milestone/2)
- [MVP: Runner usability](https://github.com/sakibshuvo/Entroping/milestone/3)
- [MVP: Reporting polish](https://github.com/sakibshuvo/Entroping/milestone/4)
- [MVP: CI proof](https://github.com/sakibshuvo/Entroping/milestone/5)
- [MVP: Architect minimal](https://github.com/sakibshuvo/Entroping/milestone/7)
- [v0.1.0-alpha release](https://github.com/sakibshuvo/Entroping/milestone/8)
- [MVP: Eye capture](https://github.com/sakibshuvo/Entroping/milestone/9)

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
| [Architect brain foundation](https://github.com/sakibshuvo/Entroping/issues/31) | Done | Persona loading, prompt packaging, structured edit models, and lazy LiteLLM adapter are in place | Keep provider calls outside deterministic run |
| [Architect output parser and staged writer](https://github.com/sakibshuvo/Entroping/issues/33) | Done | Provider JSON is parsed into validated edits and staged as Architect-owned Hurl files | Keep overwrite and symlink protections tested |
| [Architect prompt build happy path](https://github.com/sakibshuvo/Entroping/issues/35) | Done | `architect build --prompt` loads Builder persona/model routing, calls LiteLLM through Brain, parses JSON edits, and writes Architect-owned Hurl files | Keep prompt generation reviewable |
| [Prompt-generated Hurl validation](https://github.com/sakibshuvo/Entroping/issues/37) | Done | Prompt edits are validated through `hurlfmt` before any generated file is written | Keep parser failures non-echoing |
| [Config persona template creation](https://github.com/sakibshuvo/Entroping/issues/39) | Done | `config set` creates a missing local persona Markdown template after path safety checks | Keep setup commands usable end-to-end |
| [Architect refactor happy path](https://github.com/sakibshuvo/Entroping/issues/41) | Done | `architect refactor` safely updates selected Architect-owned Hurl files through the Brain and parser validation boundaries | Keep manual-file merge behavior explicit |
| [Architecture and provider boundary tests](https://github.com/sakibshuvo/Entroping/issues/43) | Done | AST-based regression tests enforce domain/bridge import direction, run-core isolation, and LiteLLM-only provider access | Keep process guardrails executable |
| [CI duplicate workflow reduction](https://github.com/sakibshuvo/Entroping/issues/46) | Done | CI runs on pull requests and pushes to `main`, avoiding duplicate feature-branch runs | Keep marathon feedback fast |
| [Managed-block Hurl merge](https://github.com/sakibshuvo/Entroping/issues/48) | Done | Pure bridge merge replaces explicit Entroping-managed Hurl blocks while preserving manual content outside them | Reused by managed-block refactor |
| [Managed-block Architect refactor](https://github.com/sakibshuvo/Entroping/issues/50) | Done | `architect refactor` can update manual Hurl managed blocks while preserving surrounding content | Reused by prompt build merge |
| [Prompt build merge strategy](https://github.com/sakibshuvo/Entroping/issues/52) | Done | `architect build --strategy merge --prompt` updates existing Architect-owned files or managed manual blocks | Keep non-prompt merge deferred |
| [Deterministic repo hygiene and local hooks](https://github.com/sakibshuvo/Entroping/issues/54) | Done | `repo_hygiene.sh` blocks tracked local/generated state, `feature_gate.sh` runs it, and optional hook installation is scripted | Keep deterministic gates ahead of prompt-only process |
| [Alpha release readiness gate](https://github.com/sakibshuvo/Entroping/issues/56) | Done | Release checklist and deterministic `release_check.sh` gate | Tag only after required evidence passes |
| [Open-source license and package metadata](https://github.com/sakibshuvo/Entroping/issues/58) | Current | Release blocker for public alpha | Choose license with owner approval before tag |
| [Eye redaction and traffic store foundation](https://github.com/sakibshuvo/Entroping/issues/61) | Done | Security-first capture models, redaction, and local SQLite state | Build before mitmproxy `watch` wiring |
| [Eye watch capture-only workflow](https://github.com/sakibshuvo/Entroping/issues/60) | Done | mitmproxy capture command after redaction/store foundation | Keep freeze/map out of scope |
| [Freeze/map implementation plan](https://github.com/sakibshuvo/Entroping/issues/59) | Next | Design traffic-to-Hurl and dependency export before implementation | Split into focused implementation issues |

## Later Roadmap

| Phase | Status | Notes |
| --- | --- | --- |
| OpenAPI Build | Done | Dedicated bridge compiler, local loader, and `architect build --new` |
| Runner Usability | Done | Local env-file loading for generated Hurl variables |
| Reporting Polish | Done | Dependency-free HTML run reports |
| CI Proof | Done | Live demo smoke with real Hurl in GitHub Actions |
| OpenAPI Depth | Done | Path/query/header/cookie parameters plus schema examples/defaults |
| Architect Minimal | Done | Prompt generation, prompt-backed build merge, pre-write Hurl validation, Architect-owned refactor, and managed-block manual refactor are available |
| Delivery Automation | Done | Deterministic repo hygiene, issue worktrees, regression gates, optional local hooks, and release-readiness checks support multi-session development |
| Alpha Release | Current | Release checklist exists; license/package metadata is the remaining public-release blocker | Use `scripts/release_check.sh --require-live-demo` before tagging |
| Eye Capture Spike | Done | Capture-only `watch` records redacted, bounded traffic through mitmproxy; freeze/map remain separate |
| Freeze and Map | Later | Traffic-to-Hurl compiler and dependency maps |
| Studio | Deferred | Useful after deterministic core and reports are real |

## Update Rules

- Update this file after every meaningful feature, bug fix, or roadmap change.
- Keep this file phase-level; do not duplicate every GitHub issue.
- Link durable decisions to ADRs.
- Keep `.context/changelog.md` as the chronological handoff log.
- Keep `.context/lessons-learned.md` for durable pitfalls only.
