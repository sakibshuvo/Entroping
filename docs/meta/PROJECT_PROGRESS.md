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

**Goal:** keep the published `v0.1.0-alpha` backed by local and CI release
evidence while burning down the validation queue: context drift, workflow
friction, quality gates, security review, and maintenance hotspots.

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
| [CI Hurl download retries](https://github.com/sakibshuvo/Entroping/issues/77) | Done | Live smoke Hurl archive and checksum downloads retry transient failures before checksum verification | Keep pinned binary verification strict |
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
| [Open-source license and package metadata](https://github.com/sakibshuvo/Entroping/issues/58) | Done | Apache-2.0 core license, explicit package metadata, README license status, and ADR-0009 | Keep commercial surfaces separate from the public core |
| [Eye redaction and traffic store foundation](https://github.com/sakibshuvo/Entroping/issues/61) | Done | Security-first capture models, redaction, and local SQLite state | Build before mitmproxy `watch` wiring |
| [Eye watch capture-only workflow](https://github.com/sakibshuvo/Entroping/issues/60) | Done | mitmproxy capture command after redaction/store foundation | Keep freeze/map out of scope |
| [Freeze/map implementation plan](https://github.com/sakibshuvo/Entroping/issues/59) | Done | Design traffic-to-Hurl and dependency export before implementation | Split into focused implementation issues |
| [Traffic filtering and session candidates](https://github.com/sakibshuvo/Entroping/issues/66) | Done | Pure bridge filtering/session inputs for freeze and map | Keep SQLite/proxy/CLI out of bridge |
| [Traffic-to-Hurl compiler](https://github.com/sakibshuvo/Entroping/issues/67) | Done | Compile redacted sessions into valid Hurl content | Depends on #66 |
| [Freeze CLI safe writes](https://github.com/sakibshuvo/Entroping/issues/68) | Done | Wire `freeze` to store reads, compiler output, staged writes, and parser validation | Depends on #66 and #67 |
| [Dependency graph export](https://github.com/sakibshuvo/Entroping/issues/69) | Done | Host-level graph compiler plus Mermaid/Markdown/DOT exports | Keep output escaping tested |
| [WireMock dependency mappings](https://github.com/sakibshuvo/Entroping/issues/75) | Done | `freeze --mock <service>` writes WireMock-compatible mappings from redacted dependency traffic | Keep mappings redacted |
| [PNG dependency map rendering](https://github.com/sakibshuvo/Entroping/issues/80) | Done | `map --export png` writes `reports/dependency-map.png` through local Graphviz `dot` when available | Keep renderer optional and subprocess-bounded |
| [Distribution and install polish](https://github.com/sakibshuvo/Entroping/issues/82) | Done | GitHub branch/tag install docs plus deterministic wheel/sdist metadata verification | Keep package publishing credentials out of the repo |
| [Bounded parallel Hurl execution](https://github.com/sakibshuvo/Entroping/issues/83) | Done | `run --parallel` uses QAnstitution worker limits and preserves deterministic result ordering | Keep run path LLM-free |
| [Deterministic drift report MVP](https://github.com/sakibshuvo/Entroping/issues/84) | Done | `run --drift-check --report drift` compares current run state with `.entroping/drift-baseline.json` | Add structured response drift later |
| [Read-only Studio status shell](https://github.com/sakibshuvo/Entroping/issues/85) | Done | `studio --env <name>` inspects QAnstitution, latest run, reports, and traffic-state availability when the optional Studio extra is installed | Add interactive TUI views later |
| [Architect build mode guidance](https://github.com/sakibshuvo/Entroping/issues/95) | Done | `architect build` without a mode now prints supported-mode guidance instead of scaffold placeholder text | Keep shipped commands actionable |
| [Coverage artifact hygiene](https://github.com/sakibshuvo/Entroping/issues/97) | Done | `.coverage`, `coverage.xml`, and `htmlcov/` are ignored with a regression test | Add repeatable quality audit gate |
| [Context refresh](https://github.com/sakibshuvo/Entroping/issues/92) | Done | `.context/plan.md` and this dashboard now match the post-alpha implementation surface | Keep future agent sessions grounded |
| [Quality audit gate](https://github.com/sakibshuvo/Entroping/issues/93) | Done | `scripts/audit_quality.sh` runs coverage, complexity, maintainability, and dead-code gates | Prevent silent quality drift |
| [Finish-issue workflow](https://github.com/sakibshuvo/Entroping/issues/94) | Done | `scripts/finish_issue.sh` verifies merged PRs, CI, clean issue worktrees, and project hygiene before local cleanup | Make multi-session marathons safer |
| [Story traceability bridge](https://github.com/sakibshuvo/Entroping/issues/91) | Done | Pure bridge report maps Hurl metadata to stories, owners, docs, tests, tags, and traceability findings | Expose through CLI/report adapter later |

## Later Roadmap

| Phase | Status | Notes |
| --- | --- | --- |
| OpenAPI Build | Done | Dedicated bridge compiler, local loader, and `architect build --new` |
| Runner Usability | Done | Local env-file loading for generated Hurl variables |
| Reporting Polish | Done | Dependency-free HTML run reports |
| Drift Reports | Done | MVP compares test path, Hurl status, exit code, and injected rule IDs |
| CI Proof | Done | Live demo smoke with real Hurl in GitHub Actions |
| Runner Parallelism | Done | Bounded `run --parallel` with deterministic report ordering |
| OpenAPI Depth | Done | Path/query/header/cookie parameters plus schema examples/defaults |
| Architect Minimal | Done | Prompt generation, prompt-backed build merge, pre-write Hurl validation, Architect-owned refactor, and managed-block manual refactor are available |
| Delivery Automation | Done | Deterministic repo hygiene, issue worktrees, regression gates, optional local hooks, and release-readiness checks support multi-session development |
| Alpha Release | Done | `v0.1.0-alpha` prerelease published from `abd08c0` with local release gate and CI evidence | Next release can include post-alpha PNG map rendering and package install polish |
| Eye Capture Spike | Done | Capture-only `watch` records redacted, bounded traffic through mitmproxy; freeze/map remain separate |
| Freeze and Map | Done | Basic `freeze`, WireMock dependency mocks, and Mermaid/DOT/Markdown/PNG dependency maps are in place |
| Studio | Current | Read-only status shell is available; full interactive TUI remains later |

## Update Rules

- Update this file after every meaningful feature, bug fix, or roadmap change.
- Keep this file phase-level; do not duplicate every GitHub issue.
- Link durable decisions to ADRs.
- Keep `.context/changelog.md` as the chronological handoff log.
- Keep `.context/lessons-learned.md` for durable pitfalls only.
