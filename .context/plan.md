# Entroping Implementation Plan

**Date:** 2026-07-29
**Status:** Issue #1561 implementation and release gates in progress

## Objective

Keep the open-source alpha credible by preserving the deterministic governance
loop while tightening the places that can create requirement drift, weak context
handoff, or multi-agent workflow friction:

```text
init -> validate QAnstitution -> discover Hurl tests -> inject gates into temp files -> run Hurl -> emit reports
```

The repo should remain usable as an Obsidian vault, a GitHub issue-driven
project, and a Codex workspace with fast context rehydration.

## Current Issue Slice: #1561 Factory Control-Plane Protection

Prevent Tier A workers from changing budget, routing, scheduler,
repository-authority, workflow, security-gate, or credential boundaries.
Maintainer labels own autonomy; issue prose and model output remain untrusted.
Enforce the canonical policy at queue submission, pre-dispatch revalidation,
patch review, and PR readiness with rename, alias, symlink, and multi-file
coverage. Keep product runtime, Brain/LiteLLM, Hurl, QAnstitution, and traffic
behavior unchanged.

## Current Baseline

- The locked v4.1 CLI surface, deterministic `entroping run`, Hurl execution,
  QAnstitution governance, and hexagonal boundaries remain release gates.
- The public launch and docs share `DESIGN.md` tokens, static GitHub Pages
  output, and canonical Markdown without a duplicate docs tree.
- Report commands stay local-only unless their docs explicitly say otherwise;
  they must not call providers, vendor APIs, hosted services, or mutate tickets,
  chat, PRs, dashboards, source Hurl, `.entroping/` state, or `entroping run`.
- Evidence packets use bounded local reads, relative paths, schema versions,
  SHA-256 hashes, source states, compact summaries, safe writes, and secret-like
  output rejection. Missing fixed optional sources should become partial or
  insufficient state; invalid, oversized, unreadable, non-file, symlinked,
  wrong-schema, or secret-like sources must become invalid or unsafe.
- AI worker lanes are advisory. OpenCode/DeepSeek outputs require Codex
  validation against local files, tests, and CI before commit or merge.
- Context packs, issue-scoped worktrees, PR body checks, regression/security
  gates, quality audit, and `scripts/finish_issue.sh` are the durable marathon
  loop. Keep context files concise enough for `scripts/context_pack.sh --mode
  implementation --manifest` to stay under budget.
- Public/commercial direction stays local-first: Evidence Cloud, connectors,
  observability, QA Brain, and cross-surface workflows start as value-free local
  packets before uploads, write-back, hosted sync, vendor adapters, or model
  calls.
- Completed detailed history lives in `docs/meta/PROJECT_PROGRESS.md`,
  `.context/changelog.md`, `docs/meta/DECISION_REGISTRY.yaml`, release
  evidence, PRs, and git history instead of this active plan.

## Historical Milestone Pointers

Older completed-slice detail was compressed on 2026-06-19 to keep
`scripts/context_pack.sh --mode implementation --strict-budget` useful for
agent work. The active plan should carry current constraints, current baseline,
and next validation targets rather than a full implementation ledger.

Lossless sources for compressed history remain in
`docs/meta/PROJECT_PROGRESS.md`, `.context/changelog.md`,
`docs/meta/DECISION_REGISTRY.yaml`, and git history.

Guarded anchors retained for docs-link tests:

- Issue #202 defines organization QAnstitution import controls.
- Issue #204 documents non-GitHub CI provider recipes.

## Current Validation Queue

Keep each marathon issue narrow, tested, merged through GitHub, and cleaned up
before starting the next branch. Near-term validation targets remain package
index proof (#303-#305), downstream feedback (#306), stable-core compatibility
(#308), and non-GitHub CI proof (#309-#310); package issue #268 stays gated on
package-index evidence.

## Explicitly Deferred

- Non-prompt merge generation, Studio mutation workflows, Nuitka packaging,
  hosted/cloud features, and generated context-tool artifacts in Git.

## Working Context Loop

At the start of a new Codex thread, hydrate from `AGENTS.md`, `.context/plan.md`,
`docs/meta/PROJECT_PROGRESS.md`, `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`,
  `docs/meta/DOCS_GOVERNANCE.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, and
  issue files found with `rg`. For product history, start with
`docs/meta/VAULT_INDEX.md`. To start issue work, dry-run the launcher first:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
```

## Constraints

- Preserve the locked command namespace.
- Keep `entroping run` deterministic and LLM-free.
- Keep Hurl as the only API execution engine.
- Do not send secrets or raw traffic to LLM providers.
- Keep generated state, reports, local env files, and generated local context output out of Git.
- Treat security and quality checks as release gates.
- Use the feature delivery checklist for TDD, regression, architecture, security, multi-agent, documentation, and commit-readiness gates.
- Use GitHub Issues for individual work items and `docs/meta/PROJECT_PROGRESS.md` for simple Obsidian progress tracking.
