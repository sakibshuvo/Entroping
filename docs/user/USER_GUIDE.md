# Entroping User Guide

**Version:** 4.1 Stable  
**Audience:** Developers, QA engineers, SDETs, architects, and platform teams

## 1. What Entroping Does

Entroping helps you turn backend intent into enforced API quality. You define policy in `qanstitution.yaml`, the canonical QAnstitution file, keep tests as Hurl files, record real traffic when needed, and run deterministic checks locally or in CI.

The normal loop is:

```text
Define law -> Generate or record tests -> Run Hurl with gates -> Review reports -> Commit artifacts
```

## 2. Install

The alpha is installed from source. For the latest GitHub branch:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git
```

For the published alpha tag:

```bash
uv tool install git+https://github.com/sakibshuvo/Entroping.git@v0.1.1-alpha
```

For local solo development:

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

Required external tools:

- `hurl`
- `hurlfmt` for Architect generated-Hurl validation; it is usually installed
  with the Hurl package, and `entroping doctor` reports it separately.
- Python 3.12 or 3.13
- `mitmproxy` for `watch`
- Ollama or cloud API credentials only when using AI commands

After installation:

```bash
entroping doctor
```

`doctor` should tell you whether Hurl, `hurlfmt`, local traffic state, local
config, QAnstitution files, and any configured AI agent personas are usable.
It checks whether configured `api_key_env` variables are present without
printing their values, and it does not call model providers.
Use `entroping doctor --output json` when CI jobs or coding agents need the
same health signal as versioned JSON instead of human text.
Before relying on Entroping in a PR gate, run `entroping doctor --ci` or
`entroping doctor --ci --output json`. CI readiness is stricter: missing Hurl,
unsafe `.entroping/` or `reports/` paths, empty suite manifests, unresolved
Hurl variables, and assumptions that `run --ci` needs model-provider access are
reported before test execution.

For local solo development, keep the install editable with `uv tool install -e .`. Homebrew, Nuitka binaries, Docker, and PyPI are distribution targets after the CLI is stable.

## 3. New Project Quick Start

Initialize Entroping:

```bash
entroping init
```

Define your law in `qanstitution.yaml`:

```yaml
project: "checkout-api"
sources:
  spec: "./openapi.json"
  stories: "./docs/stories"

gates:
  - id: "no_server_errors"
    condition: "true"
    gate: "status < 500"
    enforcement: "block"
  - id: "global_latency"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
  - id: "request_id_header"
    condition: "true"
    gate: 'header "X-Request-Id" exists'
    enforcement: "warn"
