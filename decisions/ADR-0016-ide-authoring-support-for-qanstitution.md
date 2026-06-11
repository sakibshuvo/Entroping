---
title: ADR-0016 IDE Authoring Support for QAnstitution
type: decision
status: accepted
date: 2026-06-11
tags:
  - decision
  - ide
  - editor-support
  - schema
  - open-core
---

# ADR-0016: IDE Authoring Support for QAnstitution

## Decision

For QAnstitution authoring, Entroping keeps the core path schema-first and local:

- The checked-in
  [`docs/technical/qanstitution.schema.json`](../docs/technical/qanstitution.schema.json)
  is the primary authoring aid.
- VS Code and JetBrains workflows are supported through existing schema mapping
  guidance, not by a required core extension.
- No additional telemetry, hosted login, or provider-key flow is introduced by
  QAnstitution authoring support in core.

A dedicated IDE extension for run shortcuts, policy linting, or richer
authoring workflows is explicitly out of Apache-2.0 core scope in this issue and
can be evaluated as a separate paid/team surface once product value is proven.

## Rationale

Issue #597 asked whether to pursue:

- schema-only support,
- a lightweight extension,
- or a language-server-backed workflow.

Schema-only support already gives immediate value with minimal coupling, no runtime
changes, and no dependency on local or hosted services. It also preserves the
open-core boundary by keeping authoring ergonomics inside the existing
`qanstitution.yaml` and schema contract.

An extension can be valuable in team settings, but it changes surface area, update
cadence, and distribution expectations. Without explicit roadmap evidence, that
belongs to a future optional surface.

## First Useful Workflow

Entroping users should prioritize this sequence today:

1. Enable schema-backed editing for `qanstitution.yaml` in their IDE.
2. Edit policy with immediate shape feedback from schema completion/validation.
3. Validate authoritative behavior with `entroping doctor --ci` or `entroping
   report policy`.

That path keeps quality ownership in local files, local validation, and Entroping's
existing command flow.

## Consequences

- Core documentation and reference docs now describe JetBrains-friendly schema
  configuration as well as VS Code mapping.
- Optional IDE integrations can be tracked as follow-on work without forcing core
  architectural changes now.
