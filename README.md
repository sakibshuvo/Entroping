---
title: Entroping
type: index
status: active
tags:
  - entroping
  - readme
  - quality-governance
---

# Entroping

**Code at the speed of AI. Don't crash at the speed of AI.**

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/sakibshuvo/Entroping/badge)](https://scorecard.dev/viewer/?uri=github.com/sakibshuvo/Entroping)

Entroping is a local-first runtime governance layer for AI-assisted backend
development. Let agents generate code, propose tests, and refactor APIs; keep
the merge decision deterministic with Hurl, executable policy gates, and
CI-ready reports.

The core rule is simple: **AI can suggest. Runtime truth decides.**

Project philosophy: **The QAnstitution is Law. Traffic is Truth. Hurl is the Enforcer.**

**Start here:** [Public Docs](https://sakibshuvo.github.io/Entroping/) ·
[Two-Minute Demo](#try-it-in-two-minutes) · [Roadmap](ROADMAP.md) ·
[Project Context](#project-context)

## Why Entroping

AI can now ship backend changes faster than humans can fully review them. The
hard failures rarely show up in static review: wrong status codes, broken auth,
schema drift, undocumented dependencies, slow endpoints, and "looks fine" code
that quietly breaks production behavior.

Entroping gives that workflow a hard guardrail:

- **QAnstitution is Law:** define security, latency, schema, and ownership rules once.
- **Traffic is Truth:** capture real HTTP behavior and freeze it into regression coverage.
- **Hurl is the Enforcer:** execute committed `.hurl` tests through a deterministic Rust binary.
- **CI stays LLM-free:** generation can use AI, but `entroping run` is reproducible.

## Use Entroping When

- **AI changed your API:** prove runtime behavior still passes committed Hurl tests before merge.
- **Your spec exists but tests do not:** generate reviewable Hurl coverage from OpenAPI.
- **Legacy behavior is undocumented:** watch real traffic, redact it, and freeze regression tests or mocks.
- **Rules should apply everywhere:** enforce status, latency, headers, and policy-pack gates through `qanstitution.yaml`.
- **PRs need evidence:** emit JSON, JUnit, HTML, drift, delta, traceability, and GitHub annotations.

## Try It In Two Minutes

Clone the repo, install `uv` and Hurl, and run the checkout demo:

```bash
git clone https://github.com/sakibshuvo/Entroping.git
cd Entroping
brew install uv hurl # macOS; use your package manager elsewhere
scripts/demo.sh
```

Expected proof:

```text
Hurl run: 4 passed, 0 failed
Wrote report: reports/run-latest.json
Wrote report: reports/junit.xml
Wrote report: reports/run-latest.html
```

`scripts/demo.sh` is the friendly checkout entrypoint. It delegates to the
same deterministic `scripts/live_demo_smoke.sh` release gate used by CI and
launch-asset rebuilds.

Animated previews show the happy path and the failure path:

![Checkout demo: Hurl run passes and reports are emitted](docs/assets/launch/checkout-demo.gif)

![AI regression proof: QAnstitution blocks a missing request-id header](docs/assets/launch/ai-regression-proof.gif)

For public launch previews, use the
[Two-Minute Demo Assets](docs/assets/launch/README.md):

- [Terminal demo screenshot](docs/assets/launch/terminal-demo-screenshot.png)
  from the same live smoke path used by `scripts/demo.sh`.
- [HTML report screenshot](docs/assets/launch/html-report-screenshot.png)
  captured from `reports/run-latest.html`.
- [Dependency map screenshot](docs/assets/launch/dependency-map-screenshot.png)
  generated from redacted traffic state.

## Security Policy Pack Wedge

The [OWASP API Top 10 starter policy pack](examples/policy-packs/owasp-api-top-10/README.md)
is the quickest way to see Entroping as runtime governance instead of generic
test generation. Vendor the pack, import its `qanstitution.yaml`, and use Hurl
evidence to catch missing auth, missing request ID headers, server-error
regressions, and latency budget breaches before merge.

This is an OWASP API Security Top 10-inspired starter pack. It is not official
OWASP endorsement, not complete compliance, and not certification evidence.

## What You Get

Entroping is not another AI chat wrapper. It is an execution boundary for API
quality:

- Turn OpenAPI specs into reviewable Hurl regression tests, including
  supported auth-negative coverage from declared security schemes.
- Inject global QAnstitution gates into every run without mutating source tests.
- Capture and redact live traffic, then freeze flows or dependency mocks.
- Emit JSON, JUnit, HTML, drift, delta, badge, SARIF, bug, retry/flake, and traceability evidence for local review and CI.
- Bundle Builder, Breaker, and Auditor run evidence from sanitized local manifests before human review.

```mermaid
flowchart LR
  Intent["Specs, stories, prompts"] --> Architect["Architect: build/refactor/audit"]
  Traffic["Live HTTP traffic"] --> Eye["Eye: watch/freeze/map"]
  Architect --> Tests["Hurl tests"]
  Eye --> Tests
  Law["qanstitution.yaml"] --> Enforcer["Enforcer: entroping run"]
  Tests --> Enforcer
  Enforcer --> Reports["Reports: JSON, JUnit, HTML, drift, delta, badges, SARIF"]
  Reports --> CI["Local dev and CI gates"]
```

## Current Alpha

This repository is the active alpha implementation for Entroping.

Public roadmap: [ROADMAP.md](ROADMAP.md) and
[GitHub Project board](https://github.com/users/sakibshuvo/projects/1).

Built today:

- Locked v4.1 CLI surface for `init`, `doctor`, `config`, `architect`, `watch`,
  `freeze`, `map`, `run`, `studio`, and `report`.
- QAnstitution loading with safe local imports, typed condition validation,
  duplicate gate checks, and final imported gate protection.
- Hurl discovery, metadata parsing, tag filters, gate matching, temporary
  execution-copy injection, subprocess timeouts, output redaction, and bounded
  parallel execution.
- JSON, JUnit, HTML, drift, delta, Shields-compatible badge, SARIF, bug, and traceability reporting.
- Deterministic OpenAPI-to-Hurl generation plus Architect prompt build,
  merge, refactor, audit, persona loading, LiteLLM routing, structured output
  parsing, and pre-write Hurl validation.
- Eye capture/freeze/map foundation with mitmproxy capture, SQLModel-backed
  SQLite state, redaction before persistence, generated Hurl flows, optional
  dependency export artifacts, and Mermaid/DOT/Markdown/PNG dependency maps.
- Local and CI quality gates through `uv`, `ruff`, `mypy`, `pytest`, coverage,
  package verification, security checks, optional-extras smoke, live demo smoke,
  and quality audit.

Still alpha:

- Dependency-call drift is route-level only: host, method, and templated path,
  with no raw traffic values.
- Architect validation guidance is improved, but the broader UX is intentionally narrow.
- The optional local inspector is read-only, including applied-gate drilldowns
  over existing reports; future mutation workflows must follow
  [STUDIO_MUTATION_WORKFLOW_DESIGN.md](docs/technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md).

## Install

The alpha is source-distributed first. PyPI, Homebrew, and standalone binaries
are later distribution tracks.

Install from the latest GitHub branch:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git
```

Install from the alpha tag:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha
```

For local development in a checkout:

```bash
uv tool install -e .
```

Optional shell completion comes from Typer's existing global options:

```bash
entroping --install-completion
entroping --show-completion
```

This is a Typer global option, not an Entroping subcommand, so it does not
change the locked CLI namespace.

Requirements:

- Python 3.12 or 3.13
- [`uv`](https://docs.astral.sh/uv/)
- [`hurl`](https://hurl.dev/) for deterministic execution and the live demo
  (`brew install hurl` on macOS, or use the
  [official Hurl install guide](https://hurl.dev/docs/installation.html))
- Optional extras: `mitmproxy` for `watch`, LiteLLM providers for prompt-backed Architect work, Graphviz for PNG maps
  ([AI_PROVIDER_SETUP.md](docs/user/AI_PROVIDER_SETUP.md) covers LiteLLM,
  local Qwen/oMLX, and no-provider CI)

CI proves Python 3.12 and 3.13 for the security regression suite and optional
extras smoke. Python 3.12 remains the syntax and mypy floor; Entroping is not
claimed for Python 3.14 until CI evidence is added.

## Use The CLI

Create a minimal local project:

```bash
entroping init --minimal
entroping doctor
```

To also install the reviewed GitHub Actions starter workflow, run
`entroping init --github-actions` or
`entroping init --minimal --github-actions`. Entroping writes
`.github/workflows/entroping.yml` and refuses to overwrite an existing
workflow.

For automation, use `entroping doctor --output json` to get versioned setup
health without scraping human output.
Before wiring a PR gate, run `entroping doctor --ci` or
`entroping doctor --ci --output json` to validate Hurl availability, safe local
artifact paths, suite manifests, required Hurl variables, and the provider-free
`run --ci` boundary.

The starter policy is intentionally small: status, latency, and request-ID
header gates. See [QANSTITUTION_FIRST_HOUR.md](docs/user/QANSTITUTION_FIRST_HOUR.md)
before jumping into the full reference.

Editor autocomplete is already wired for `qanstitution.yaml`: Entroping ships
[docs/technical/qanstitution.schema.json](docs/technical/qanstitution.schema.json),
and [QANSTITUTION_REFERENCE.md](docs/technical/QANSTITUTION_REFERENCE.md) shows
the VS Code / YAML language server mapping. The schema catches authoring shape
mistakes early; `entroping doctor` remains the authoritative runtime validation.

Generate tests from OpenAPI:

```bash
entroping architect build --new --tag smoke
```

During feature work, generate only operations changed from a Git base ref:

```bash
entroping architect build --new --changed-from origin/main --tag smoke
```

Run deterministic tests and reports:

```bash
entroping run --env local --tag smoke --report json --report junit --report html
```

Capture and freeze legacy behavior:

```bash
entroping watch --target http://localhost:3000
entroping freeze --name checkout_flow --golden --dry-run
entroping freeze --name checkout_flow --golden
entroping map --export mermaid --include-host api.example.test
```

Route AI generation without putting the LLM in CI:

```bash
entroping config set --agent builder --model openai/gpt-4.1-mini
entroping architect build --prompt "Generate checkout smoke coverage" --tag ai
entroping config set --agent breaker --model deepseek/deepseek-r1
entroping architect build --agent breaker --prompt "Generate hostile auth and IDOR tests" --tag security
```

## Develop Locally

Install dependencies:

```bash
uv sync --dev
```

Run the normal regression gate:

```bash
scripts/regression.sh
```

Run security-sensitive gates:

```bash
scripts/feature_gate.sh --security
scripts/regression.sh --security
```

CI enforces `scripts/regression.sh --security` for pull requests and pushes to
`main`. CI enforces `scripts/audit_quality.sh` as a separate quality-audit job,
runs `install-smoke` across Linux, macOS, and Windows, and runs
`optional-extras-smoke` with all optional dependencies installed so
AI-provider, proxy, and local-inspector extras boot without provider credentials
or live traffic capture. The quality-audit job uploads generated reports as
workflow artifacts.

Local-only before release:

```bash
scripts/package_check.sh
uv run python scripts/performance_smoke.py
scripts/release_check.sh --dry-run --require-live-demo
scripts/release_check.sh --require-live-demo
```

Release-owner checklists, package-index publishing, install-channel sequencing,
and agent handoff are backstage maintainer context linked below.

## Project Context

Public Docs are the adoption path. Maintainer and agent context is backstage and
not required for first use.

- Public path: [Public Docs](https://sakibshuvo.github.io/Entroping/),
  [USER_GUIDE.md](docs/user/USER_GUIDE.md),
  [QANSTITUTION_FIRST_HOUR.md](docs/user/QANSTITUTION_FIRST_HOUR.md), and
  [USE_CASES.md](docs/user/USE_CASES.md). Provider setup lives in
  [AI_PROVIDER_SETUP.md](docs/user/AI_PROVIDER_SETUP.md).
- GitHub Issues track work; [ROADMAP.md](ROADMAP.md) sequences releases, and
  [PROJECT_PROGRESS.md](docs/meta/PROJECT_PROGRESS.md) keeps the short daily
  dashboard.
- Obsidian is project memory, not the backlog. Open the vault at
  [Vault Index](docs/meta/VAULT_INDEX.md), and use [DOCS_GOVERNANCE.md](docs/meta/DOCS_GOVERNANCE.md);
  `docs/meta/DOCS_GOVERNANCE.md` decides which docs must change.
- Agent handoff uses `scripts/start_issue.sh <issue-number> <branch>`,
  `scripts/context_pack.sh --mode implementation`, `--mode review`,
  `--mode source`, `--mode growth`, and `--mode handoff`.
- Architecture and command reference live in [TDS.md](docs/technical/TDS.md),
  [QANSTITUTION_REFERENCE.md](docs/technical/QANSTITUTION_REFERENCE.md),
  [COMMAND_CHEAT_SHEET.md](docs/technical/COMMAND_CHEAT_SHEET.md),
  [CLI_COMPATIBILITY_AUDIT.md](docs/technical/CLI_COMPATIBILITY_AUDIT.md),
  [POLICY_PACK_LAYOUT.md](docs/technical/POLICY_PACK_LAYOUT.md), and
  [THREAT_MODEL.md](docs/technical/THREAT_MODEL.md).
- Release and distribution evidence lives in
  [RELEASE_CHECKLIST.md](docs/meta/RELEASE_CHECKLIST.md),
  [PYPI_RELEASE_RUNBOOK.md](docs/meta/PYPI_RELEASE_RUNBOOK.md),
  [INSTALL_SMOKE_MATRIX.md](docs/meta/INSTALL_SMOKE_MATRIX.md),
  [DISTRIBUTION_RECOMMENDATION.md](docs/meta/DISTRIBUTION_RECOMMENDATION.md),
  [GITHUB_ACTIONS_STARTER.md](docs/user/GITHUB_ACTIONS_STARTER.md), and
  [CI_PROVIDER_RECIPES.md](docs/user/CI_PROVIDER_RECIPES.md).
- Launch copy starts with REST/OpenAPI + QAnstitution + Hurl + CI reports;
  advanced examples remain documented, but they are not the first public story.
- Growth, open-core, and examples are in
  [GROWTH_AND_MONETIZATION.md](docs/product/GROWTH_AND_MONETIZATION.md),
  [OPEN_CORE_BOUNDARIES.md](docs/product/OPEN_CORE_BOUNDARIES.md),
  [examples/checkout-api](examples/checkout-api/README.md),
  [examples/support-api](examples/support-api/README.md),
  [examples/ai-regression-demo](examples/ai-regression-demo/README.md).

The public docs site is generated by `mkdocs.yml`; CI runs a strict docs build
on pull requests, and GitHub Pages publishes `main` to
[sakibshuvo.github.io/Entroping](https://sakibshuvo.github.io/Entroping/).

## Locked Alpha CLI Surface

Compatibility details live in [CLI_COMPATIBILITY_AUDIT.md](docs/technical/CLI_COMPATIBILITY_AUDIT.md).

```text
entroping init [--minimal] [--github-actions]
entroping doctor [--ci] [--output <text|json>]
entroping config list
entroping config set --agent <builder|auditor|breaker> --model <model-id>
entroping config vendor-policy-pack --pack <path> [--name <dir>]
entroping config test-policy-pack --pack <path> [--output <text|json>]

entroping architect build [--new] [--changed-from <ref>] [--prompt <text>] [--strategy merge] [--tag <tag>] [--agent <builder|breaker>]
entroping architect refactor --target <glob> --prompt <text> [--preview]
entroping architect audit [--focus <logic|auditor>] [--output <json|md>] [--changed-from <ref>]

entroping watch [--port <port>] [--target <url>] [--scope-host <host> ...] [--scope-url-prefix <url> ...]
entroping freeze --name <flow> [--golden] [--mock <service>] [--dry-run] [capture filters]
entroping map [--export <mermaid|dot|md|png>] [capture filters]

entroping studio [--env <name>]
entroping run [--env <name>] [--suite <name>] [--tag <tag>] [--tag-expression <expr>] [--operation-id <id>] [--ci] [--parallel] [--fail-fast] [--report <html|junit|json|drift> ...] [--drift-check] [--changed-from <ref>] [--rerun-failures]
entroping report bug
entroping report failure-bundle [--output <directory>]
entroping report delta [--base <path>] [--current <path>] [--output <md|json>]
entroping report badges [--output <directory>] [--run-json <path>] [--policy-json <path>] [--openapi-json <path>] [--traceability-json <path>]
entroping report redaction [--output <md|html>]
entroping report policy [--output <md|json>]
entroping report gate-coverage [--output <md|json>]
entroping report gate-injection --target <path> [--output <md|json>]
entroping report artifact-manifest [--output <path>]
entroping report agent-bundle [--output <md|json>] [--role <builder|auditor|breaker>] [--scope <path>]
entroping report traceability [--output <md|json>]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
entroping report sarif [--output <path>] [--junit <path>] [--drift <path>] [--traceability]
entroping report promote-drift-baseline [--candidate <path>] [--output <path>]
entroping report review-summary [--output md] [--junit <path>] [--run-json <path>] [--drift <path>] [--traceability]
```

`architect audit --focus logic` is deterministic: it compares the configured
OpenAPI document with committed Hurl metadata, reports uncovered operations,
and includes an operation-to-test matrix with stale `operation_id` references.
When redacted Eye traffic exists, it also flags captured routes that are not in
the OpenAPI contract without printing raw query strings, headers, cookies,
bodies, or captured values. Add `--changed-from <ref>` to compare the configured
local OpenAPI spec with the same file at a Git base ref and report deterministic
operation, status, required-input, and response-shape changes without generating
or deleting tests.

`entroping studio --env local` is a read-only traffic session browser as well
as a local run/status view. The Traffic tab reads redacted SQLModel-backed state
from `.entroping/state.db`, shows inferred target/dependency grouping, route
counts, latency summaries, and safe redaction categories and counts. It does not
start `watch`, run Hurl, write config, or render raw URLs with query values,
headers, bodies, cookies, tokens, or secrets.

Deprecated names such as `gen`, `fix`, `scan`, `chaos`, and `report --type`
are intentionally not primary commands.

## Architecture

Entroping follows a Ports and Adapters design:

```mermaid
flowchart TB
  subgraph Domain["Domain"]
    Models["models: Pydantic schemas"]
    Bridge["bridge: pure translators and compilers"]
  end

  subgraph Primary["Primary adapters"]
    CLI["cli: Typer commands"]
    Studio["studio: Textual TUI"]
  end

  subgraph Secondary["Secondary adapters"]
    Core["core: Hurl, DB, reports, proxy"]
    Brain["brain: LiteLLM agents"]
  end

  CLI --> Models
  CLI --> Bridge
  Studio --> Models
  Studio --> Bridge
  Core --> Models
  Core --> Bridge
  Brain --> Models
  Brain --> Bridge
  Bridge --> Models
```

Dependency rule: domain modules do not import adapters.

## Repository Map

```text
src/entroping/         Python package implementation
tests/                 Fast regression and boundary tests
docs/product/          Product spec, MVP plan, and marketing note
docs/technical/        TDS, QAnstitution, command contract, Codex prompt
docs/user/             User guide, flows, and use cases
docs/evolution/        Timeline, requirements analysis, and creator intent
docs/architecture/     Architecture, diagrams, and development guide
docs/meta/             Obsidian onboarding, progress, and project operations
examples/              Minimal fixtures for onboarding and tests
decisions/             ADRs for durable product decisions
sources/               Source-material map
.context/              Maintainer/agent handoff context, hidden from public docs
AGENTS.md              Project-local Codex implementation rules
```

## Contributing And Community

- [GOOD_FIRST_ISSUE_WALKTHROUGH.md](docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH.md) gives new contributors a deterministic path from issue selection to local gates.
- [CONTRIBUTING.md](CONTRIBUTING.md) explains the local development and PR rules.
- [SECURITY.md](SECURITY.md) explains private vulnerability reporting and security gates.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) sets the project conduct baseline.

The open-source growth and monetization strategy lives in
[GROWTH_AND_MONETIZATION.md](docs/product/GROWTH_AND_MONETIZATION.md), with
maintainer guardrails in
[OPEN_CORE_BOUNDARIES.md](docs/product/OPEN_CORE_BOUNDARIES.md).

Public trust signals:

- `scripts/community_profile_audit.sh` verifies local community-health files.
- `.github/workflows/scorecard.yml` runs OpenSSF Scorecard weekly or manually,
  publishes results for the README badge, and is not a pull-request gate.

## Security and Quality Rules

- Do not log or commit secrets.
- Keep `.entroping/`, reports, local env files, and generated Graphify output out of Git.
- Use Hurl as the execution boundary; do not replace API execution with Python HTTP clients.
- Keep `entroping run` deterministic and LLM-free.
- Treat generated tests as code that must be reviewed.
- Audit optional extras before release:

```bash
uv run --all-extras --with pip-audit pip-audit --progress-spinner off
```

## License

Entroping Core is licensed under Apache-2.0. See [LICENSE](LICENSE).

The public core is intended to stay adoption-friendly and genuinely open source.
Future hosted, team, enterprise, model, policy-pack, or support offerings may be
distributed separately under commercial terms as defined by
[OPEN_CORE_BOUNDARIES.md](docs/product/OPEN_CORE_BOUNDARIES.md).
