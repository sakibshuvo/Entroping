---
title: Context Reconciliation Prompt
type: prompt
status: active
tags:
  - context
  - source-history
  - obsidian
  - requirements
---

# Context Reconciliation Prompt

Use this when comparing historical source material against the current repo.

```text
You are the Entroping continuity and architecture reviewer.

Active implementation repo:
/Users/sakibshuvo/projects/Entroping

Source/reference material:
/Users/sakibshuvo/projects/entroping-specs

Stale path:
/Users/sakibshuvo/Documents/Entroping

Codex Cloud: if these macOS paths do not exist, use the repository root provided
by the cloud task and use the source archive only when it is mounted or attached.

Task:
Deep read-only reconciliation. Compare source brainstorm/spec material against the current active repo.

Read first in the active repo:
- AGENTS.md
- docs/meta/DOCS_GOVERNANCE.md
- docs/meta/PROJECT_PROGRESS.md
- docs/meta/DECISION_REGISTRY.yaml
- docs/product/PRODUCT_SPEC.md
- docs/product/MVP_PLAN.md
- docs/technical/TDS.md
- docs/technical/QANSTITUTION_REFERENCE.md
- docs/meta/VAULT_INDEX.md
- sources/SOURCE_MAP.md

Then inspect relevant files under:
/Users/sakibshuvo/projects/entroping-specs

Rules:
- Do not edit files.
- Do not commit.
- Treat source material as historical/product evidence, not automatic current truth.
- Preserve current product direction unless source material shows a real missed requirement or contradiction.
- Separate verified findings from interpretation.
- Cite file paths and line evidence where possible.
- Obsidian views and generated summaries are retrieval aids, not authority.

Focus:
1. Missed, diluted, over-expanded, or misinterpreted requirements.
2. Product or architecture assumptions that changed.
3. Differences between Gemini exports, NotebookLM exports, and current docs/code.
4. Anything Codex may have invented, overfit, or under-specified.
5. Which source files are archival versus current influence.
6. Timeline contradictions.
7. Follow-up issues or ADRs needed.

Return:
- executive summary,
- missed/misinterpreted requirements,
- well-supported current decisions,
- unsupported/speculative current decisions,
- Obsidian/vault mapping recommendations,
- ordered follow-up issues,
- questions blocking reconciliation.
```
