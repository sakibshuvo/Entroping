---
title: Test Strategy
type: runbook
status: active
tags:
  - testing
  - regression
  - tdd
  - coverage
---

# Test Strategy

Entroping uses a risk-based test pyramid. The release target is 100 percent
meaningful coverage, not decorative coverage; the goal is deterministic evidence
that the governance loop works.

## Test Pyramid

| Layer | Purpose | Examples |
| --- | --- | --- |
| Unit | Prove pure logic and schemas | QAnstitution models, condition parser, bridge compilers, gate matching |
| Adapter | Prove boundary behavior without live systems | CLI commands, filesystem writes, subprocess stubs, YAML loading, report writers |
| Integration | Prove multiple Entroping subsystems work together | policy load -> gate compile -> temp Hurl execution copy -> result model |
| Smoke | Prove installed CLI still boots | `entroping --help`, `entroping --version`, `entroping doctor` |
| Regression | Freeze bugs and risky behaviors | import-boundary drift, import cycles, redaction gaps, path traversal, source Hurl mutation |
| Security | Prove sensitive boundaries stay controlled | secret redaction, path handling, subprocess args, dependency audits |

## Required Commands

Fast feature gate:

```bash
scripts/feature_gate.sh
```

The feature gate starts with `scripts/repo_hygiene.sh`, which fails if local machine
state, runtime state, generated reports, graph output, virtualenvs, or tool caches
are tracked by Git.

Regression suite:

```bash
scripts/regression.sh
```

Security-sensitive work:

```bash
scripts/feature_gate.sh --security
scripts/regression.sh --security
```

The security feature gate also checks direct dependency license policy coverage:

```bash
uv run python scripts/dependency_license_check.py
```

Every declared direct runtime, optional, and development dependency must have a
reviewed entry in `docs/meta/dependency-license-policy.json` before it can land.

Validation or release-hardening audit:

```bash
scripts/audit_quality.sh
```

The quality audit is intentionally heavier than `scripts/regression.sh`. It
runs the full test suite with a default 100 percent coverage threshold, records
ignored JSON audit artifacts under `reports/`, then checks Radon complexity,
Radon maintainability, and Vulture dead-code discovery.

Performance smoke:

```bash
uv run python scripts/performance_smoke.py
```

The performance smoke is a local release-owner gate, not a pull-request CI
requirement. It uses a fake Hurl binary to avoid network calls while exercising
many Hurl files, bounded parallel runner behavior, gate injection, JSON/JUnit/HTML
report generation, and a larger SQLModel-backed traffic store with retention.
It writes reviewable evidence to `reports/performance-smoke.json`, which stays
ignored like other generated reports.

AI-regression proof:

```bash
scripts/ai_regression_demo.sh
```

This local proof starts the intentionally broken `examples/ai-regression-demo`
API and succeeds only when Entroping blocks the missing `X-Request-Id` response
header through QAnstitution and Hurl.

## GitHub Actions Enforcement

GitHub Actions enforces the same security-sensitive gate used for local release
proof:

```bash
scripts/regression.sh --security
```

The `checks` job runs that gate on Python 3.12 and Python 3.13. CI proves
Python 3.12 and 3.13 before the package metadata can claim support for those
runtimes. Python 3.12 remains the syntax and mypy floor, so static typing and
linting stay anchored to the lowest supported version; Entroping is not claimed
for Python 3.14 until a future compatibility issue adds CI evidence.

The CI workflow also runs the heavier quality audit as a separate job after the
security regression job:

```bash
scripts/audit_quality.sh
```

The `install-smoke` job proves the supported install path across operating
systems:

```text
Linux: uv tool install + pinned Hurl archive + doctor
macOS: uv tool install + Homebrew Hurl + doctor
Windows: uv tool install + doctor-only missing-Hurl guidance
```

The detailed support and non-claim matrix lives in
[INSTALL_SMOKE_MATRIX.md](INSTALL_SMOKE_MATRIX.md).

The `optional-extras-smoke` job installs all optional extras and exercises the
Brain/LiteLLM, Eye/mitmproxy, and Studio/Textual import/setup boundaries without
provider credentials or live traffic capture:

```bash
uv sync --dev --all-extras
uv run python scripts/optional_extras_smoke.py
```

