---
title: ADR-0007 External Business Truth
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - traceability
  - requirements
---

# ADR-0007: External Business Truth

## Decision

Jira, Notion, Linear, monday.com, or another external system may remain the business source of truth. Entroping stores trace IDs and optional local Markdown caches, not a forced duplicate source of truth.

## Context

The product needs traceability without making users rewrite all business requirements into Entroping-specific files.

## Consequences

- Hurl files can include `# entroping: story_id=...` and `# entroping: doc_url=...`.
- Markdown story caches are optional and read-only by default.
- Architect generation must stay source-grounded.

Links: [[docs/user/USER_GUIDE|USER_GUIDE]], [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]], [[docs/evolution/REQUIREMENTS_ANALYSIS|REQUIREMENTS_ANALYSIS]]

