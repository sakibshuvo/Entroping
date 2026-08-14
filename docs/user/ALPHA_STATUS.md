---
title: Current Alpha Status
description: "Understand the supported alpha scope, evidence boundaries, and canonical sources before adopting Entroping."
type: reference
status: active
tags:
  - alpha
  - public
  - release-status
---

# Current Alpha Status

**Product maturity:** Alpha

This page is a stable orientation point for the current Entroping alpha. It
describes the supported shape of the product and the evidence boundaries around
it; it is not a release tracker or a promise about production use.

## What the alpha covers

The public core is a local-first runtime-governance workflow for AI-assisted
backend development:

- deterministic Hurl-backed API checks on supported local environments;
- QAnstitution policy loading and gate evaluation;
- OpenAPI and reviewed-traffic paths for producing reviewable Hurl tests;
- sanitized local reports and dependency evidence; and
- provider-free local and GitHub Actions workflows.

Hurl execution and QAnstitution gates remain the pass/fail authority. Entroping
does not replace test design, human review, or production monitoring.

## Boundaries to keep in view

Windows is currently a doctor-only alpha path; Hurl-backed `entroping run` on
Windows is not yet a public support claim. For installation steps, supported
tool versions, and the complete local workflow, use the [User
Guide](USER_GUIDE.md) rather than duplicating that operational reference here.

The alpha makes no promise about long-term compatibility, production operation,
or security. Stable-core readiness depends on evidence outside this repository,
including package-index proof and feedback from a real downstream project.

## Canonical sources and refresh policy

Use the [public roadmap](https://github.com/sakibshuvo/Entroping/blob/main/ROADMAP.md)
for release sequence and public scope, the [project progress
dashboard](https://github.com/sakibshuvo/Entroping/blob/main/docs/meta/PROJECT_PROGRESS.md)
for the phase dashboard and stable-core evidence boundary, and [GitHub
Issues](https://github.com/sakibshuvo/Entroping/issues) for work items and their
current state.

This page is refreshed only when those canonical sources change the supported
alpha scope or its caveats. It intentionally does not copy issue identifiers,
counts, or transient statuses; follow the linked tracker for those details.
