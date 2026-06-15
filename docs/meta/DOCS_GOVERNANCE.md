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

For the practical day-to-day distinction between GitHub and Obsidian, read
[[docs/meta/OBSIDIAN_VS_GITHUB|OBSIDIAN_VS_GITHUB]].

## Canonical Surfaces

| Surface | Owner job |
| --- | --- |
| `README.md` | Public front door, product promise, quick demo path |
| MkDocs site | Public reading path generated from `docs/` |
| GitHub Issues | Bugs, feature slices, chores, regressions, and action items |
| `ROADMAP.md` | Release sequence and public scope, not the full backlog |
| `CHANGELOG.md` | Public release history |
| `docs/meta/PROJECT_PROGRESS.md` | Current phase dashboard and stable-core blocker status |
| `docs/meta/VAULT_INDEX.md` | Obsidian vault map and historical/product context entry point |
| `docs/meta/DECISION_REGISTRY.yaml` | Durable decision index with links back to ADRs, docs, issues, and source evidence |
| `.context/` | Maintainer and agent handoff state |
| `decisions/` | Durable product and architecture decisions |

## Anti-Sprawl Rule

Do not create a new strategy document when an existing canonical owner can hold
the decision, evidence, or workflow. Update the existing canonical owner first:
`ROADMAP.md` for release sequence, GitHub Issues for actionable work,
`docs/meta/PROJECT_PROGRESS.md` for the daily dashboard, ADRs for durable
decisions, and `.context/changelog.md` for chronological handoff.

Only add a new document when all of these are true:

- no existing canonical owner can hold the information cleanly.
- the new file has a stable owner and expected reader.
- the file is linked from the vault index, README, MkDocs, or another canonical
  entry point as appropriate.
- the PR explains why the information could not live in an existing file.

GitHub Issues remain the backlog. Obsidian can explain why a decision happened,
but it must not become a second issue tracker.

Use `docs/meta/DECISION_REGISTRY.yaml` when the problem is retrieval, not new
prose. It should point to existing ADRs, docs, issues, and source exports. It
must not replace those sources, summarize away contradictions, or become a
second backlog.

## Documentation Inventory Rule

Use `scripts/docs_inventory.py --format json --strict` when the problem is
Markdown sprawl, active-context drift, or agent onboarding cost. The inventory
is generated from tracked repo files; do not create a second hand-maintained
Markdown tracker for the same purpose.

The inventory classifies tracked Markdown as active, reference, or archive,
records owner and audience hints, marks the default agent-context files, and
enforces the default-agent Markdown budget. `README.md` and
`docs/meta/VAULT_INDEX.md` remain important reference/navigation surfaces, but
they are not default implementation context.

## Public Docs Curation Rule

Public docs should lead with the shortest path to understanding, installing,
and trying Entroping. Do not expose maintainer memory as first-level public navigation
just because the file is useful to agents or future maintainers.

Use this order for public onboarding surfaces:

1. Product promise and two-minute proof.
2. Getting started and user workflow docs.
3. QAnstitution, policy, CI, and report references.
4. Roadmap and release-status evidence.
5. Technical reference.

Historical exports, evolution notes, source maps, Obsidian workflow notes,
agent-control notes, and `.context/` handoff files should stay linked from the
vault or relevant maintainer docs unless they directly help a new user adopt
the tool. New MkDocs top-level nav entries require a public-reader reason in
the PR; otherwise place the document under an existing group or leave it out of
the public nav.

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
| Durable decision indexing | `docs/meta/DECISION_REGISTRY.yaml`, linked ADR/docs/issues/source files | New narrative strategy doc |
| Public launch or README claim | README, roadmap/progress if scope changed, `scripts/public_claims_audit.py` evidence | TDS unless behavior changed |

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
Before opening or editing a PR, agents can validate a local body draft with
`scripts/pr_body_check.py --body-file <path>`.

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
4. Update `docs/meta/DECISION_REGISTRY.yaml` when a durable decision needs fast
   retrieval across context resets.
5. Run `scripts/doc_governance_check.sh`.
6. Run `python scripts/public_claims_audit.py` directly when changing public
   launch copy, README positioning, roadmap status, or release notes.
7. Include the Documentation Impact Declaration in the PR or handoff.

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
- `scripts/pr_body_check.py` validates the declaration on pull requests and,
  when CI or a local preflight passes changed files with `--changed-file`,
  requires security-gate evidence for sensitive runner, redaction, provider,
  proxy, report-evidence, worker, or secret-adjacent surfaces.
- `scripts/doc_governance_check.sh` validates the documentation control plane.
- `scripts/docs_freshness_check.py` rejects stale paths, broken local Markdown
  links, merge markers, unsupported readiness/security claims, deprecated
  command literals, and placeholder markers in current tracked Markdown.
- `scripts/docs_inventory.py --strict` reports tracked Markdown tiers and
  rejects default-agent context drift or duplicate active titles.
- `scripts/source_preservation_check.py` validates the decision registry,
  source-history anchors, and local registry links.
- `scripts/public_claims_audit.py` rejects unsupported production-readiness and
  security-guarantee claims in public Markdown.
- `scripts/shell_quality.sh` validates tracked shell script syntax and runs
  ShellCheck when available.
- `scripts/feature_gate.sh` runs the documentation governance and shell quality
  checks before Python checks.
- `scripts/regression.sh` runs the feature gate.

If a future change weakens this chain, local gates and CI should fail.
