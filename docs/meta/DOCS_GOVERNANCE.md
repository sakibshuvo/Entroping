---
title: Documentation Governance
type: runbook
status: active
tags:
  - documentation
  - roadmap
  - governance
  - agents
---

# Documentation Governance

This is the documentation control plane. Its job is to stop Entroping from
becoming a Markdown ocean again.

The rule is simple:

```text
GitHub tracks work. Obsidian explains why. README sells. Roadmap sequences. Specs constrain.
```

## Update Matrix

| Change type | Required update | Usually do not update |
| --- | --- | --- |
| New backlog item | GitHub issue, labels, milestone, project board | `ROADMAP.md` |
| Current issue status changes | GitHub issue and project board | Product specs |
| Release priority or sequence changes | `ROADMAP.md`, GitHub milestones, `PROJECT_PROGRESS.md`, `.context/changelog.md` | TDS unless architecture changed |
| User-visible command or behavior changes | User docs, command cheat sheet, README if public onboarding changes | ADR unless decision changed |
| Architecture, boundary, storage, provider, or execution changes | `TDS.md`, ADR if durable, `.context/changelog.md` | README unless user-facing |
| Product contract changes | `PRODUCT_SPEC.md`, roadmap if priority changes, ADR if durable | Low-level implementation docs |
| Bug fix with durable lesson | GitHub issue, regression test, `.context/changelog.md`, `.context/lessons-learned.md` if reusable | Roadmap unless priority changed |
| Source-material reconciliation | Evolution docs, source map, issue if action is needed | Runtime docs until validated |

Most feature branches should touch one to three documentation surfaces. If a
branch touches more than that, the PR must explain why.

## Roadmap Change Gate

`ROADMAP.md` is not a backlog. It should only change when one of these is true:

- a release target changes.
- a milestone is added, removed, renamed, or reordered.
- a feature moves into or out of near-term scope.
- an open-core boundary changes.
- a public launch promise changes.

All implementation tasks belong in GitHub Issues. If a roadmap item needs work,
create or update the issue first, then update the roadmap only if the sequence
or public scope changed.

## Documentation Impact Declaration

Every pull request must include a checked Documentation Impact Declaration in
the PR body. CI validates this on pull requests with `scripts/pr_body_check.py`.

Accepted declaration types:

- No docs update needed, with a reason.
- User-facing docs updated.
- Technical docs updated.
- Roadmap/progress updated.
- ADR/spec/context updated.

This forces humans and agents to make the documentation decision explicit.

## Agent Rules

Agents must do the following before patching documentation:

1. Identify the canonical owner from the update matrix.
2. Update the smallest set of docs that preserves truth.
3. Avoid duplicating GitHub issue details in Obsidian.
4. Run `scripts/doc_governance_check.sh`.
5. Include the Documentation Impact Declaration in the PR or handoff.

Agents must not update `ROADMAP.md` just because code changed. Roadmap edits
require roadmap-change-gate evidence.

## Human Rules

Humans should use this shorter loop:

1. Put work in GitHub Issues.
2. Use the Project board for status.
3. Update Obsidian only for phase status, decisions, and product history.
4. Ask whether the roadmap sequence changed before editing `ROADMAP.md`.

## Enforcement

The enforcement chain is:

```text
PR template -> PR body check in CI -> doc governance check -> feature gate -> regression gate
```

- `.github/pull_request_template.md` forces the declaration.
- `scripts/pr_body_check.py` validates the declaration on pull requests.
- `scripts/doc_governance_check.sh` validates the documentation control plane.
- `scripts/feature_gate.sh` runs the documentation governance check.
- `scripts/regression.sh` runs the feature gate.

If a future change weakens this chain, local gates and CI should fail.
