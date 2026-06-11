# Changelog

Public release history for Entroping.

This file is intentionally concise and user-facing. Detailed implementation
handoff history lives in `.context/changelog.md`; stable-core evidence and
release-gate proof live in `docs/meta/RELEASE_EVIDENCE.md`.

## Notable unreleased changes

- Added an explicit `entroping report policy-diff --fail-on-change` CI mode for
  effective-policy drift gates while preserving default review-report behavior.
- Extracted `entroping run` option validation into direct-tested core helpers
  without changing the locked CLI surface.
- Added scheduled performance-smoke evidence for large-suite and report-size
  checks without making timing-sensitive work part of every pull request.

## v0.1.1-alpha - 2026-05-31

Source-distributed GitHub prerelease.

- Public cleanup release for first-time open-source visitors.
- README, roadmap, release checklist, public docs, community profile, and
  quality/security gates were aligned around the alpha boundary.
- Release evidence: `scripts/release_check.sh --require-live-demo`.
- Boundary: alpha release evidence only; not package-index proof and not
  stable-core proof.

## v0.1.0-alpha - 2026-05-30

First source-distributed GitHub prerelease.

- Established the public alpha release path and deterministic release gate.
- Published with explicit early-alpha boundaries.

## v0.1.2-alpha-rc.1 - 2026-06-01

Local release-candidate rehearsal, not a public package-index release.

- Rehearsed the alpha release gate with recorded local evidence.
- Boundary: release-candidate evidence only; not stable-core proof, not
  package-index proof, and not real downstream user feedback.