```

For a plain-language walkthrough of these starter gates, read
`docs/user/QANSTITUTION_FIRST_HOUR.md`.

Generate first tests from your API spec:

```bash
entroping architect build --new --tag smoke
```

When the API spec changes on a feature branch, focus generation to changed
operations from a reviewed base ref:

```bash
entroping architect build --new --changed-from origin/main --tag smoke
```

This mode writes tests only for current added, modified, or renamed OpenAPI
operations. Removed operations are reported for manual review; Entroping does
not delete existing Hurl tests automatically.

When an OpenAPI operation declares security requirements and an explicit `401`
or `403` response, `architect build --new` also writes deterministic
auth-negative Hurl coverage under `tests/generated/security/`. Supported HTTP
bearer/basic and API-key header/query/cookie schemes get missing/invalid auth
tests. Unsupported schemes are printed as warnings instead of guessed.

Generate or merge scoped prompt-backed coverage:

```bash
entroping architect build --agent breaker --prompt "Cover checkout authorization failures." --tag security
entroping architect build --strategy merge --prompt "Update checkout authorization coverage."
```

Prompt-backed merge updates existing Hurl files only. Manual files must expose
managed blocks; use prompt build without `--strategy merge` for new files. Builder
is the default prompt role, while `--agent breaker` selects the Breaker persona
for hostile auth, boundary, and policy-bypass coverage.

Successful prompt-backed Architect runs write value-free manifests under
`.entroping/agent-runs/`. These files record role, model ID, persona path/digest,
prompt hashes, output paths, tags, validation status, latency, and token counts.
They are audit evidence, not model approval, and they do not store raw prompts,
provider output, provider keys, persona content, raw traffic, or Hurl contents.

Run the suite:

```bash
entroping run --env local --tag smoke --report html
```

For a fast ad hoc subset, use a boolean tag expression:

```bash
entroping run --tag-expression "smoke and not slow" --report json
```

`--tag-expression` supports `and`, `or`, `not`, and parentheses over
Entroping metadata tags. It cannot be combined with repeatable `--tag` or
committed `--suite` manifests.

Use strict CI mode in pipelines:

```bash
entroping run --env ci --ci --parallel --report junit
```

To install the reviewed GitHub Actions starter workflow, run
`entroping init --github-actions`. For manual copy instructions and variants,
see `docs/user/GITHUB_ACTIONS_STARTER.md`.
For GitLab CI, Buildkite, CircleCI, or a generic shell runner, see
`docs/user/CI_PROVIDER_RECIPES.md`.

`--parallel` uses `settings.parallel_workers` from `qanstitution.yaml` and keeps
report ordering stable, so CI output remains deterministic even when files run
concurrently.
`--fail-fast` stops scheduling new tests after the first failing Hurl result.
Sequential runs stop immediately. Parallel runs let already scheduled workers
finish, then report selected, executed, and not-scheduled counts in latest-run
state and requested reports.
`settings.retry` gives each selected Hurl file a bounded retry budget. A test
only passes if its final Hurl attempt passes; Entroping does not hide flaky
failures. JSON, JUnit, HTML, and review-summary reports show retry count,
attempt status, final status, and unstable pass-after-retry evidence without
copying raw per-attempt output.
Run reports also show the effective `timeout_ms` for each test. If Hurl exceeds
that subprocess budget, Entroping marks the row as `timeout`, uses exit code
`124`, and renders timeout findings separately from ordinary failed assertions.
To run by API intent instead of tags, use committed OpenAPI metadata:

```bash
entroping run --operation-id createCheckout --operation-id createRefund --report json
```

This selects existing `.hurl` files with exact
`# entroping: operation_id=<id>` metadata and records the operation ID in JSON,
JUnit, and HTML run reports. It cannot be combined with `--tag`,
`--tag-expression`, `--suite`, or `--changed-from`.

## 4. Existing Hurl Project

If you already have Hurl tests, Entroping should adopt them rather than replace them.

1. Add `qanstitution.yaml`.
2. Ensure tests live under `tests/`.
3. Add tags and story metadata where useful.
4. Run:

```bash
entroping run --env local --report html
```

To apply a safe bulk change:

```bash
entroping architect refactor \
  --target "tests/payments/*.hurl" \
  --prompt "Add the Authorization header using {{auth_token}} to every request."
```

Current alpha support is intentionally narrow: refactor targets must either be
Architect-owned Hurl files marked with `# entroping: source=architect` or manual
Hurl files with explicit `# entroping: managed-begin <id>` and
`# entroping: managed-end <id>` blocks. For manual targets, Entroping replaces only
matching managed blocks and preserves surrounding content. Refactored Hurl is
validated before writing changes.

## 5. Legacy API Rescue

Use the Eye when no good spec or tests exist.

Start the recorder:

```bash
entroping watch --port 8080 --target http://localhost:3000
```

Route a browser, curl, Postman, Bruno, Insomnia, or another client through the proxy. Exercise the workflow manually.

### Practical `watch` Limits

Start with a local demo, test fixture, or development environment before
attempting capture against corporate, shared, staging, or production systems.

`watch` requires an explicit capture scope before it persists traffic. Use
`--target` for the primary service origin, repeat `--scope-host` for additional
host names, or repeat `--scope-url-prefix` for specific absolute URL prefixes.
Out-of-scope and malformed flow URLs are ignored before persistence; the
terminal summary reports only counts and does not print ignored URLs.

