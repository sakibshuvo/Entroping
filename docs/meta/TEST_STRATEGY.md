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

## Stable-Core Test Taxonomy

The suite intentionally includes runtime behavior tests, documentation
compliance tests, maintainer-script integrity tests, smoke checks, regression
guards, and security negative tests. Stable-core evidence must distinguish those
categories instead of treating the total test count as a single undifferentiated
quality claim.

Generate the machine-readable taxonomy with:

```bash
uv run python scripts/test_taxonomy.py --output reports/test-taxonomy.json --strict
```

The report uses schema `entroping.test-taxonomy.v1` and summarizes test files
plus static test definitions by category. The v1 schema additively records
whether each file/category attribution is `explicit`, `inferred`, or `mixed`,
along with the contributing pytest markers and filename rules:

- `behavior`: runtime, domain, adapter, and compiler behavior tests for product code.
- `docs-compliance`: public docs, roadmap, release evidence, and public-claim checks.
- `script-integrity`: maintainer scripts, CI helpers, and local automation checks.
- `integration`: cross-subsystem, installed CLI, and end-to-end local workflows.
- `smoke`: boot, demo, install, and fast confidence checks.
- `regression`: fragile behavior, compatibility promises, and fixed-bug guards.
- `security`: secrets, redaction, path handling, subprocess, and policy-risk tests.

`scripts/audit_quality.sh` writes `reports/test-taxonomy.json` before the
coverage, Radon, Vulture, quality-trend, and bounded performance smoke gates,
then uploads the report with the rest of the ignored quality artifacts in CI.
The taxonomy is file-level and deterministic; pytest markers improve
classification when present, but the script also uses stable file-name rules so
it can summarize the existing suite without mass marker churn. Strict mode
requires aggregate explicit marker evidence for the `integration`, `regression`,
and `security` categories; inference alone never satisfies them. Evidence counts
only final, statically collectable `test*`/`Test*` bindings under canonical
`pytest`. It does not execute imports or module code; the required pytest gates
decide live collection. Suppression, overwrites, inherited behavior, non-marker
decorators, invalid rows, and lookalike namespaces do not count. Other categories
may use inference.

For mechanical test-suite splits, generate a static collection manifest before
and after moving definitions:

```bash
uv run python scripts/pytest_collection_manifest.py \
  --output /absolute/host/evidence/collection-before.json \
  tests/test_original.py

uv run python scripts/pytest_collection_manifest.py \
  --output /absolute/host/evidence/collection-after.json \
  tests/test_split_one.py tests/test_split_two.py

uv run python scripts/pytest_collection_manifest.py \
  --compare \
  /absolute/host/evidence/collection-before.json \
  /absolute/host/evidence/collection-after.json
```

The `entroping.pytest-collection-manifest.v1` artifact uses a standard-library
AST reader to store a canonical multiset of module-normalized test IDs and
effective markers. It never imports or executes tests, conftest, plugins, or
pytest. Evidence covers supported syntax and unchanged imports only; run focused
pytest before and after a split.

`parameter_id_projection: normalized-away` keeps literal-row multiplicity and
static row marks while omitting values and ID suffixes; nested row values stay
opaque and explicit IDs are rejected. The allowlist requires canonical `pytest`
(including `cli_test_support`) and inert, statically provable annotations.
Dynamic collection, excessive expansion, metaprogramming, mutation, aliases,
constructors, duplicate bindings, hooks, plugins, and collection controls fail
closed. Reads use stable descriptor metadata and no-follow walks; final symlinks
are forbidden. Sources cap at 2 MiB, while generated and compared manifests
share an 8 MiB ceiling.

## Required Commands

Smallest no-Hurl CLI smoke for constrained agent sessions:

```bash
scripts/cli_smoke.sh
```

Use this when you only need to prove that the installed or development CLI
boots, reports a version, can initialize a minimal project, and can run
`doctor` without requiring Hurl. It is intentionally narrower than
`scripts/check.sh` and `scripts/feature_gate.sh`; it does not replace linting,
typing, unit coverage, security audits, or `scripts/live_demo_smoke.sh` for
runtime Hurl execution evidence.

Installed CLI plus real-Hurl E2E proof:

```bash
uv run pytest tests/test_cli_real_hurl_e2e.py -q
```

This integration test file skips cleanly when Hurl is unavailable. When Hurl is
installed, it starts a localhost-only demo API and drives `entroping init` plus
`entroping run` through the installed console script. It verifies JSON/JUnit
reports, QAnstitution gate injection evidence, failing assertion redaction,
timeout status mapping, run-event/report consistency, temporary execution
cleanup, and source `.hurl` immutability.

