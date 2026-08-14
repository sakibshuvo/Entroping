---
title: Entroping Documentation
description: "Start with the curated public path for installing, governing, running, and operating Entroping."
type: index
status: active
tags:
  - docs-site
  - public
---

# Entroping Documentation

Entroping is a local-first runtime governance layer for AI-assisted backend
teams. It keeps API integrity reviewable by turning specs, reviewed traffic,
and versioned policy into deterministic checks and CI-ready evidence. Hurl is
the deterministic local HTTP runner; Entroping adds policy, generation, and
reviewable evidence around it.

Choose the shortest path to your goal:

1. **[Run the local demo](../#demo)** — get deterministic API proof in two
   minutes without a provider key.
2. **[Protect an API](user/USER_GUIDE.md#3-new-project-quick-start)** — create
   or generate Hurl checks, apply policy, and review the resulting reports.
3. **[Add the CI gate](user/GITHUB_ACTIONS_STARTER.md)** — run the same proof in
   GitHub Actions before merge.

## Browse by Topic

- **Getting Started:** [User Guide](user/USER_GUIDE.md),
  [QAnstitution First Hour](user/QANSTITUTION_FIRST_HOUR.md),
  and [Use Cases](user/USE_CASES.md).
- **Alpha Status:** [Current Alpha Status](user/ALPHA_STATUS.md) explains the
  supported scope, caveats, and where to find the canonical release and issue
  evidence.
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
  [Surface Scope Policy](technical/SURFACE_SCOPE.md).

## What You Will Prove

- An OpenAPI spec or reviewed traffic can become reviewable API tests.
- Versioned policy can enforce status, auth, schema, header, and latency rules.
- The same deterministic checks can run locally and before merge.
- JSON, JUnit, and HTML reports can show what passed or failed without a model
  provider.

Entroping does not replace test design, human review, or production monitoring.
It keeps API behavior reviewable and repeatable at the local and CI boundary.

## How This Site Fits

This site is the public reading path generated from the repository's Markdown.
It is optimized for first-hour users; Obsidian remains a separate context layer.

- README sells and orients.
- Astro and Starlight render the public reading path from
  `site/public-docs.json`.
- GitHub Issues track work.
- `ROADMAP.md` sequences releases.
- `docs/meta/VAULT_INDEX.md` maps the Obsidian vault.
- `docs/meta/DOCS_GOVERNANCE.md` defines update rules.
- `docs/technical/SURFACE_SCOPE.md` clarifies what is core, advanced, or optional.

## Project Context

Historical, evolution, source, and maintainer-process notes remain in the
repository for traceability, but they are not the first public reading path.
Use [Technical Design](technical/TDS.md),
[Threat Model](technical/THREAT_MODEL.md),
[CLI Compatibility Audit](technical/CLI_COMPATIBILITY_AUDIT.md),
[Command Cheat Sheet](technical/COMMAND_CHEAT_SHEET.md),
[Surface Scope Policy](technical/SURFACE_SCOPE.md),
[Studio Mutation Workflow Design](technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md),
[Python Compatibility](technical/PYTHON_COMPATIBILITY.md), and the
`Maintainer Reference` navigation group when you need the deeper
implementation layer. For maintainer and release evidence, use
[Release Checklist](meta/RELEASE_CHECKLIST.md),
[Release Evidence](meta/RELEASE_EVIDENCE.md),
[PyPI Release Runbook](meta/PYPI_RELEASE_RUNBOOK.md),
[Homebrew Tap Prototype](meta/HOMEBREW_TAP_PROTOTYPE.md),
[Install Smoke Matrix](meta/INSTALL_SMOKE_MATRIX.md),
[Downstream Smoke Evidence](meta/DOWNSTREAM_SMOKE_EVIDENCE.md), and
[Downstream Feedback Kit](meta/DOWNSTREAM_FEEDBACK_KIT.md) when you need the
release-owner evidence layer. Maintainers rebuilding launch media can use the
[Demo Asset Reference](assets/launch/README.md).

Canonical source stays in the repository Markdown. The Obsidian vault entry
point remains `docs/meta/VAULT_INDEX.md`; this page is only the public web
landing page.