`entroping watch` uses mitmproxy, so HTTPS capture may require client-specific
setup. Install the mitmproxy CA certificate for each client, browser, or runtime
that you route through the proxy. Browser profiles, mobile simulators, JVMs,
Node runtimes, containers, and CLI tools can each have different certificate and
proxy trust stores.

Common real-environment failure modes include corporate VPNs or upstream
proxies, certificate pinning, clients that bypass system proxy settings, and
applications that refresh authentication and session headers outside the flow
you are exercising. If a client ignores the proxy, rejects the mitmproxy CA, or
pins a certificate, Entroping cannot truthfully observe that traffic through
`watch`.

Do not capture traffic unless you have permission. Entroping redaction happens
before persistence, but you are still responsible for capture authorization and review:
confirm that the environment is approved for interception, avoid collecting
third-party or user-private traffic, run `entroping report redaction` before
freezing tests, and inspect generated artifacts before committing them.
Multipart request and response bodies are fully summarized before persistence;
file fields, token fields, and harmless text fields are not stored as captured
body text.

Current alpha status: `watch` records redacted, bounded traffic locally under
`.entroping/state.db`; `freeze --name <flow> [--golden] [--dry-run]` can preview
or write validated generated Hurl files; `map --export mermaid|dot|md|png` emits
host-level dependency maps from redacted traffic; `freeze --mock <service>`
writes or previews WireMock-compatible dependency mappings. PNG export requires
local Graphviz `dot`; use Mermaid, DOT, or Markdown export when Graphviz is not
installed.
Written Hurl, WireMock, and PNG dependency-map artifacts also write approval
manifests under `reports/approvals/`. These manifests contain generated paths,
checksums, deterministic source fingerprints, and counts-only redaction
summaries; they do not contain raw traffic values or approve the artifact for
commit by themselves.

Use capture filters when the recorded session contains noise or multiple flows:

```bash
entroping freeze --name checkout_flow --golden --dry-run \
  --include-host api.example.test \
  --include-method POST \
  --include-path /checkout
entroping freeze --name checkout_flow --golden \
  --include-host api.example.test \
  --include-method POST \
  --include-path /checkout \
  --exclude-path "/checkout/internal/*"
entroping map --export mermaid --include-host api.example.test
```

The same filters work with `freeze --mock <service>`. Include filters narrow by
host, method, and path; exclude filters win. Filters apply to already-redacted
traffic and match request paths only, so query strings, headers, cookies, and
bodies are not used as filter output or copied into errors.

Use `--dry-run` first when a captured session contains sensitive or noisy
traffic. The preview shows selected methods, paths, status codes, proposed
output paths, golden status, and counts-only redaction categories. It does not
write Hurl files, WireMock mappings, approval manifests, or source artifacts.

Review what redaction categories fired before freezing or mapping:

```bash
entroping report redaction --output md
```

The redaction review writes `reports/redaction-review.md` by default and can
write `reports/redaction-review.html` with `--output html`. It contains counts
and categories only, not raw header, query, or body values.

Vendor a reviewed local policy pack when you want reusable gates without
hand-editing the import path:

```bash
entroping config test-policy-pack --pack ../entroping-policy-pack-api-baseline --output json
entroping config vendor-policy-pack --pack ../entroping-policy-pack-api-baseline --name api-baseline
```

The self-test command validates the local pack and writes nothing. The vendoring
command copies the pack under `policy-packs/`, validates the manifest and
QAnstitution entrypoint, and appends a local import. Neither command fetches
from remote registries or makes `entroping run` depend on a paid service.

Review the effective QAnstitution after local imports and overrides:

```bash
entroping report policy --output md
```

The policy report writes `reports/effective-policy.md` by default and can write
`reports/effective-policy.json` with `--output json`. It shows which file
supplied each effective gate, including imported policy packs and local
overrides.

Map each effective gate to committed Hurl coverage:

