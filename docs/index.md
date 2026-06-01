---
title: Entroping Documentation
type: index
status: active
tags:
  - docs-site
  - public
---

# Entroping Documentation

Entroping is a local-first runtime governance layer for AI-assisted backend
development. Use this site for public docs that should be easy to read outside
Obsidian.

Start here:

- **Getting Started:** [User Guide](user/USER_GUIDE.md),
  [QAnstitution First Hour](user/QANSTITUTION_FIRST_HOUR.md),
  [Use Cases](user/USE_CASES.md), and
  [Launch Demo Assets](assets/launch/README.md).
- **Policy:** [QAnstitution Reference](technical/QANSTITUTION_REFERENCE.md),
  [QAnstitution JSON Schema](technical/qanstitution.schema.json),
  [Policy Pack Layout](technical/POLICY_PACK_LAYOUT.md), and
  [Policy Pack Distribution](technical/POLICY_PACK_DISTRIBUTION.md).
- **CI and Reports:** [GitHub Actions Starter](user/GITHUB_ACTIONS_STARTER.md),
  [CI Provider Recipes](user/CI_PROVIDER_RECIPES.md),
  [Drift Baseline Workflow](user/DRIFT_BASELINE_WORKFLOW.md), and
  [Report Schemas](technical/REPORT_SCHEMAS.md).
- **Setup and Strategy:** [AI Provider Setup](user/AI_PROVIDER_SETUP.md),
  [Open-Core Boundaries](product/OPEN_CORE_BOUNDARIES.md), and
  [PyPI Release Runbook](meta/PYPI_RELEASE_RUNBOOK.md).

## How This Site Fits

This site is the public reading path generated from the repository's Markdown.
It should help new users learn and evaluate Entroping without opening the
Obsidian vault.

- README sells and orients.
- MkDocs is the public reading path.
- GitHub Issues track work.
- `ROADMAP.md` sequences releases.
- `docs/meta/VAULT_INDEX.md` maps the Obsidian vault.
- `docs/meta/DOCS_GOVERNANCE.md` defines update rules.

## Project Context

Historical, evolution, source, and maintainer-process notes remain in the
repository for traceability, but they are not the first public reading path.
Use [Technical Design](technical/TDS.md),
[Threat Model](technical/THREAT_MODEL.md),
[CLI Compatibility Audit](technical/CLI_COMPATIBILITY_AUDIT.md),
[Command Cheat Sheet](technical/COMMAND_CHEAT_SHEET.md),
[Studio Mutation Workflow Design](technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md),
[Python Compatibility](technical/PYTHON_COMPATIBILITY.md),
[Release Evidence](meta/RELEASE_EVIDENCE.md),
[Install Smoke Matrix](meta/INSTALL_SMOKE_MATRIX.md),
[Downstream Smoke Evidence](meta/DOWNSTREAM_SMOKE_EVIDENCE.md), and
[Downstream Feedback Kit](meta/DOWNSTREAM_FEEDBACK_KIT.md) when you need the
deeper implementation or release-evidence layer.

Canonical source still lives in the repository Markdown. The Obsidian vault
entry point remains `docs/meta/VAULT_INDEX.md`; this page is only the public web landing page.