Fast feature gate:

```bash
scripts/feature_gate.sh
```

The feature gate starts with `scripts/repo_hygiene.sh`, which fails if local machine
state, runtime state, generated reports, graph output, virtualenvs, or tool caches
are tracked by Git. Repo hygiene also runs `scripts/ai_artifact_hygiene.py`, which
rejects committed AI worker artifacts, prompt or provider dumps, raw stdout/stderr
captures, cookies, raw traffic, and secret-shaped context in tracked docs/context
surfaces. The feature gate also runs `scripts/doc_governance_check.sh`,
`scripts/shell_quality.sh`, and `scripts/architecture_integrity.sh` before the
Python lint, type, and test gate. `scripts/shell_quality.sh` always runs
`bash -n` over tracked shell scripts and runs ShellCheck when `shellcheck` is
available; if ShellCheck is not installed, the skip is printed explicitly.
`scripts/architecture_integrity.sh` runs the focused AST import-boundary tests
that enforce hexagonal dependencies, provider boundaries, and deterministic
run-core isolation without calling providers, Hurl, the network, or secrets.

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
runs the test taxonomy report, the full test suite with a default 100 percent
coverage threshold, records ignored JSON audit artifacts under `reports/`, then
checks Radon complexity, Radon maintainability, and Vulture dead-code discovery.
It also writes `reports/quality-trend.json`, a deterministic trend summary that
captures coverage, complexity, maintainability, dead-code, and test-taxonomy
fields for comparison across runs; set `ENTROPING_QUALITY_TREND_PREVIOUS` to a
previous trend JSON path when a local audit should include numeric deltas.
The default Radon cyclomatic-complexity ceiling is rank D; any rank E or F block
must be refactored or explicitly justified before release-hardening claims.
The audit also writes `reports/script-quality-report.json` and compares the
release-critical in-process script subset against
`docs/meta/script-quality-ratchet-baseline.json` by default. This baseline
ratchets only scripts whose tests currently produce coverage evidence; the
subprocess-heavy release and factory scripts remain listed in the baseline as
deferred candidates until their tests can be observed by the script coverage
mode.

The separate script-maintainability gate measures every repository-owned Python
file under `scripts/`. It compares Radon weighted complexity, worst and
protected-rank counts, and 500-line hotspots with the input-only
`docs/meta/script-maintainability-ratchet-baseline.json`. Normal audits write
actionable evidence to the ignored
`reports/script-maintainability-ratchet.json`; they cannot rewrite the tracked
baseline or offset growth in one metric family with improvement in another.

Performance smoke:

```bash
uv run python scripts/performance_smoke.py
```

The performance smoke is a bounded audit-quality gate and scheduled/manual CI
evidence job. It uses a fake Hurl binary to avoid network calls while
exercising many Hurl files, bounded parallel runner behavior, gate injection,
JSON/JUnit/HTML report generation, and a larger SQLModel-backed traffic store
with retention. It writes reviewable evidence to
`reports/performance-smoke.json`, which stays ignored like other generated
reports. The scheduled workflow uploads the same JSON evidence for trend
review, but it does not satisfy package-index proof, downstream feedback, or
the stable-core compatibility decision by itself.

AI-regression proof:

```bash
scripts/ai_regression_demo.sh
```

This local proof starts the intentionally broken `examples/ai-regression-demo`
API and succeeds only when Entroping blocks the missing `X-Request-Id` response
header through QAnstitution and Hurl.

Policy-pack smoke proof:

```bash
uv run python scripts/policy_pack_smoke.py --strict
uv run python scripts/policy_pack_smoke.py --pack ./vendor/acme-strict-api --format json --strict
```

This local proof validates the example API-baseline policy pack through the
current local QAnstitution import mechanism, and it can validate arbitrary local
policy-pack directories supplied with `--pack`. It checks the provenance
manifest shape, local source metadata, attribution, supported Entroping range,
evidence command, manifest-declared gates, gate source files, final flags,
entrypoint, imported gates, documented final gates, and copyable consumer
example evidence without adding remote registries or pack-install behavior.
JSON output emits the reusable `policy-pack-verification` artifact for release,
issue, or external pack review.

Alpha launch-readiness proof:

```bash
uv run python scripts/launch_readiness.py --strict
scripts/demo_matrix.sh --dry-run
```

The launch-readiness script aggregates the public/demo/release/backlog evidence
needed for alpha launch review while still reporting stable-core blockers. The
demo matrix is a maintainer rehearsal wrapper for the checkout happy path,
AI-regression failure proof, policy-pack smoke, launch-readiness, and backlog
health commands; it does not replace the regression or security gates.

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