```bash
entroping report gate-coverage --output md
entroping report gate-coverage --output json
```

The gate coverage report writes `reports/gate-coverage.md` or
`reports/gate-coverage.json`. It shows which effective gates match committed
Hurl files, tags, operation IDs, request methods, and redacted request paths,
and it lists gates with no matching tests. It is not a run result: it does not
execute Hurl, inject assertions, evaluate pass/fail, call model providers, or
print full URLs, query strings, headers, bodies, variables, or traffic values.

Explain which gates would be injected into a selected Hurl file:

```bash
entroping report gate-injection --target tests/health.hurl --output md
entroping report gate-injection --target tests/health.hurl --output json
```

The gate-injection report writes `reports/gate-injection.md` or
`reports/gate-injection.json`. It resolves imports, final gates, reusable gate
groups, and active known-failure skips, then lists gate ID, source policy path,
condition, assertion, enforcement, and target file without running Hurl or
mutating source `.hurl` files.

Write checksum evidence for the local report artifacts:

```bash
entroping report artifact-manifest
```

The artifact manifest writes `reports/artifact-manifest.json`. It lists
standard local report artifacts, schema versions when available, byte sizes,
and SHA-256 checksums; missing expected artifacts are recorded without failing
the command. Use it as CI upload or release-review integrity evidence, not as a
signature, notarization, or attestation system.

Freeze the session into tests:

```bash
entroping freeze --name checkout_flow --golden
```

Run the generated tests:

```bash
entroping run --env local --tag regression --report html
```

Generate a dependency map:

```bash
entroping map --export mermaid
```

## 6. Component Testing with Mocks

When a service depends on external APIs, record a known-good session and generate mocks:

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name refund_flow --mock payments
```

Entroping emits WireMock-compatible mappings under `mocks/<service>/` for the
observed dependency. Run your service under test against those mocks, then run
the Hurl suite.

## 7. Microservice and Multi-Repo Workflows

Each service can own a local QAnstitution:

```text
service-a/qanstitution.yaml
service-b/qanstitution.yaml
service-c/qanstitution.yaml
```

Shared rules can live in a central governance repo and be imported:

```yaml
imports:
  - "../quality-rules/security.yaml"
  - "../quality-rules/performance.yaml"
```

Consumer services can also reference provider specs for compatibility and mock validation:

```yaml
dependencies:
  - name: "auth-service"
    spec: "../auth-service/openapi.json"
  - name: "payments"
    spec: "https://raw.githubusercontent.com/acme/payments/main/openapi.json"
```

A separate quality-gate repo can own cross-service E2E flows where useful:

```text
platform-quality/
  qanstitution.yaml
  tests/e2e/checkout_to_fulfillment.hurl
  envs/ci.env.example
```

## 8. Writing Good Hurl Tests

Prefer clear, stable assertions:

```hurl
# entroping: tags=smoke,auth
# entroping: story_id=AUTH-001

POST {{base_url}}/auth/login
Content-Type: application/json
{
  "email": "{{user_email}}",
  "password": "{{user_password}}"
}

HTTP 200
[Captures]
auth_token: jsonpath "$.token"
[Asserts]
jsonpath "$.token" exists
header "Content-Type" contains "application/json"
```

Good tests:

- Use variables for environment-specific values.
- Capture IDs and tokens instead of hardcoding volatile values.
- Tag meaningful suites such as `smoke`, `regression`, `security`, and `critical`.
- Link important tests to user stories with `# entroping: story_id=...`.
- Link external business systems with `# entroping: doc_url=...` when Jira, Notion, Linear, or monday.com remains the business source of truth.
- Assert contract and business behavior, not only status code.

When tags alone are not enough, commit named suite manifests under `suites/`.
They make the selected env, tags, paths, reports, parallel mode, fail-fast
behavior, and drift policy reviewable:

