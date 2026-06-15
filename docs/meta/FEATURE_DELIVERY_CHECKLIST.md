---
title: Feature Delivery Checklist
type: checklist
status: active
tags:
  - workflow
  - tdd
  - quality
  - security
  - agents
---

# Feature Delivery Checklist

Use this checklist for every non-trivial Entroping feature. It is the executable version of the autonomous workflow: every gate needs file evidence, command evidence, or a documented exception before commit.

## 0. Feature Intake

- [ ] Pick exactly one feature or defect from `docs/product/MVP_PLAN.md`, an issue, or a dedicated spec.
- [ ] Create or link the GitHub issue that tracks this feature, bug, or regression.
- [ ] Write the feature outcome in one sentence.
- [ ] Identify the user-visible command, file, or behavior that will prove the feature works.
- [ ] List the source-of-truth files read for this task.
- [ ] Confirm the feature does not expand the locked v4.1 command surface unless the spec was updated first.

## 1. Context Rehydration

- [ ] Read `AGENTS.md`.
- [ ] Read `.context/plan.md`.
- [ ] Read `docs/product/MVP_PLAN.md`.
- [ ] Read `docs/technical/TDS.md`.
- [ ] Read `docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md`.
- [ ] Read the specific feature spec, issue, ADR, or failing test.
- [ ] Note any stale or contradictory docs before editing code.

## 2. Agent Coordination

- [ ] Declare the autonomy tier from `docs/meta/AGENT_CONTROL_PLANE.md`: Tier A autonomous lane, Tier B assisted lane, or Tier C restricted lane.
- [ ] Assign merge authority for the branch: autonomous worker for Tier A only after gates and CI, or human/Codex for Tier B/Tier C.
- [ ] Give every helper agent a bounded brief with allowed files, read-only versus write access, and expected output.
- [ ] Do not let two agents edit the same file family at the same time.
- [ ] Treat OpenCode, DeepSeek, local Qwen/oMLX, and generated summaries as evidence sources, not authority unless a Tier A PR independently proves itself through deterministic gates and CI.
- [ ] Require helper findings to cite local file paths, line numbers, and a reproducible command or reasoning path.
- [ ] Resolve Tier B/Tier C conflicts in the parent thread before applying patches; Tier A workers must stop and escalate when scope becomes ambiguous or restricted.

## 3. TDD And Test Pyramid

- [ ] Write or update the failing test first when the behavior can be tested before implementation.
- [ ] Add unit tests for pure domain or bridge behavior.
- [ ] Add adapter tests for CLI, filesystem, subprocess, report, proxy, or LLM boundaries.
- [ ] Add regression tests for any bug fixed or risky edge case discovered.
- [ ] Add integration or smoke coverage when behavior crosses subsystem boundaries.
- [ ] For future Hurl runner work, add fixture Hurl files and real Hurl smoke checks when `hurl` is available.
- [ ] Avoid broad mocks when a focused fixture or subprocess stub gives stronger evidence.

## 4. Implementation

- [ ] Keep the change scoped to the selected feature.
- [ ] Preserve hexagonal dependencies: domain modules must not import CLI, core, brain, or studio adapters.
- [ ] Keep `entroping run` deterministic and LLM-free.
- [ ] Use Hurl as the API execution boundary; do not replace it with Python HTTP calls.
- [ ] Validate boundary inputs: CLI args, YAML, paths, globs, Hurl metadata, OpenAPI, traffic, and model output.
- [ ] Use explicit errors, timeouts, bounded output, cleanup, and redaction for process or external-system work.

## 5. Local Verification

- [ ] Run the documentation governance gate before final review:

```bash
scripts/doc_governance_check.sh
```

- [ ] Run the standard gate:

```bash
scripts/feature_gate.sh
```

- [ ] Run the regression suite:

```bash
scripts/regression.sh
```

- [ ] For dependency, subprocess, LLM, proxy, report, or filesystem-sensitive work, run:

```bash
scripts/feature_gate.sh --security
scripts/regression.sh --security
```

- [ ] For docs-only changes, still run at least:

```bash
scripts/check.sh
```

- [ ] For validation marathons, release hardening, or maintenance-risk reviews, run:

```bash
scripts/audit_quality.sh
```

- [ ] Record any skipped check and the concrete reason in the final handoff or PR.

## 6. Regression And Architecture Review

- [ ] Check that existing tests still pass.
- [ ] Review `git diff` for unrelated edits, accidental generated files, secrets, and local state.
- [ ] Check imports for architecture drift.
- [ ] When package boundaries are touched, confirm `tests/test_architecture_boundaries.py` still covers the relevant import direction and provider boundary.
- [ ] Check command names and flags against `docs/technical/COMMAND_CHEAT_SHEET.md`.
- [ ] Check docs for claims that are not implemented yet.
- [ ] For public docs or launch copy, confirm `python scripts/public_claims_audit.py` passes.
- [ ] If the feature touches a boundary listed in `AGENTS.md`, request independent review before commit.

## 7. Security Review

- [ ] Re-check secret handling for logs, errors, reports, model prompts, captured traffic, and fixtures.
- [ ] Re-check path handling for traversal, glob overreach, symlink surprises, and destructive writes.
- [ ] Re-check subprocess calls for argument arrays, timeouts, bounded output, and no shell interpolation.
- [ ] Re-check dependency changes with default and all-extras audits.
- [ ] Re-check direct dependency license coverage with `uv run python scripts/dependency_license_check.py`.
- [ ] Re-check LLM flows for redaction, structured validation, and no provider-specific SDK drift.

## 8. Documentation And Context Preservation

- [ ] Read `docs/meta/DOCS_GOVERNANCE.md` and identify the canonical documentation owner before editing docs.
- [ ] Include a Documentation Impact Declaration in the PR or final handoff.
- [ ] Update `docs/meta/PROJECT_PROGRESS.md` after meaningful feature, bug, or roadmap changes.
- [ ] Update user-facing docs when behavior or commands change.
- [ ] Update technical docs when architecture, schemas, boundaries, or gates change.
- [ ] Update `.context/changelog.md` for meaningful changes.
- [ ] Update `.context/lessons-learned.md` for durable pitfalls, decisions, or commands.
- [ ] Add or update an ADR for decisions that should survive context resets.
- [ ] Keep Obsidian workspace state, generated local context output, local env files, reports, and `.entroping/` out of Git.

## 9. Commit Readiness

- [ ] `git status --short` contains only intentional changes.
- [ ] `git diff --check` passes.
- [ ] `git diff --cached --check` passes when files are staged.
- [ ] The branch has an atomic Conventional Commit message ready.
- [ ] The PR description or handoff includes what changed, how it was tested, security review status, docs updates, and known gaps.
- [ ] CI passes before merge.

## Non-Negotiable Gates

```text
No local file evidence -> no architecture claim.
No failing or targeted test -> no feature implementation start unless explicitly documented.
No issue or explicit task source -> no feature branch.
No regression suite -> no commit.
No security pass for sensitive boundaries -> no merge.
No Documentation Impact Declaration -> no PR.
No context update -> no durable memory.
No Agent Autonomy Declaration -> no autonomous merge.
Tier C restricted lane -> no autonomous merge.
No CI green -> no autonomous merge.
No parent integrator approval -> no Tier B/Tier C multi-agent patch lands.
```
