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

## Status Key

- **Done:** committed, pushed, and CI green.
- **Current:** active implementation target.
- **Next:** queued after the current target.
- **Later:** planned after deterministic alpha.
- **Deferred:** intentionally out of scope for alpha.

## Current Target

**Goal:** credible open-source alpha of the deterministic governance loop.

GitHub milestone: [Alpha: deterministic core](https://github.com/sakibshuvo/Entroping/milestone/1)

```text
init -> doctor -> load QAnstitution -> discover Hurl tests -> inject gates -> run Hurl -> JSON/JUnit report
```

## Alpha Progress

| Slice | Status | Evidence | Next proof |
| --- | --- | --- | --- |
| Repo and context scaffold | Done | CI, docs, Obsidian vault, `scripts/feature_gate.sh` | Keep context docs current |
| Issue tracking and progress system | Done | Issue templates, regression script, progress dashboard, CI regression command | Keep the queue and dashboard current |
| [`init`, `doctor`, and QAnstitution loading](https://github.com/sakibshuvo/Entroping/issues/1) | Current | CLI scaffold exists | Creates minimal config and validates local tools |
| [Hurl discovery and metadata](https://github.com/sakibshuvo/Entroping/issues/2) | Next | Discovery adapter scaffold exists | Finds `.hurl` files and parses `# entroping:` metadata |
| [Gate matching and injection](https://github.com/sakibshuvo/Entroping/issues/3) | Next | Policy compiler boundary exists | Source `.hurl` files are never mutated |
| [Hurl subprocess runner](https://github.com/sakibshuvo/Entroping/issues/4) | Next | Runner scaffold exists | Timeouts, bounded output, redaction, non-zero failures |
| [JSON/JUnit reports](https://github.com/sakibshuvo/Entroping/issues/5) | Next | Report command scaffold exists | CI can consume JUnit and humans can inspect JSON |
| [README demo quickstart](https://github.com/sakibshuvo/Entroping/issues/6) | Next | Checkout fixture exists | A new user can run the alpha loop locally |

## Later Roadmap

| Phase | Status | Notes |
| --- | --- | --- |
| Architect Minimal | Later | LiteLLM, structured outputs, generated Hurl review flow |
| OpenAPI Build | Later | Dedicated bridge compiler and merge strategy |
| Eye Capture Spike | Later | mitmproxy capture-only with redaction before persistence |
| Freeze and Map | Later | Traffic-to-Hurl compiler and dependency maps |
| Studio | Deferred | Useful after deterministic core and reports are real |

## Update Rules

- Update this file after every meaningful feature, bug fix, or roadmap change.
- Keep this file phase-level; do not duplicate every GitHub issue.
- Link durable decisions to ADRs.
- Keep `.context/changelog.md` as the chronological handoff log.
- Keep `.context/lessons-learned.md` for durable pitfalls only.
