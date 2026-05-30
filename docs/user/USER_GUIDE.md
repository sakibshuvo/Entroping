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

For the MVP/source workflow:

```bash
uv tool install -e .
```

Required external tools:

- `hurl`
- Python 3.12+
- `mitmproxy` for `watch`
- Ollama or cloud API credentials only when using AI commands

After installation:

```bash
entroping doctor
```

`doctor` should tell you whether Hurl, mitmproxy, local config, and QAnstitution files are usable.

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
  - id: "global_latency"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
```

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
generated Hurl files; `map --export mermaid|dot|md` emits host-level dependency
maps from redacted traffic; `freeze --mock <service>` writes WireMock-compatible
dependency mappings. PNG map rendering is still planned follow-up work.

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
reports/junit/report.xml
reports/html/index.html
reports/run.json
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

## 11. Drift Detection

Use drift detection when you have a baseline and want to know whether runtime behavior changed:

```bash
entroping run --env staging --drift-check --report drift
```

Drift findings should identify:

- Status code changes.
- Schema/body shape changes.
- Header changes.
- Latency regressions.
- New or missing dependency calls where traffic baselines exist.

## 12. Studio

Open the local TUI:

```bash
entroping studio --env local
```

Studio should help inspect:

- Test suites and tags.
- Last run results.
- Applied gates.
- Failure details.
- Traffic sessions.
- Reports.

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

The Architect should generate only from configured sources: specs, stories, dependency specs, redacted traffic, or explicit prompt context. If you ask for exploratory negative tests, review them carefully and keep the resulting Hurl files in Git.

### Business Truth Elsewhere

If your real requirements live in Jira, Notion, Linear, or monday.com, do not duplicate everything manually. For v1, add trace IDs:

```hurl
# entroping: tags=regression,login
# entroping: story_id=JIRA-101
# entroping: doc_url=https://jira.example.com/browse/JIRA-101
```

At team scale, generate `docs/stories/*.md` as a read-only cache from the external system so the Architect has local context.

## 15. Troubleshooting

### Hurl is Missing

Run `entroping doctor`. Install Hurl through your package manager, then retry.

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