```yaml
# suites/smoke.yaml
version: entroping.suite.v1
name: smoke
env: ci
tags:
  - smoke
paths:
  - tests/**/*.hurl
reports:
  - json
  - junit
  - html
parallel: true
fail_fast: false
drift_check: false
```

Run the committed suite:

```bash
entroping run --suite smoke --ci
```

Create separate manifests such as `suites/regression.yaml` and
`suites/security.yaml` when a suite needs different paths, reports, or drift
settings. `--suite` cannot be combined with ad hoc selectors such as `--env`,
`--tag`, `--tag-expression`, `--report`, `--parallel`, `--fail-fast`, `--drift-check`, or
`--changed-from`; use `--ci` only to choose strict exit behavior.

Entroping can compile discovered Hurl metadata into a local story/test
traceability report:

```bash
entroping report traceability --output md
```

By convention, local story documents live under `docs/stories/*.md` and declare
their ID with a frontmatter-style line:

```markdown
---
story_id: CHK-001
title: Checkout accepts payment
---

# Checkout accepts payment
```

The report links matching Hurl `story_id` metadata to those Markdown documents
and flags missing story IDs, Hurl tests that reference stories without local
Markdown, Markdown stories without tests, duplicate story IDs, malformed story
metadata, and unsafe story paths. The command reads local files only. It does
not sync Jira, Notion, Linear, or monday.com directly.

## 9. Managing Test Data

Use environment files for safe defaults:

```text
envs/local.env
envs/ci.env
envs/prod-smoke.env
```

`entroping run --env <name>` loads `envs/<name>.env`, then applies explicit
shell `HURL_VARIABLE_<name>` values. Missing `{{variable}}` references fail
before Hurl starts, and the error lists variable names only, not values.

Commit examples, not secrets:

```text
envs/local.env.example
envs/ci.env.example
```

For dynamic workflows, use Hurl `[Options] variable` entries or captures:

```hurl
[Options]
variable: base_url=http://localhost:18080

[Captures]
order_id: jsonpath "$.order.id"
```

Then reuse:

```hurl
GET {{base_url}}/orders/{{order_id}}
HTTP 200
```

## 10. Reports and Bug Handoff

Generate reports during a run:

```bash
entroping doctor --ci
entroping run --env ci --ci --parallel --fail-fast --report json --report junit --report html
```

Expected artifacts:

```text
reports/junit.xml
reports/run-latest.json
reports/run-latest.html
.entroping/latest-run.json
.entroping/latest-run-events.jsonl
```

The JSONL event log is safe local progress evidence for CI wrappers and coding
agents. It records selected tests, redacted result events, report artifact
paths, no-match or error events, and completion status without storing Hurl
variables or raw passing stdout/stderr.

Compare a previous known-good JSON report with the current JSON report before
posting review evidence:

```bash
entroping report delta --base reports/run-base.json --current reports/run-latest.json
entroping report delta --base reports/run-base.json --current reports/run-latest.json --output json
```

The delta command reads existing local reports only. It reports added failures,
resolved failures, status changes, latency deltas, and policy-gate deltas
without executing Hurl or rendering raw stdout/stderr. It exits `1` when the
current run introduces added or changed failures, which makes it suitable for a
CI PR-comment step after `entroping run --report json`.

Generate local Shields-compatible coverage badges from existing reports:

```bash
entroping report policy --output json
entroping report gate-coverage --output json
entroping report gate-injection --target tests/health.hurl --output json
entroping report artifact-manifest
entroping architect audit --focus logic --output json > reports/openapi-audit.json
entroping report traceability --output json > reports/traceability.json
entroping report badges
```

This writes `reports/badges/policy-gates.json`,
`reports/badges/openapi-operations.json`, and
`reports/badges/story-traceability.json`. Badge generation is local and
report-backed: it reads the JSON reports above, fails clearly if a source report
is missing or malformed, and does not call shields.io or any hosted service.

Before reviewing an OpenAPI change against your main branch, run:

```bash
entroping architect audit --focus logic --changed-from origin/main --output md
```

