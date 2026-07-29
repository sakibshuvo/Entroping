---
title: ADR-0025 Factory Control-Plane Protection
type: decision
status: accepted
date: 2026-07-29
tags:
  - decision
  - factory
  - agents
  - security
  - architecture
---

# ADR-0025: Factory Control-Plane Protection

## Decision

Tier A autonomy is granted only by exactly one maintainer-owned GitHub label:
`autonomy:tier-a`, `autonomy:tier-b`, or `autonomy:tier-c`. Issue bodies,
comments, prompts, worker output, and PR prose are untrusted inputs and cannot
grant or lower autonomy.

`scripts/factory_control_plane_policy.py` is the canonical code-owned policy
for budget, provider-routing, scheduler, repository-authority, and credential
surfaces. Tier A queue submission and pre-dispatch revalidation, proposed-patch
review, and PR readiness all consume this policy. Paths are normalized and
invalid aliases fail closed. Existing symlinks, generated symlink patches,
renames, both sides of a renamed CI diff, and every file in a multi-file patch
are evaluated before Tier A work can proceed.

Protected proposals are not discarded. They are denied Tier A authority and
routed to Codex or human review as Tier B or Tier C work. Denials contain only
relative paths and reason codes, never issue prose, patch content, secrets, or
credential values. Before either JSON or text rendering, the complete compact
packet projection is serialized and rejected if secret-like content remains.

## Boundary

This policy protects the maintainer factory; it does not change Entroping's
product runtime, LiteLLM boundary, Hurl execution, or QAnstitution governance.
It does not make GitHub CODEOWNERS a required-review mechanism by itself.
Branch protection remains an independent repository setting.

## Consequences

- A new autonomous issue must receive exactly one reviewed autonomy label.
- Adding or moving a control-plane surface requires a policy update, focused
  policy tests, CODEOWNERS review, and the release-CI-architecture gate.
- A Tier A worker cannot authorize changes to this policy, its enforcement
  scripts, their tests, workflows, ownership, budget, routing, or credentials.
- Rename-safe NUL-delimited CI enumeration preserves both paths without
  interpreting filenames as shell input.
- Invalid or ambiguous metadata stops autonomous dispatch and merge readiness.

## Evidence

- GitHub issue #1561 owns the implementation and verification record.
- `scripts/factory_control_plane_policy.py` owns protected path and autonomy
  label classification.
- `scripts/factory_patch_inspection.py` owns bounded Git patch parsing,
  truncation detection, rename/copy coverage, and generated-symlink detection.
- `scripts/factory_review_packet.py` remains the stable CLI facade;
  `scripts/factory_review_packet_model.py` builds compact artifact projections,
  and `scripts/factory_review_packet_validation.py` enforces packet contracts.
- `scripts/ai_jobs.py` and `scripts/pr_body_check.py` enforce the queue and PR
  boundaries.
- `.github/workflows/ci.yml` projects rename-safe changed paths into the PR
  checker.
- `docs/meta/AGENT_CONTROL_PLANE.md` owns policy and update procedures.
