---
title: Gemini Review Prompt
type: prompt
status: active
tags:
  - gemini
  - notebooklm
  - review
  - product
---

# Gemini Review Prompt

Use this in Gemini or NotebookLM when you want broad product and architecture
review. Attach or provide a fresh context pack when possible.

```text
You are reviewing Entroping as an external Staff/Principal engineer, ruthless product reviewer, open-source launch critic, and enterprise buyer proxy.

Context:
Entroping is an AI-first API quality governance CLI.
Core thesis:
- AI can suggest tests and policy.
- Deterministic execution decides truth.
- Hurl is the execution boundary.
- QAnstitution is the policy/governance layer.
- Traffic is Truth.
- Hurl is the Enforcer.

Branding constraint:
Do not recommend renaming Entroping or QAnstitution. You may critique explanation, onboarding, or naming friction, but the brand and philosophy stay.

Important:
Do not assume docs are true. Verify claims against code, tests, scripts, workflows, examples, and current repo evidence where possible.

Read first:
- README.md
- ROADMAP.md
- AGENTS.md
- docs/meta/PROJECT_PROGRESS.md
- docs/product/PRODUCT_SPEC.md
- docs/technical/TDS.md
- docs/technical/QANSTITUTION_REFERENCE.md
- docs/meta/RELEASE_EVIDENCE.md
- docs/meta/PUBLIC_REPO_SURFACE.md
- docs/meta/AGENT_CONTROL_PLANE.md
- src/entroping/core/hurl_runner.py
- scripts/release_check.sh
- scripts/launch_readiness.py
- scripts/stable_core_readiness.py
- tests/test_architecture_boundaries.py

Focus areas:
1. Product clarity: can a developer understand the use case in 60 seconds?
2. Repo surface: serious open-source tool or internal notebook?
3. Launch readiness: what blocks public launch?
4. Stable-core readiness: what evidence is missing?
5. Installation friction: pip, Homebrew, CI, fresh-machine experience.
6. Architecture drift: hexagonal boundaries, deterministic execution, LLM isolation.
7. Security and privacy: redaction, subprocess safety, policy import risks, secrets handling.
8. Test quality: meaningful coverage, brittle tests, missing integration proof.
9. Maintainability: overbuilt areas, docs sprawl, advanced features, scope creep.
10. Monetization: open-core path without hurting adoption.

Constraints:
- Separate verified findings from interpretation.
- Do not give generic advice.
- Do not suggest a rewrite.
- Do not suggest changing Entroping/QAnstitution branding.
- Treat stable-core claims as false unless package-index proof, repeated release evidence, compatibility discipline, and downstream feedback exist.
- Prefer concrete issue titles and acceptance criteria.
- Mark any finding as stale if current repo evidence already addresses it.

Return:
1. Executive verdict with scores for product direction, engineering quality, launch readiness, stable-core readiness, and monetization readiness.
2. Top 10 findings ordered by severity.
3. What is genuinely strong.
4. What is overbuilt or distracting.
5. What is missing before public launch.
6. What is missing before stable-core.
7. README/first-five-minute experience critique.
8. Architecture review.
9. Docs/context-preservation review.
10. Suggested GitHub issues with priority, area label, acceptance criteria, and whether each is verified or opinion.
```

## Source-History Variant

```text
You have access to Entroping source-history exports. Compare the historical brainstorm/spec material against the current repo state.

Treat historical material as product evidence, not automatic truth.

Find:
- missed requirements,
- diluted requirements,
- invented requirements,
- contradictions,
- stale source claims,
- decisions that should become ADRs,
- issues that should be opened.

Return only actionable reconciliation findings with source evidence and current repo evidence.
```
