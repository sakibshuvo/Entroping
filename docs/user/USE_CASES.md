# Entroping Use Cases

**Version:** 4.1 Stable

## 1. Guard an AI-Generated Endpoint

### Scenario

A coding agent adds a new payment refund endpoint. The developer wants confidence before opening a PR.

### Entroping Workflow

```bash
entroping architect build --prompt "Create tests for the new refund endpoint, including invalid amount and missing auth." --tag payments
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
entroping freeze --name checkout_flow --golden
entroping map --export mermaid
entroping run --env local --tag regression --report html
```

### Expected Artifacts

- `tests/generated/checkout_flow.hurl`
- Golden assertions.
- Counts-only redaction review.
- Dependency map.
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
```

### Expected Artifacts

- Effective policy summary.
- JUnit report with rule IDs on failure.
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
```

### Expected Artifacts

- `reports/drift.json`
- Summary of changed status codes, headers, schemas, or latency.

### Value

The team sees runtime drift before customers do.

## 6. Generate Security Breaker Tests

### Scenario

The team wants hostile tests for auth bypass, IDOR, and invalid roles without adding a separate `chaos` command.

### Entroping Workflow

```bash
entroping architect build \
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

Run audit:

```bash
entroping report traceability --output md
```

### Expected Artifacts

- Traceability report listing linked stories, owners, docs, tests, tags, and metadata findings.
- Hurl tests with stable traceability metadata.

### Value

Product intent is connected to runtime evidence.

## 8. GraphQL API Governance

### Scenario

A service exposes GraphQL over HTTP and must ensure queries do not return top-level errors.

### Entroping Workflow

```bash
entroping architect build --prompt "Generate GraphQL tests for user lookup and permission denial." --tag graphql
entroping run --env local --tag graphql --report html
```

### Expected Assertions

- HTTP status is valid.
- `$.errors` is absent for success cases.
- `$.data` contains required fields.
- Denied access returns the expected error shape.

### Value

GraphQL behavior is covered using the same Hurl execution and policy engine.

## 9. Webhook Regression

### Scenario

A service emits webhooks to downstream consumers and the team wants to preserve event shape.

### Entroping Workflow

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name invoice_paid_webhook --golden
entroping run --env local --tag regression --report html
```

### Expected Artifacts

- Captured webhook request.
- Golden event shape assertions.
- Dependency map showing webhook receiver.

### Value

Webhook contracts become visible and testable.

## 10. Production Smoke Gate

### Scenario

After deployment, the platform team wants a tiny safe suite to validate critical endpoints.

### Entroping Workflow

```bash
entroping run --env prod-smoke --tag smoke --ci --report junit
```

### Expected Artifacts

- JUnit report.
- Failure with rule ID if a smoke gate breaks.

### Value

Production behavior gets a fast, deterministic safety check.