The quality-audit job also runs `uv run python scripts/performance_smoke.py`
through `scripts/audit_quality.sh`, so bounded large-suite, report, and traffic
store smoke evidence is PR-enforced without adding a flaky benchmark suite.

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
Proxy-stack security overrides in `pyproject.toml` must stay covered by this
lane and by the all-extras dependency audit so upstream transitive caps cannot
silently pin vulnerable runtime packages.

The `docs-site` job checks and builds the Astro/Starlight public site on pull
requests and pushes to `main`:

```bash
npm ci
npm run format:check
npm run check
npm run build
npm run test:site
```

Missing manifest sources, invalid content, broken generated links, and wrong
GitHub Pages base paths fail before the deployment workflow can publish from
`main`.

The separate `performance-smoke` workflow runs on a weekly schedule and by
manual dispatch only:

```bash
uv run python scripts/performance_smoke.py
```

It uploads `reports/performance-smoke.json` as additional workflow evidence for
trend review; the PR-enforced smoke is the bounded audit-quality invocation.

The documentation governance gate also runs:

```bash
python scripts/public_claims_audit.py
```

Unsupported public claims such as production readiness or guaranteed security
must fail before review.

Pull-request CI-enforced commands are `scripts/regression.sh --security`,
`scripts/audit_quality.sh`, the checked Astro/Starlight build, the
`install-smoke` matrix, and the `optional-extras-smoke` lane.
Scheduled/manual CI also runs the performance smoke. Because the regression gate
runs the feature gate, CI also runs shell syntax validation through
`scripts/shell_quality.sh`.

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
drift, effective-policy, structured diagnostics, and traceability reports. A
machine-readable report or local-evidence shape change should update the
serializer, JSON Schema file, compatibility note, and contract test in the same
pull request.
Structured diagnostics tests must prove the `entroping.diagnostics.v1`
value-free boundary: safe component names, statuses, counts, durations, and
relative artifact paths are allowed, while value-bearing fields such as raw
traffic, prompts, provider output, environment values, full source Hurl
contents, headers, bodies, cookies, and token-like values fail closed or are
redacted before JSONL serialization.

The quality-audit job uploads the generated `reports/` directory as workflow
artifacts for review. Packaging checks and release/live-demo release decisions
remain local release-owner gates through `scripts/release_check.sh`, because
they depend on the release context and whether local Hurl is installed.
`scripts/release_check.sh` also runs `uv run python scripts/performance_smoke.py`
unless `--skip-performance` is used for a local diagnostic pass. The release
check now runs `uv run python scripts/launch_readiness.py --strict` and
`uv run python scripts/stable_core_readiness.py --strict` so alpha launch and
stable-core evidence files and markers cannot silently disappear.
After `scripts/package_check.sh`, the release check also runs
`uv run python scripts/local_wheel_install_smoke.py --skip-build` so a locally
built wheel is installed into a fresh temporary venv, exercised through the
installed public CLI, and driven through the installed demo path when Hurl is
available. Missing Hurl is recorded as an explicit demo-skip without requiring
package-index access.
The release check also runs `uv run python scripts/downstream_smoke.py` when
Hurl is available, proving the local CLI can govern an external temporary
project from outside the repository. `--skip-downstream-smoke` is a diagnostic
escape hatch; release-candidate proof should keep the downstream smoke enabled.
The optional freshness command
`uv run python scripts/release_evidence.py --check-freshness --strict` is a
maintainer convenience for comparing the committed ledger with latest
successful GitHub Actions runs. It is intentionally outside the offline release
gate and does not mutate `docs/meta/release-evidence.json`.

## Coverage Expectations

- 100 percent meaningful coverage is the release bar and the default
  `scripts/audit_quality.sh` gate. Temporary lower thresholds must be explicit
  `ENTROPING_COVERAGE_FAIL_UNDER` overrides with tracked gaps.
- New pure logic needs unit tests.
- New CLI, filesystem, subprocess, YAML, report, proxy, or LLM behavior needs adapter tests.
- Bug fixes need regression tests when the bug is reproducible.
- Features crossing subsystem boundaries need integration or smoke coverage.
- Hurl runner work needs fixture `.hurl` files and real Hurl smoke checks once `hurl` is available.
- End-to-end governance evidence should include the installed console script,
  localhost-only API behavior, real Hurl execution, report validation, and
  source `.hurl` immutability when the toolchain is available.
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
