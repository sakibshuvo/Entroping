---
title: Distribution Recommendation
type: decision
status: active
tags:
  - distribution
  - packaging
  - homebrew
  - binaries
  - uv
---

# Distribution Recommendation

## Problem

Entroping needs a lower-friction install path than source checkout while avoiding
release machinery that is expensive to operate before demand is proven.

## Options

| Path | Strength | Cost | Fit Now |
| --- | --- | --- | --- |
| `uv tool install` from Git or PyPI | Cross-platform, fast, Python-aware, already used in docs, can install/manage Python where needed | Requires users to install uv first; Hurl and Graphviz remain external tools | Best immediate path |
| Homebrew tap | Excellent macOS developer ergonomics, natural place to depend on Hurl and Graphviz | Formula maintenance, Python resource stanzas, bottle/tap maintenance, macOS-first | Good after PyPI alpha |
| standalone binary | Lowest apparent install friction for non-Python users | Build matrix, large artifacts, bundled Python/native dependencies, macOS signing, notarization, Windows signing, security update responsibility | Defer |

## Recommendation

Recommendation: uv first, PyPI next, Homebrew tap after PyPI, standalone later.

Keep the current public install path centered on:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha
```

After the package-index path is activated through
`docs/meta/PYPI_RELEASE_RUNBOOK.md`, prefer:

```bash
uv tool install entroping
```

Then prototype a Homebrew tap once PyPI/TestPyPI has proven package metadata,
entry points, and install smoke behavior. Defer standalone binaries until users
are asking for them or until enterprise/commercial packaging needs justify the
signing and support burden.

Cross-platform install claims are controlled by
[INSTALL_SMOKE_MATRIX.md](INSTALL_SMOKE_MATRIX.md). The current CI matrix proves
uv tool installation on Linux, macOS, and Windows, but Windows remains
doctor-only for Hurl until a Windows Hurl-backed execution path is reviewed.

Do not start with signing or notarization. That complexity should arrive only
after the simpler package-manager paths are already useful.

## Dependency Handling

### Python

`uv tool install` keeps Python installation and isolated tool environments out
of the Entroping repo. Homebrew formulas can install Python applications through
Homebrew Python and formula resources, but that adds formula maintenance work.
Standalone binaries bundle or compile against Python, which shifts interpreter
updates and CVE response onto the Entroping release process.

### Hurl

Hurl remains the deterministic execution dependency. For `uv tool install`,
users install Hurl separately and `entroping doctor` verifies it. A Homebrew tap
can depend on Hurl for macOS users. Standalone binaries should not bundle Hurl
until licensing, checksum, update, and platform-support rules are explicit.

### mitmproxy

`mitmproxy` is optional for `watch`. Keep it as an optional Python extra for
`uv tool install` and PyPI. Do not make it part of a default Homebrew formula
until proxy workflows are a core onboarding path. For standalone binaries,
mitmproxy increases artifact size and native dependency risk.

### Graphviz

Graphviz is optional for PNG dependency maps. For `uv tool install`, users
install Graphviz separately when they need PNG output. A Homebrew formula can
recommend or depend on Graphviz after the default UX is reviewed. Standalone
bundling should be deferred.

### Studio

Studio is optional and read-only. Keep Textual/Studio as an optional Python
extra. Do not let Studio force the default distribution to become heavier.

## What Not To Do Now

- Do not add a Homebrew formula in this issue.
- Do not add standalone binary automation in this issue.
- Do not add Nuitka or PyInstaller to the default dev dependencies yet.
- Do not add macOS signing, notarization, Windows signing, or installer
  automation before there is a release-owner runbook.
- Do not weaken the `uv tool install` and PyPI path to make other distribution
  channels seem necessary.

PyPI/TestPyPI path must land first.

## Standalone Binary Decision

Standalone binary decision: defer.

Do not add binary build/signing automation until after PyPI alpha and Homebrew tap demand are proven.
A standalone binary can look simpler to users, but it
would move Entroping from a Python CLI distribution problem into a
platform-release operation with signing keys, native dependency updates, and
security-response ownership.

Nuitka and PyInstaller remain the two plausible Python packaging candidates for
a later review. Neither should enter default development dependencies until a
release-owner runbook exists and the project has evidence that `uv tool
install`, PyPI, and Homebrew are not enough for the target users.

The later review must account for:

- macOS signing and notarization;
- Windows signing and installer reputation;
- Linux packaging targets, glibc/musl expectations, and artifact hosting;
- whether to bundle the Hurl binary or require users to install it separately;
- whether Graphviz remains optional or becomes an external dependency;
- whether mitmproxy optional proxy support makes artifacts too large or brittle;
- whether Studio/Textual remains optional or creates a heavier default binary;
- update cadence and CVE response for bundled Python and native dependencies.

Standalone binaries are worth revisiting only when at least one of these is
true:

- Homebrew users ask for a non-Homebrew path after the tap is proven;
- Linux or Windows users cannot adopt `uv tool install` or PyPI;
- an enterprise/commercial buyer requires signed offline artifacts;
- support evidence shows install friction is blocking real adoption.

## Follow-Up Implementation Issues

These follow-up implementation issues were created from this recommendation:

- [#223 packaging: activate PyPI/TestPyPI trusted publishing workflow](https://github.com/sakibshuvo/Entroping/issues/223)
- [#224 packaging: prototype Homebrew tap formula after PyPI alpha](https://github.com/sakibshuvo/Entroping/issues/224)
- [#225 packaging: evaluate standalone binary only after tap demand](https://github.com/sakibshuvo/Entroping/issues/225)

Order:

1. Activate the Trusted Publishing workflow after TestPyPI/PyPI environments are
   configured outside the repo.
2. Prototype the Homebrew tap from the stable package-index artifact path.
3. Revisit standalone binary packaging only after the first two paths show real
   adoption or commercial need.

## External Notes

- Homebrew can manage Python application formula resources, but maintaining
  resource stanzas is work the project should not take on before PyPI works.
- Homebrew can provide a strong macOS developer install path, but it does not
  solve Linux or Windows by itself.
- Nuitka and PyInstaller are still candidates for a later standalone binary
  review, but both move the project into platform-specific build and signing
  operations.
