---
title: Install Smoke Matrix
description: "Compare the operating-system install paths that CI proves with the manual evidence still required."
type: runbook
status: active
tags:
  - install
  - ci
  - release
  - cross-platform
---

# Install Smoke Matrix

This matrix defines the operating-system setup that Entroping currently proves.
It keeps public install claims aligned with CI and manual release evidence.

## CI Matrix

The `install-smoke` job in `.github/workflows/ci.yml` runs after the main
`checks` job and installs Entroping as a local uv tool from the checked-out
repository:

```bash
uv tool install . --force
```

Then each platform runs:

```bash
entroping --version
entroping init --minimal
entroping doctor
```

| OS | Shell | Hurl mode | What is proved |
| --- | --- | --- | --- |
| `ubuntu-latest` | Bash | pinned Hurl archive | uv tool install, console script, Hurl discovery, minimal init, and doctor health on Linux |
| `macos-latest` | Bash via GitHub Actions | Homebrew Hurl | uv tool install, console script, Hurl discovery, minimal init, and doctor health on macOS |
| `windows-latest` | PowerShell | doctor-only | uv tool install, Windows console script, minimal init, and doctor missing-Hurl guidance |

Windows Hurl-backed `entroping run` is not claimed for alpha. The alpha claim is
that the Python CLI installs and starts on Windows, and that `doctor` gives a
clear Hurl dependency message. A future issue must review a Windows Hurl install
path before Entroping claims Hurl-backed Windows execution.

`windows-latest` is a moving GitHub-hosted runner alias. GitHub image migration notices
should be treated as install-smoke evidence review prompts, not as a reason to
expand Windows support claims. Pin a Windows image only if the doctor-only smoke
becomes image-sensitive or a release claim depends on a specific Windows
version.

## Dependency Rules

- Hurl is required for deterministic `entroping run`.
- `hurlfmt` is required for Architect generated-Hurl validation. Most Hurl
  package installs include it, but `entroping doctor` reports it separately so
  users can catch parser-validation gaps before AI-backed generation/refactor
  workflows fail.
- Linux CI installs a reviewed pinned Hurl archive and verifies `HURL_SHA256`.
- macOS CI installs Hurl through Homebrew.
- Windows CI intentionally stays doctor-only until the Hurl install path is
  reviewed.
- Optional extras are not part of `install-smoke`; they are covered by the
  `optional-extras-smoke` job.
- Graphviz remains optional and is not required for the install smoke.
- mitmproxy and Textual remain optional extras and are not required for the base
  CLI install.

## Manual Evidence

Before a release or stable-core support claim, compare:

1. The latest passing `install-smoke` CI matrix.
2. The latest passing `optional-extras-smoke` CI job.
3. The latest passing `live-demo-smoke` CI job.
4. Local release-owner evidence:

```bash
scripts/release_check.sh --require-live-demo
uv run python scripts/performance_smoke.py
```

Do not claim a platform until either CI or a documented manual run proves the
same command path.

## Non-Claims

The current alpha does not claim:

- Windows Hurl-backed `entroping run`.
- Windows proxy capture through mitmproxy.
- Homebrew tap installation.
- PyPI/TestPyPI installation.
- standalone binary installation.
- Graphviz PNG rendering on every platform.

These remain follow-up distribution phases, not current support claims.