This compares the configured local `sources.spec` file with the same file at
the Git base ref and reports removed operations, response status changes, newly
required request inputs, and practical JSON response-shape changes. It is
report-only: it does not generate, delete, or overwrite Hurl tests.

When a failure needs an issue:

```bash
entroping report bug
entroping report failure-bundle
```

The bug report should include:

- Failing test path.
- Gate rule ID.
- Environment name.
- Hurl repro command.
- Equivalent curl when possible.
- Actual vs expected behavior.
- Relevant sanitized request/response data.

Use `entroping report failure-bundle` when the handoff needs attachable local
evidence instead of a single Markdown body. The bundle writes
`reports/failure-bundle/manifest.json`, sanitized latest-run JSON, generated bug
Markdown, failed-test Hurl metadata, and any already-reviewed JUnit, HTML,
effective-policy, or redaction-review artifacts that exist. It refuses missing
latest runs, passing runs, raw traffic state, local env files, and unsafe
artifact paths.

When a review needs story/test evidence:

```bash
entroping report traceability --output md
entroping report traceability --output json > reports/traceability.json
```

In GitHub Actions, emit PR annotations from local reports:

```bash
entroping report github-annotations
```

Add `--traceability` only after the repository uses `story_id` metadata and you
want missing or conflicting story links to show as annotations.

To write SARIF 2.1.0 for GitHub code scanning or another SARIF consumer:

```bash
entroping report sarif --traceability
```

This writes `reports/entroping.sarif` from local JUnit, drift, and optional
traceability findings. Entroping does not upload the SARIF file; your CI system
owns that step.

For provider-neutral CI review text that can be uploaded as an artifact or
posted by any CI system, write a Markdown summary from the local artifacts:

```bash
entroping report review-summary --traceability
```

This writes `reports/review-summary.md` from the JSON run report, JUnit XML,
drift JSON, and optional local traceability metadata. Entroping does not call
GitHub, GitLab, Buildkite, Jira, Linear, or model providers to post it.

After writing reports that you plan to upload, write a manifest for reviewers:

```bash
entroping report artifact-manifest
```

The manifest includes checksums and sizes for present report files and a
`missing_artifacts` list for expected files that were not produced in this run.

## 11. Drift Detection

Use drift detection when you have a baseline and want to know whether runtime behavior changed:

```bash
entroping run --env staging --drift-check --report drift
```

For the MVP, the active baseline lives at `.entroping/drift-baseline.json`.
Entroping does not overwrite that file automatically. When `--report drift` is
requested and the Hurl suite passes, Entroping writes a sanitized candidate:

```bash
reports/drift-baseline.candidate.json
```

Review the candidate, compare it with the existing baseline when one exists, and
promote it only after accepting the behavior:

```bash
git diff --no-index -- .entroping/drift-baseline.json reports/drift-baseline.candidate.json
entroping report promote-drift-baseline
```

Promotion validates the candidate schema and writes the active baseline
atomically. It still represents human approval; do not run it until the
candidate diff is accepted.

The first drift slice compares:

- New or missing test paths.
- Hurl result status and exit code changes.
- Injected QAnstitution rule ID changes.
- Material per-test latency regressions from a reviewed duration baseline.
- Response status code changes when a response fingerprint is available.
- Selected stable response header changes such as `content-type`.
- JSON body shape changes without storing response values.
- New or missing dependency routes when `.entroping/dependency-baseline.json`
  exists.

Dependency-call drift is route-level. The baseline stores only reviewed
`destination_host`, `method`, and redacted `path_template` values:

```json
{
  "source_label": "client",
  "routes": [
    {
      "destination_host": "payments.example.test",
      "method": "POST",
      "path_template": "/charges/{id}"
    }
  ]
}
```

Current observations are read from redacted `.entroping/state.db` traffic and
compiled through the dependency-map path. Counts, latency, query strings,
headers, bodies, cookies, and tokens are not dependency drift truth.

