---
title: Entroping Use Cases
description: "See how Entroping governs AI-generated APIs, drift, policy, CI, and reviewed runtime evidence."
type: guide
status: active
tags:
  - use-cases
  - onboarding
---

# Entroping Use Cases

**Contract version:** 4.1
**Product maturity:** Alpha

## 1. Guard an AI-Generated Endpoint

### Scenario

A coding agent adds a new payment refund endpoint. The developer wants confidence before opening a PR.

### Entroping Workflow

```bash
entroping architect build --prompt "Create happy-path tests for the new refund endpoint." --tag payments
entroping architect build --agent breaker --prompt "Create invalid amount and missing-auth refund tests." --tag payments
entroping run --env local --tag payments --report html
```

### Expected Artifacts

- New or updated Hurl tests under `tests/payments/`.
- Security and latency gates applied from QAnstitution.
- HTML report for review.

### Value

The developer gets executable coverage for behavior the AI just introduced.

## 2. Reverse-Engineer a Legacy Checkout Flow

### Scenario

A legacy checkout API has no reliable tests and incomplete documentation.

### Entroping Workflow

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping report redaction --output md
entroping freeze --name checkout_flow --golden --include-host api.example.test --exclude-path "/assets/*"
entroping map --export mermaid --include-host api.example.test
entroping run --env local --tag regression --report html
```

### Expected Artifacts

- `tests/generated/checkout_flow.hurl`
- Golden assertions.
- Counts-only redaction review.
- Dependency map.
- Capture filters for noisy hosts, methods, and paths.
- Local traffic records in `.entroping/state.db`.

### Value

Real behavior becomes reviewable regression coverage.

## 3. Enforce Shared Security Policy

### Scenario

An organization wants every API to include request IDs, avoid 5xx responses in smoke tests, and stay below latency budgets.

### Entroping Workflow

```yaml
imports:
  - "../central-quality/security.yaml"
  - "../central-quality/performance.yaml"
```

```bash
entroping doctor
entroping run --env ci --ci --parallel --report junit
entroping report github-annotations
entroping report sarif
```

### Expected Artifacts

- Effective policy summary.
- JUnit report with rule IDs on failure.
- GitHub PR annotations for failed Hurl files.
- SARIF code-scanning artifact for policy and security findings.
- CI failure for blocking rules.

### Value

Architectural rules become executable across repos.

## 4. Create Component Tests with Mocks

### Scenario

The checkout service depends on an external payment provider that is costly and flaky in tests.

### Entroping Workflow

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name successful_payment --mock payments
entroping run --env local --tag component --report html
```

### Expected Artifacts

- Hurl component tests.
- WireMock mappings for payment provider responses.
- A repeatable local test harness.

### Value

The team can test checkout behavior without depending on the real payment service.

## 5. Detect Contract Drift

### Scenario

Staging behavior changes after a deployment. The team wants to know whether response shape or status changed.

### Entroping Workflow

```bash
entroping run --env staging --drift-check --report drift
entroping report promote-drift-baseline
```

Run the promotion command only after reviewing and accepting the candidate diff.

### Expected Artifacts

- `reports/drift.json`
- `reports/drift-baseline.candidate.json` when the Hurl suite passes.
- Summary of changed status codes, headers, schemas, or latency.

### Value

The team sees runtime drift before customers do, then promotes a new baseline
only after reviewing the candidate artifact.

## 6. Generate Security Breaker Tests

### Scenario

The team wants hostile tests for auth bypass, IDOR, and invalid roles without adding a separate `chaos` command.

### Entroping Workflow

```bash
entroping architect build \
  --agent breaker \
  --prompt "Generate hostile tests for auth bypass, IDOR, missing tenant ID, and invalid role escalation." \
  --tag security
entroping run --env local --tag security --report html
```

### Expected Artifacts

- Security-tagged Hurl tests.
- Breaker agent output validated by Hurl.
- Reports showing actual behavior.

### Value

The Breaker role expands risk coverage without command sprawl.

## 7. Link Tests to User Stories

### Scenario

Leadership wants traceability from Markdown stories to runtime tests.

### Entroping Workflow

Add metadata:

```hurl
# entroping: tags=checkout,regression
# entroping: story_id=CHK-001
```

Add a matching local story document:

```markdown
---
story_id: CHK-001
title: Checkout accepts payment
---
```

Run audit:

```bash
entroping report traceability --output md
```

### Expected Artifacts

- Traceability report listing linked stories, local story Markdown files, owners, docs, tests, tags, and metadata findings.
- Gap findings for tests without `story_id`, Hurl story IDs missing local Markdown, Markdown stories without tests, duplicate story IDs, malformed story metadata, and unsafe story paths.
- Hurl tests with stable traceability metadata.

### Value

Product intent is connected to runtime evidence.

## 8. GraphQL-over-HTTP Internal Scaffold

> **Support boundary:** This is an internal scaffold, not a supported public workflow.
> There is no public GraphQL schema-to-test command or native GraphQL runtime guarantee.

### Scenario

A service exposes GraphQL over HTTP and must ensure queries do not return top-level errors.

### Bounded Exploration

```bash
entroping run --env local --tag graphql --report html
```

### Expected Assertions

- HTTP status is valid.
- `$.errors` is absent for success cases.
- `$.data` contains required fields.
- Denied access returns the expected error shape.

### Value

Reviewed HTTP requests can run through Hurl, but the scaffold does not establish
public GraphQL generation or native protocol support.

## 9. Observed HTTP Callback Regression

### Scenario

A service emits an HTTP callback to downstream consumers and the team wants to
preserve the observed request shape.

### Entroping Workflow

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name invoice_paid_webhook --golden
entroping run --env local --tag regression --report html
```

### Expected Artifacts

- Captured HTTP callback request.
- Golden event shape assertions.
- Dependency map showing webhook receiver.

### Value

Observed HTTP callbacks become reviewable Hurl evidence. This does not provide
an AsyncAPI broker, message-delivery runtime, or webhook-specific public command.

## 10. Production Smoke Gate

### Scenario

After deployment, the platform team wants a tiny safe suite to validate critical endpoints.

### Entroping Workflow

Create a reviewed suite manifest:

```yaml
version: entroping.suite.v1
name: prod-smoke
env: prod-smoke
protected: true
safety: read-only
tags:
  - smoke
reports:
  - junit
```

Then run it in CI mode:

```bash
entroping run --suite prod-smoke --ci
```

### Expected Artifacts

- JUnit report.
- Failure with rule ID if a smoke gate breaks.
- Blocked report evidence if a selected mutating test lacks reviewed safety
  metadata or is marked `destructive`.

### Value

Production behavior gets a fast, deterministic safety check.

## 11. AI-broke-my-API Walkthrough

### Scenario

An AI-assisted edit removes a response header that downstream operations rely on,
while the endpoint still returns an apparently healthy payload and status.

### Entroping Workflow

```bash
scripts/ai_regression_demo.sh
```

### Expected Artifacts

- `examples/ai-regression-demo/` fixture that intentionally omits a required
  `X-Request-Id` header.
- `reports/run-latest.json` with a failing `request_id_header` gate.
- Local proof that runtime governance catches the regression before review or
  deployment.

### Value

Teams can validate that AI-generated changes pass happy-path behavior while still
failing deterministic policy gates for operational integrity.