That optional-extras smoke also runs on Python 3.12 and 3.13 so optional
dependency compatibility is part of the supported-version proof.

The `docs-site` job builds the public documentation with MkDocs strict mode on
pull requests and pushes to `main`:

```bash
uvx --with 'mkdocs-material==9.*' mkdocs build --strict
```

Broken public-docs links, invalid navigation entries, and MkDocs warnings fail
before the GitHub Pages deployment workflow can publish from `main`.

The documentation governance gate also runs:

```bash
python scripts/public_claims_audit.py
```

Unsupported public claims such as production readiness or guaranteed security
must fail before review.

CI-enforced commands are `scripts/regression.sh --security`,
`scripts/audit_quality.sh`, `uvx --with 'mkdocs-material==9.*' mkdocs build
--strict`, the `install-smoke` matrix, and the `optional-extras-smoke` lane.

Drift tests must keep response comparison value-free. The structured drift MVP
compares response status codes, selected stable headers, and JSON body shape
paths from sanitized run reports; it must not snapshot full bodies, cookies,
request IDs, dates, or other volatile values.
Latency drift tests compare only reviewed `duration_ms` fields from sanitized
run reports. They should keep conservative thresholds so tiny local timing
noise does not become a release-blocking regression.
Dependency-call drift tests compare only route identity from reviewed
dependency baselines: `destination_host`, `method`, and `path_template`.
They must not persist raw URLs, query values, headers, bodies, cookies, tokens,
call counts, or latency values as dependency drift truth.
Report schema contract tests freeze representative v1 JSON payloads for run,
drift, effective-policy, and traceability reports. A machine-readable report shape change should
update the serializer, JSON Schema file, compatibility note, and contract test in
the same pull request.

The quality-audit job uploads the generated `reports/` directory as workflow
artifacts for review. Packaging checks and release/live-demo release decisions
remain local release-owner gates through `scripts/release_check.sh`, because
they depend on the release context and whether local Hurl is installed.
`scripts/release_check.sh` also runs `uv run python scripts/performance_smoke.py`
unless `--skip-performance` is used for a local diagnostic pass. The release
check now runs `uv run python scripts/stable_core_readiness.py --strict` so
stable-core evidence files and markers cannot silently disappear.

## Coverage Expectations

- 100 percent meaningful coverage is the release bar and the default
  `scripts/audit_quality.sh` gate. Temporary lower thresholds must be explicit
  `ENTROPING_COVERAGE_FAIL_UNDER` overrides with tracked gaps.
- New pure logic needs unit tests.
- New CLI, filesystem, subprocess, YAML, report, proxy, or LLM behavior needs adapter tests.
- Bug fixes need regression tests when the bug is reproducible.
- Features crossing subsystem boundaries need integration or smoke coverage.
- Hurl runner work needs fixture `.hurl` files and real Hurl smoke checks once `hurl` is available.
- Security-sensitive behavior needs negative tests for unsafe input, redaction, or failure mode.
- Architecture-sensitive behavior needs import-boundary tests when a package boundary
  matters more than a single function result. `tests/test_architecture_boundaries.py`
  is the executable guard for hexagonal imports, deterministic run-core isolation,
  and LiteLLM-only provider access.
- Development-process guardrails need tests too. Script-level checks should have
  smoke or negative tests when they enforce behavior that agents might otherwise
  forget.

## Pytest Markers

Use these markers as the suite grows:

- `unit`: pure logic and schema tests.
- `adapter`: CLI, filesystem, subprocess, YAML, report, proxy, and LLM boundary tests.
- `integration`: cross-subsystem tests.
- `smoke`: boot and command-surface checks.
- `regression`: tests added for fixed bugs or fragile behavior.
- `security`: security-sensitive negative tests.

## Regression Suite Growth

Today `scripts/regression.sh` runs the feature gate plus CLI smoke checks. As the deterministic core lands, add:

1. QAnstitution import and merge fixtures.
2. Hurl discovery and metadata fixtures.
3. Gate injection fixtures proving source files are not mutated.
4. Hurl subprocess stubs and real Hurl smoke checks.
5. JSON/JUnit report fixtures.
6. Redaction tests for reports and future proxy capture.
7. Architecture/provider boundary tests for every new adapter family.

Keep the regression suite boring, deterministic, and local-first.
