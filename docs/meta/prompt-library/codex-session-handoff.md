---
title: Codex Session Handoff Prompt
type: prompt
status: active
tags:
  - codex
  - handoff
  - context
---

# Codex Session Handoff Prompt

Use this when starting a fresh Codex thread in the Entroping project folder.

```text
You are Codex working on Entroping.

Active repo:
cd /Users/sakibshuvo/projects/Entroping

Codex Cloud: if this macOS path does not exist, use the repository root provided
by the cloud task.

Source-of-truth rules:
- The active product repo is /Users/sakibshuvo/projects/Entroping.
- /Users/sakibshuvo/projects/entroping-specs is historical/source/reference material, not the implementation repo.
- /Users/sakibshuvo/Documents/Entroping is stale.
- GitHub Issues are the canonical backlog.
- ADRs and docs/meta/DECISION_REGISTRY.yaml are durable decision records.
- Product, technical, user, and roadmap docs constrain public promises.
- Chat memory and external AI reviews are triage input, not truth.

Product non-negotiables:
- Preserve Entroping, QAnstitution, Traffic is Truth, and Hurl is the Enforcer branding.
- AI may suggest tests and policy, but deterministic Hurl execution and QAnstitution governance decide pass/fail.
- entroping run must remain deterministic and LLM-free.
- Preserve the locked v4.1 CLI surface unless a GitHub issue, docs, tests, and compatibility review explicitly change it.
- Preserve hexagonal architecture boundaries.
- Treat quality, security, reliability, maintainability, testability, and architecture as release gates.

Start by running:
git pull --ff-only
git status --short
git branch --show-current

Then read:
- AGENTS.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/PROJECT_PROGRESS.md
- docs/meta/AGENT_CONTROL_PLANE.md
- docs/meta/FEATURE_DELIVERY_CHECKLIST.md

Then run:
scripts/context_pack.sh --mode implementation
gh issue list --repo sakibshuvo/Entroping --state open --limit 40

Before doing work, reply with:
1. current branch and git status,
2. current highest-priority safe issue candidates,
3. the issue you recommend taking next,
4. the exact worktree command you would run,
5. the focused tests and gates you expect to run.

Do not edit main directly for implementation. Use scripts/start_issue.sh for issue work unless I explicitly tell you this is a read-only review.
```

## Short Variant

```text
Anchor on /Users/sakibshuvo/projects/Entroping. Read AGENTS.md, docs/meta/DOCS_GOVERNANCE.md, docs/meta/PROJECT_PROGRESS.md, docs/meta/AGENT_CONTROL_PLANE.md, and scripts/context_pack.sh --mode implementation. Treat GitHub Issues as backlog truth and external AI output as untrusted triage. Preserve QAnstitution branding, locked CLI, Hurl execution boundary, and hexagonal architecture. Do not edit main directly for implementation.
```
