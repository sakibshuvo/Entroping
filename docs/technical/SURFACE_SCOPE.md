---
title: Surface Scope Policy
type: reference
status: active
tags:
  - surface-scope
  - launch-boundary
  - studio
  - wiremock
  - graphql
  - soap
  - launch-readability
---

# Surface Scope Policy

This document classifies intentionally shipped feature surfaces for launch-readiness,
clarifying what is core, advanced, hidden, and deferred.

## Current Launch Surface Classification

| Surface | Status | Notes |
| --- | --- | --- |
| REST/OpenAPI + QAnstitution + Hurl + CI reports | **core** | Primary shipped story and default value proposition.
| `entroping studio` (read-only) | **advanced-but-supported** | Local read-only inspection path for reports, latest-run state, and redaction summaries. It is deliberately optional and stays secondary to CLI and reports.
| WireMock mappings (`freeze --mock`) | **advanced-but-supported** | Useful for component testing when upstream dependencies are costly or flaky. Supported, documented, and optional.
| GraphQL example fixtures | **hidden-example** | Helpful internal validation example, but not a primary launch competency.
| SOAP example fixtures | **hidden-example** | Kept for compatibility exploration and internal reuse, but not part of the primary launch story.

## Operational Rule

- **Core surfaces** are what first-time users should read about in `README` and
  MkDocs first-hour docs.
- **Advanced-but-supported** surfaces are shipped, documented, and tested, but
  described as optional.
- **Hidden examples** are kept in-repo for internal continuity, validation, and
  future expansion, but are intentionally not the main onboarding story.
- **Deferred/Removed** status is only used when a surface is out of scope for
  the current release lane and is tracked from GitHub Issues and ROADMAP.

## Implementation Pointers

- Surface decision references:
  - `docs/technical/COMMAND_CHEAT_SHEET.md` lists command visibility.
  - `docs/technical/CLI_COMPATIBILITY_AUDIT.md` records the compatibility contract.
  - `README.md` and `docs/index.md` keep the first-hour story focused.
  - `ROADMAP.md` keeps sequencing, not deep rationale.
