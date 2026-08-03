# Entroping Implementation Plan

**Date:** 2026-08-03
**Status:** Issue #1574 is in progress pre-merge; Tier A orchestration requires acceptance review before activation.

## Objective

Keep the open-source alpha credible by preserving the deterministic governance
loop while tightening the places that can create requirement drift, weak context
handoff, or multi-agent workflow friction:

```text
init -> validate QAnstitution -> discover Hurl tests -> inject gates into temp files -> run Hurl -> emit reports
```

The repo should remain usable as an Obsidian vault, a GitHub issue-driven
project, and a Codex workspace with fast context rehydration.

## Current Issue Slice: #1574 Tier A Worktree Orchestration

Add a maintainer-only, plan-first `factoryctl orchestrate` adapter without
changing the product `entroping` CLI. It accepts strict owner-only request and
proposal files, revalidates the live scheduler owner and the exact
`completed-unsettled` proposal handoff plus scheduler-persisted delivery
authority, and may create a missing canonical
issue worktree only through `scripts/start_issue.sh`. Explicit `--apply`
checks and applies only static Markdown under `docs/product/` or `docs/user/`
in the two docs lanes. Source, tests, scripts, config, workflows, and
machine-consumed control docs escalate until OS/container isolation exists.
Gates come only from the validated target worktree's exact allowlist and emit a value-free
revision-bound receipt. A separate private lifecycle journal makes exact
terminal replay deterministic; ambiguous mutation, authority drift, gate
drift, cancellation after mutation, main-checkout drift, or interrupted active
replay becomes `uncertain` and requires recovery. Scheduler settlement and
completion remain a later trusted control-plane action.

Free-local write admission has one public entrypoint,
`tick_selected_delivery`, which fetches fresh selection state internally and
uses private admission helpers. Generic scheduler APIs expose no admission or
snapshot seam and reject free-local writes; paid writes retain their existing
reservation or authorization authority path. The policy digest follows an
AST-derived transitive internal-import closure from fixed authority roots and
includes executed parent package initializers recursively under fixed aggregate
path/load/byte/AST/depth budgets, then verifies every loaded closure module
against canonical-main commit bytes.

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
- Issues #1571 through #1573 are done; #1574 adds the separate Tier A worktree
  orchestration adapter without changing product runtime or merge authority.
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
before starting the next branch. The current factory dependency chain is #1571
recovery, #1572 status, #1573 quality correlation, and #1574 Tier A orchestration,
#1575 end-to-end restart proof, and #1576 PR/CI/merge cleanup. External stable
core targets remain package-index proof (#303-#305), downstream feedback
(#306), and non-GitHub CI proof (#309-#310).

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