If the baseline is missing, `--report drift` writes a machine-readable
`reports/drift.json` with a `missing_baseline` finding and a reviewable
`reports/drift-baseline.candidate.json` candidate when the Hurl suite passed.
`--drift-check` returns a non-zero exit code for missing baselines or drift
findings after Hurl itself has finished, so Hurl failures are still visible. See
[Drift Baseline Workflow](DRIFT_BASELINE_WORKFLOW.md) for the full review path.

### Fast Changed-Test Runs

Use changed-test selection when you are iterating locally on a small branch:

```bash
entroping run --changed-from origin/main --tag smoke
```

This mode selects existing changed `.hurl` files from Git diff, skips deleted
files, and follows rename targets. It is a fast feedback shortcut for developers
and agents, not a release gate. Keep full-suite `entroping run --ci` in CI.

## 12. Studio

Open the read-only local Studio TUI:

```bash
entroping studio --env local
```

Install the optional dependency first in a local checkout:

```bash
uv sync --extra studio
```

Studio opens tabbed views for:

- Detected QAnstitution project.
- Latest run summary and suite rows when `.entroping/latest-run.json` exists.
- Failure details from the sanitized latest run report.
- Applied-gate drilldowns from latest-run report rule IDs and QAnstitution gate definitions.
- Existing report artifact paths.
- A read-only traffic session browser over redacted SQLModel-backed state.
- Inferred target/dependency grouping, route counts, latency summaries, and safe redaction categories and counts.

Studio is intentionally read-only in the alpha. It does not update tests,
config, reports, or `.entroping` state. It also does not start `watch`, control
live capture, or render raw URLs with query values, headers, bodies, cookies,
tokens, or secrets.

The applied-gate drilldowns explain which QAnstitution gates were applied to
which tests by reading latest-run report rule IDs and QAnstitution gate
definitions. The view does not run Hurl, does not edit tests or config, and
does not replace the report artifacts as the durable evidence.

Near-term Studio work is report-backed and read-only: applied-gate drilldowns,
deeper failure drilldown, and traffic-session navigation may read sanitized
artifacts or redacted state. Studio should not rerun suites, edit tests, or change config in the alpha.
Future write actions must follow
[STUDIO_MUTATION_WORKFLOW_DESIGN.md](../technical/STUDIO_MUTATION_WORKFLOW_DESIGN.md)
before implementation.

Studio is a local development interface. CI should use `entroping run`.

## 13. Production Smoke Testing

Production smoke suites should be small, read-heavy, and safe.

Recommended pattern:

```bash
entroping run --env prod-smoke --tag smoke --ci --report junit
```

Do not rely on a generated test to make unsafe production writes safe. In v4.1, keep the `smoke` tag reserved for read-only or explicitly idempotent tests, and use QAnstitution gates for latency, status, and header expectations:

```yaml
gates:
  - id: "prod_smoke_latency"
    condition: "tags contains 'smoke'"
    gate: "duration < 500"
    enforcement: "block"
```

Compound production safety rules that combine environment, tag, and method can be added after the condition DSL explicitly supports compound expressions.

## 14. AI Workflow

Use AI for:

- Generating test drafts.
- Creating negative cases.
- Refactoring repetitive test changes.
- Auditing coverage gaps.
- Explaining failures in reports.

Do not use AI as the final authority. Always run:

```bash
entroping run --ci
```

Generated tests should be reviewed like code.

### Local-First Brain Setup

The intended UX is local-first and cloud-second:

- Use a local Ollama model where privacy or offline work matters.
- Use cloud models only after explicit configuration.
- Do not rely on external Gemini or Claude CLI tools; Entroping talks to models through LiteLLM.
- Keep API keys in environment variables or OS credential storage, not plaintext config files.

The operational setup guide lives in `docs/user/AI_PROVIDER_SETUP.md`. It covers
LiteLLM installation, local Qwen through Ollama, local Qwen through oMLX
OpenAI-compatible endpoints, cloud model routing, and no-provider CI.

