---
title: ADR-0017 Official GitHub Action Boundary
type: decision
status: accepted
date: 2026-06-11
tags:
  - decision
  - github-actions
  - official-action
  - distribution
  - ci
---

# ADR-0017: Official GitHub Action Boundary

## Decision

Entroping should keep `entroping init --github-actions` as the supported
downstream CI onboarding path until a reusable official action has package-index
proof and downstream evidence.

When the reusable action is built, it should live in a dedicated
`entroping/action` repository instead of this implementation repository. The
action should install released Entroping artifacts from the package index. A
tagged GitHub release fallback is acceptable only for prerelease prototypes and
must be explicit in the workflow.

The action contract is intentionally narrow:

- install or verify Hurl before execution;
- run `entroping doctor --ci` before `entroping run --ci`;
- upload local `reports/` artifacts and avoid `.entroping/` by default;
- keep default permissions read-only;
- make PR comments opt-in and permission-scoped;
- never call LLM providers during the deterministic `run` path.

## Rationale

The generated starter workflow is transparent and reviewable today. It lets
teams inspect every install, Hurl verification, report, and artifact step before
committing it to their repository.

An official marketplace-style action is useful for adoption, but it introduces a
separate release cadence, action metadata, support surface, and permission
contract. Shipping it before package-index proof would either duplicate source
install complexity or hide unstable install behavior behind a friendlier
interface.

## Consequences

- This repository remains the source of truth for the Python CLI, packaged
  starter workflow, and action design contract.
- The action repository can be created after TestPyPI/PyPI evidence proves the
  package install path.
- Public docs must distinguish the current generated starter from the future
  reusable action.
- Stable-core readiness remains false until package-index proof, repeated
  release evidence, compatibility discipline, and downstream feedback exist.
