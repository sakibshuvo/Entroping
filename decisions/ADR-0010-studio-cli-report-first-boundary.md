---
title: ADR-0010 Studio CLI Report First Boundary
type: decision
status: accepted
date: 2026-05-31
tags:
  - decision
  - studio
  - reports
  - roadmap
---

# ADR-0010: Studio CLI Report First Boundary

## Decision

CLI and reports remain the primary workflow for Entroping v0.3.

Studio remains optional and read-only. It is a secondary local inspection surface
over deterministic artifacts, not the product's primary runner, editor, or
workflow engine.

For v0.3:

- Issue #190 may stay in v0.3 only as a read-only traffic-session browser over
  redacted traffic state and counts/summaries that are safe to inspect.
- Issue #192 may stay in v0.3 only as a read-only applied-gate drilldown over
  existing run/report metadata and injected rule IDs.
- Issue #196 stays in v0.3 as a design gate only. No Studio mutation
  implementation is planned for v0.3.
- Textual remains an optional extra and must not be required for default
  installs, CI, or headless use.

## Context

The source history contains strong enthusiasm for a Textual "mission control"
experience because it demos well and can make local debugging feel native. The
current implementation already honors the useful part of that idea: `studio`
exists as an optional read-only TUI over local state.

The execution risk is scope. Entroping's core value is deterministic runtime
governance: Hurl execution, QAnstitution gates, redacted traffic, and reports
that CI and humans can trust. Custom TUI mutation workflows would add review,
security, and maintenance cost before the CLI/report path is mature.

## Consequences

- Build durable CLI/report artifacts before adding Studio views that depend on
  them.
- Studio drilldowns must not fetch raw traffic, call LLM providers, run Hurl, or
  write config/tests/state in v0.3.
- Traffic and applied-gate Studio work should be implemented as small adapters
  over existing redacted state and report models.
- Mutation workflows require a separate accepted design before any code lands.
- Public messaging should sell Entroping through the two-minute CLI demo,
  reports, and CI proof first; Studio is useful polish, not the adoption
  blocker.

Links: [[ROADMAP]], [[docs/user/USER_GUIDE|USER_GUIDE]], [[docs/technical/TDS|TDS]], [STUDIO_MUTATION_WORKFLOW_DESIGN.md](../docs/technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md), [#190](https://github.com/sakibshuvo/Entroping/issues/190), [#192](https://github.com/sakibshuvo/Entroping/issues/192), [#196](https://github.com/sakibshuvo/Entroping/issues/196), [#231](https://github.com/sakibshuvo/Entroping/issues/231)
