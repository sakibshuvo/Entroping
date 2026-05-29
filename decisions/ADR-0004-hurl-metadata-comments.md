---
title: ADR-0004 Hurl Metadata Comments
type: decision
status: accepted
date: 2026-05-29
tags:
  - decision
  - hurl
  - metadata
---

# ADR-0004: Hurl Metadata Comments

## Decision

Entroping metadata belongs in Hurl comments:

```hurl
# entroping: tags=smoke,checkout
# entroping: story_id=CHK-001
```

## Context

Custom `tags` or `meta` keys inside Hurl `[Options]` are not safe because `[Options]` is for real Hurl options.

## Consequences

- Hurl ignores Entroping metadata safely.
- Entroping parses comments for tags, story IDs, owners, and external document URLs.
- Generated tests must avoid custom non-Hurl options.

Links: [[docs/technical/TDS|TDS]], [[docs/technical/QANSTITUTION_REFERENCE|QANSTITUTION_REFERENCE]], [[docs/user/USER_GUIDE|USER_GUIDE]]