The Architect should generate only from configured sources: specs, stories, dependency specs, redacted traffic, or explicit prompt context. If you ask for exploratory negative tests, review them carefully and keep the resulting Hurl files in Git.

### Business Truth Elsewhere

If your real requirements live in Jira, Notion, Linear, or monday.com, do not duplicate everything manually. For v1, add trace IDs:

```hurl
# entroping: tags=regression,login
# entroping: story_id=JIRA-101
# entroping: doc_url=https://jira.example.com/browse/JIRA-101
```

At team scale, generate `docs/stories/*.md` as a read-only cache from the external system so the Architect has local context.
Keep external systems as sources of truth; Entroping treats `story_id` and
`doc_url` as local traceability metadata unless a future adapter explicitly
adds API synchronization.

## 15. Troubleshooting

### Hurl is Missing

Run `entroping doctor`. Install Hurl through your package manager, then retry.
If `hurlfmt` is missing but Hurl is present, deterministic runs can still work,
but Architect generation/refactor validation needs the parser binary before it
can accept generated Hurl.

### mitmproxy Certificate Errors

Install the mitmproxy CA certificate for the client that is routed through `watch`.
For browser, runtime, VPN, proxy, and permission limits, see the Practical
`watch` Limits section in the legacy rescue workflow.

If `watch` exits before starting the proxy, confirm that you provided an explicit
capture scope with `--target`, `--scope-host`, or `--scope-url-prefix`.

### Tests Pass Locally but Fail in CI

Check:

- `--env` value.
- Environment variables, including `HURL_VARIABLE_<name>` overrides.
- Base URLs.
- Secret availability.
- Network access to dependent services.
- Imported QAnstitution rules.

### Generated Test Looks Wrong

Run:

```bash
hurlfmt --out json tests/path/to/test.hurl >/dev/null
entroping architect audit --focus logic --output md
entroping architect audit --focus auditor --output md
```

The deterministic logic audit shows an operation-to-Hurl matrix: covered,
uncovered, and ambiguous OpenAPI operations, plus stale committed
`operation_id` metadata that no longer exists in the configured spec. If you
have captured redacted traffic with `entroping watch`, the same logic audit
also flags live routes that appeared in traffic but are missing from OpenAPI,
and `--changed-from <ref>` adds deterministic OpenAPI breaking-change diff
findings for spec evolution review.
and shows spec-only operations that were not observed. The traffic route audit
uses method, path templates, counts, and operation IDs only; it does not print
raw query strings, headers, cookies, bodies, tokens, or captured values.

Then refine with a narrower prompt. If `hurlfmt` is not installed, use the project's configured Hurl parser-backed validation step before accepting generated files.
When Architect provider output is not valid JSON or generated Hurl fails parser
validation, Entroping stops before writing files and prints a short validation
summary. The raw provider output and parser streams are still not echoed because
they can contain untrusted or secret-like content.
Use the printed retry guidance as the next prompt constraint: ask for only the
Architect JSON object when schema parsing fails, or ask for syntactically valid
Hurl content inside the selected file when parser validation fails. Do not paste
raw provider output or parser streams into tickets until you have reviewed them
for secrets.

### Local Brain Feels Slow

Check whether the local Ollama model is installed and running. If the machine is memory-constrained, configure a smaller local model or explicitly switch the agent model to a cloud provider.
Run `entroping doctor` to confirm configured persona files are safe and the
expected `api_key_env` names are set without exposing secret values.

## 16. Safe Defaults

- Keep `.entroping/state.db` out of Git.
- Keep `.entroping/state.db` bounded with retention settings or cleanup.
- Keep real env files out of Git.
- Commit generated tests only after review.
- Prefer `warn` or `audit_only` for new broad rules before switching them to `block`.
- Require expiry dates for known failures and keep them exact: a selected
  known-failure entry must match a selected Hurl test path and injected
  QAnstitution gate ID, or `entroping run --ci` fails before Hurl execution.
- Keep smoke tests fast and deterministic.
