---
title: Alpha Release Checklist
type: runbook
status: active
tags:
  - release
  - alpha
  - quality
  - security
---

# Alpha Release Checklist

This checklist defines the release bar for the current alpha tag. It is intentionally stricter than the daily feature gate because the public alpha should prove the deterministic governance loop, not only compile.

## Release Claim

The current alpha may claim:

- Local-first Hurl-native API governance.
- QAnstitution policy loading, validation, matching, and gate injection.
- Deterministic Hurl execution through subprocess boundaries.
- JSON, JUnit, HTML, and bug-report handoff artifacts.
- OpenAPI-to-Hurl generation for the checkout demo and common request shapes.
- Prompt-backed Architect build/refactor foundations with parser-backed Hurl validation.
- Capture-only traffic observation, Hurl freeze generation, WireMock mock export, and Mermaid/DOT/Markdown dependency maps from redacted traffic.
- Optional Graphviz-backed PNG dependency map export from redacted traffic.
- CI proof through the live checkout demo smoke.

## Required Evidence

Run the release gate from a clean checkout:

```bash
scripts/release_check.sh --require-live-demo
```

This gate includes:

- `scripts/repo_hygiene.sh`
- `uv run python scripts/policy_pack_smoke.py --strict`
- `uv run python scripts/launch_readiness.py --strict`
- `uv run python scripts/stable_core_readiness.py --strict`
- `uv run python scripts/release_evidence.py --strict`
- `scripts/package_check.sh`
- `uv run python scripts/local_wheel_install_smoke.py --skip-build`
- `scripts/regression.sh --security`
- `uv run python scripts/performance_smoke.py`
- `uv run python scripts/downstream_smoke.py`
- `scripts/live_demo_smoke.sh`

If the local machine does not have Hurl installed, the non-release diagnostic form is:

```bash
scripts/release_check.sh
```

That still runs hygiene, package verification, and `scripts/regression.sh --security`, but skips the live demo unless Hurl is available.

The security regression path includes the direct dependency license policy gate.
Review `docs/meta/dependency-license-policy.json` whenever `pyproject.toml`
adds, removes, or changes direct dependencies.

Package artifacts are verified locally before any publish. The package gate
removes `dist/`, runs `uv build`, and inspects the wheel and source
distribution for the expected name, version, SPDX `License-Expression`, license
file metadata, alpha classifier, and root release files. Package-index upload is
manual through `.github/workflows/publish-python-package.yml` and protected
`testpypi`/`pypi` environments.

The local wheel install smoke reuses the built wheel, creates a temporary
virtual environment and temporary project outside the repository, installs the
wheel with `uv pip install --offline`, then runs only public installed CLI
commands: `entroping --version`, `entroping init --minimal`, and
`entroping doctor`. It emits machine-readable evidence and does not require
PyPI, TestPyPI, registry credentials, or committed `dist/` artifacts.

The downstream smoke creates a separate temporary API project, starts a local
fixture server, and runs Entroping through the public CLI from that external
project. The release gate skips it when Hurl is unavailable unless
`--require-live-demo` is used, and `--skip-downstream-smoke` is available for
local diagnostics. This is maintainer-controlled smoke evidence; it still does
not satisfy real downstream user feedback.

## CI Evidence

Before tagging, the latest `main` commit must have passing GitHub Actions jobs:

- `checks` on Python 3.12 and Python 3.13
- `install-smoke`
- `live-demo-smoke`
- `optional-extras-smoke` on Python 3.12 and Python 3.13
- `quality-audit`

CI proves Python 3.12 and 3.13 for the security regression suite and optional
extras smoke before release. Python 3.12 remains the syntax and mypy floor, and
the package is not claimed for Python 3.14 until CI evidence is added.

The `live-demo-smoke` job installs a pinned Hurl binary, verifies the archive
against the reviewed `HURL_SHA256` value in `.github/workflows/ci.yml`,
generates Hurl from the checkout OpenAPI fixture, runs the deterministic
Enforcer path, and uploads run reports.

When bumping Hurl:

