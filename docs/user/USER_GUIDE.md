# Entroping User Guide

**Version:** 4.1 Stable  
**Audience:** Developers, QA engineers, SDETs, architects, and platform teams

## 1. What Entroping Does

Entroping helps you turn backend intent into enforced API quality. You define policy in `qanstitution.yaml`, keep tests as Hurl files, record real traffic when needed, and run deterministic checks locally or in CI.

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

`doctor` should tell you whether Hurl, `hurlfmt`, local traffic state, local config, and QAnstitution files are usable.

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

Generate or merge scoped prompt-backed coverage:

```bash
entroping architect build --prompt "Cover checkout authorization failures." --tag security
entroping architect build --strategy merge --prompt "Update checkout authorization coverage."
```

Prompt-backed merge updates existing Hurl files only. Manual files must expose
managed blocks; use prompt build without `--strategy merge` for new files.

Run the suite:

```bash
entroping run --env local --tag smoke --report html
```

Use strict CI mode in pipelines:

```bash
entroping run --env ci --ci --parallel --report junit
```

For a copyable GitHub Actions workflow, see
`docs/user/GITHUB_ACTIONS_STARTER.md`.
For GitLab CI, Buildkite, CircleCI, or a generic shell runner, see
`docs/user/CI_PROVIDER_RECIPES.md`.

`--parallel` uses `settings.parallel_workers` from `qanstitution.yaml` and keeps
report ordering stable, so CI output remains deterministic even when files run
concurrently.

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

Current alpha status: `watch` records redacted, bounded traffic locally under
`.entroping/state.db`; basic `freeze --name <flow> [--golden]` writes validated
generated Hurl files; `map --export mermaid|dot|md|png` emits host-level dependency
maps from redacted traffic; `freeze --mock <service>` writes WireMock-compatible
dependency mappings. PNG export requires local Graphviz `dot`; use Mermaid, DOT,
or Markdown export when Graphviz is not installed.

Review what redaction categories fired before freezing or mapping:

```bash
entroping report redaction --output md
```

The redaction review writes `reports/redaction-review.md` by default and can
write `reports/redaction-review.html` with `--output html`. It contains counts
and categories only, not raw header, query, or body values.

Review the effective QAnstitution after local imports and overrides:

```bash
entroping report policy --output md
```

The policy report writes `reports/effective-policy.md` by default and can write
`reports/effective-policy.json` with `--output json`. It shows which file
supplied each effective gate, including imported policy packs and local
overrides.

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

Entroping can compile discovered Hurl metadata into a local story/test
traceability report:

```bash
entroping report traceability --output md
```

The command reads local Hurl metadata only. It does not sync Jira, Notion,
Linear, or monday.com directly.

## 9. Managing Test Data

Use environment files for safe defaults:

```text
envs/local.env
envs/ci.env
envs/prod-smoke.env
```

Commit examples, not secrets:

```text
envs/local.env.example
envs/ci.env.example
```

For dynamic workflows, use Hurl captures:

```hurl
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
entroping run --env ci --ci --parallel --report junit --report html
```

Expected artifacts:

```text
reports/junit.xml
reports/run-latest.html
.entroping/latest-run.json
```

When a failure needs an issue:

```bash
entroping report bug
```

The bug report should include:

- Failing test path.
- Gate rule ID.
- Environment name.
- Hurl repro command.
- Equivalent curl when possible.
- Actual vs expected behavior.
- Relevant sanitized request/response data.

When a review needs story/test evidence:

```bash
entroping report traceability --output md
```

In GitHub Actions, emit PR annotations from local reports:

```bash
entroping report github-annotations
```

Add `--traceability` only after the repository uses `story_id` metadata and you
want missing or conflicting story links to show as annotations.

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
cp reports/drift-baseline.candidate.json .entroping/drift-baseline.json
```

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

### Tests Pass Locally but Fail in CI

Check:

- `--env` value.
- Environment variables.
- Base URLs.
- Secret availability.
- Network access to dependent services.
- Imported QAnstitution rules.

### Generated Test Looks Wrong

Run:

```bash
hurlfmt --out json tests/path/to/test.hurl >/dev/null
entroping architect audit --focus logic --output md
```

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

## 16. Safe Defaults

- Keep `.entroping/state.db` out of Git.
- Keep `.entroping/state.db` bounded with retention settings or cleanup.
- Keep real env files out of Git.
- Commit generated tests only after review.
- Prefer `warn` or `audit_only` for new broad rules before switching them to `block`.
- Require expiry dates for known failures.
- Keep smoke tests fast and deterministic.
