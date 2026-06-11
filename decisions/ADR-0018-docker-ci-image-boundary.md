---
title: ADR-0018 Docker CI Image Boundary
type: decision
status: accepted
date: 2026-06-11
tags:
  - decision
  - docker
  - docker-ci-image
  - distribution
  - ci
---

# ADR-0018: Docker CI Image Boundary

## Decision

Entroping should defer an official Docker CI image until package-index proof
exists. The current distribution sequence remains:

```text
uv/source -> TestPyPI/PyPI -> Homebrew/action/Docker prototypes -> broader packaging
```

When implemented, the image should be a CI convenience published to GHCR as
`ghcr.io/sakibshuvo/entroping-ci`. It should include pinned Entroping, Hurl, and
hurlfmt versions, run as a non-root user, expose OCI labels, support immutable
release tags and digest pinning, and pass image-level smoke checks before any
moving tag is promoted.

The detailed image contract lives in
[`docs/meta/DISTRIBUTION_RECOMMENDATION.md`](../docs/meta/DISTRIBUTION_RECOMMENDATION.md).
It requires OCI labels for source repository, revision, license, created
timestamp, package version, Hurl version, and image description. Its rollback
policy forbids mutating a broken immutable release tag; publish a fixed patch
tag or deprecate the image metadata, then move only mutable tags after the
replacement smoke passes.

Docker must not become the only supported path for local users or CI users.

## Rationale

A Docker image can improve repeatability for Linux CI jobs, but it also adds a
registry, base-image patching, provenance, tagging, rollback, and support
surface. Shipping it before TestPyPI/PyPI proof would make a larger artifact
responsible for hiding an unproven package install path.

Deferring Docker keeps the project focused on the simpler package-index path
first while preserving a clear future contract for CI users who want a
preinstalled toolchain.

## Consequences

- No Dockerfile, image-publish workflow, or GHCR claim is added yet.
- CI docs may describe the future image boundary, but must state that it is not
  supported today.
- The image can temporarily use tagged GitHub release artifacts only for
  prerelease prototypes; public support should install released package-index
  artifacts.
- Image promotion requires smoke checks for Entroping, Hurl, hurlfmt, and a
  minimal no-provider Entroping project.