1. Update `.github/workflows/ci.yml` `HURL_VERSION`.
2. Download the matching Linux archive from the Hurl release page.
3. Compute and review the checksum locally:

   ```bash
   sha256sum hurl-<version>-x86_64-unknown-linux-gnu.tar.gz
   ```

4. Update `.github/workflows/ci.yml` `HURL_SHA256` in the same review.
5. Let the `live-demo-smoke` job prove the pinned checksum and demo path.

## Manual Review

Before tagging:

- Review `git status --short` and confirm the worktree is clean.
- Review `git log -1 --oneline` and confirm the intended release commit.
- Review `README.md` for accurate current status.
- Review `docs/meta/PROJECT_PROGRESS.md` for phase-level status.
- Review `docs/technical/THREAT_MODEL.md` before any stable-core security
  posture claim.
- Review `docs/technical/CLI_COMPATIBILITY_AUDIT.md` before any stable-core
  command, flag, exit-code, or report-artifact claim.
- Review `docs/technical/PYTHON_COMPATIBILITY.md` before any supported-runtime
  claim.
- Review `docs/meta/RELEASE_EVIDENCE.md` and run
  `uv run python scripts/release_evidence.py --strict` before any repeated
  release, package-index, or stable-core evidence claim.
- Run `uv run python scripts/release_evidence.py --check-freshness --strict`
  when a release or stable-core claim depends on the latest successful `main`
  CI and Pages runs. This optional GitHub CLI check is read-only, degrades when
  `gh` is unavailable or unauthenticated, and never updates the committed
  ledger automatically.
- Review the `scripts/stable_core_readiness.py --format json` output before any
  v1 or stable-core claim.
- Run `scripts/demo_matrix.sh --dry-run` before launch copy review to inspect
  the checkout happy path, AI-regression failure proof, policy-pack smoke,
  launch-readiness, and backlog-health commands from one place.
- Run `uv run python scripts/policy_pack_smoke.py --strict` before making
  policy-pack import claims.
- Run `scripts/ai_regression_demo.sh` when launch messaging needs a concrete
  failure proof instead of only the happy-path checkout demo.
- Confirm the `optional-extras-smoke` CI lane is passing before making claims
  about Brain/LiteLLM, Eye/mitmproxy, or Studio/Textual optional surfaces.
- Confirm the `install-smoke` CI matrix is passing before making Linux, macOS,
  or Windows install claims. Windows Hurl-backed `entroping run` is not claimed
  for alpha; see [INSTALL_SMOKE_MATRIX.md](INSTALL_SMOKE_MATRIX.md).
- Review `reports/performance-smoke.json` from
  `uv run python scripts/performance_smoke.py` before making stable-core
  scalability claims.
- Confirm no secrets, local env files, `.entroping/`, generated reports, Graphify output, or Obsidian UI state are tracked.
- Confirm public Markdown passes `python scripts/public_claims_audit.py` before
  publishing release notes, launch copy, or README changes.
- Confirm `watch` is described as capture-only, `freeze` is described as Hurl/mock generation from redacted traffic, `map` is described as Mermaid/DOT/Markdown/PNG export with optional Graphviz, and `studio` is clearly presented as an interactive read-only TUI rather than a mutation workflow.

## Not Built Yet

Do not imply these are complete in release notes:

- Studio mutation workflows such as editing tests, rerunning suites, or changing config.
- hosted cloud workflows.
- enterprise policy approval workflows.

## Tagging Steps

Only after required evidence passes:

```bash
git tag -a v0.1.1-alpha -m "Entroping v0.1.1-alpha"
git push origin v0.1.1-alpha
```

Then create a GitHub release with:

- A short alpha positioning statement.
- The exact verification commands and CI run link.
- The implemented command list.
- The "Not Built Yet" section above.
- A pointer to the next milestone from `ROADMAP.md`.
- Optional manually attached wheel and sdist artifacts built by
  `scripts/package_check.sh`.

Do not add PyPI/TestPyPI tokens, release signing keys, or package-index
credentials to the repository. Package-index publishing is planned through the
TestPyPI-first Trusted Publishing runbook in
`docs/meta/PYPI_RELEASE_RUNBOOK.md`, not through long-lived repository secrets.
