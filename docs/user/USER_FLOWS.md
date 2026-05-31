# Entroping User Flows

**Version:** 4.1 Stable

## 1. Flow Map

| Flow | User | Primary Commands |
| --- | --- | --- |
| Genesis for a new API | Developer | `init`, `architect build`, `run` |
| Legacy rescue | QA/SDET | `watch`, `report redaction`, `freeze`, `map`, `run` |
| Active feature development | Developer | `architect build`, `architect refactor`, `run` |
| CI quality gate | Platform team | `doctor`, `run --ci` |
| Governance rollout | Architect | `config`, QAnstitution imports, `doctor` |
| Failure handoff | Developer/QA | `run`, `report bug` |
| Traceability review | Architect/QA | `report traceability` |
| Production smoke | SRE/platform | `run --tag smoke --ci` |

## 2. Genesis: New API

### Trigger

A team has an OpenAPI spec or early implementation and wants a governed test baseline.

### Steps

1. Initialize Entroping.
2. Add or reference `openapi.json`.
3. Configure basic gates in `qanstitution.yaml`.
4. Generate tests.
5. Run smoke suite.
6. Commit QAnstitution and reviewed Hurl files.

### Commands

```bash
entroping init
entroping architect build --new --tag smoke
entroping run --env local --tag smoke --report html
```

### Artifacts

- `qanstitution.yaml`
- `tests/**/*.hurl`
- `envs/local.env.example`
- `reports/run-latest.html`

### Success Criteria

- Generated tests pass Hurl syntax validation.
- Smoke suite passes locally.
- Every critical endpoint has at least status, schema, and latency coverage.

## 3. Active Feature Development

### Trigger

A developer or AI coding agent adds or changes API behavior.

### Steps

1. Describe new behavior through prompt or updated spec.
2. Ask Architect to build or merge tests.
3. Review generated diff.
4. Run relevant tags.
5. Fix application or tests as needed.

### Commands

```bash
entroping architect build --strategy merge --prompt "Cover the new refund endpoint" --tag payments
entroping run --env local --tag payments --report html
```

Prompt-backed merge updates existing Hurl targets only. Manual files must expose
managed blocks; new files should use `architect build --prompt` without
`--strategy merge`.

### Success Criteria

- Tests represent intended behavior.
- Source tests are reviewed.
- QAnstitution gates pass.

## 4. Existing Test Refactor

### Trigger

Headers, auth, tenant routing, or API shape changes across many tests.

### Steps

1. Select the target glob.
2. Provide a precise refactor prompt.
3. Review generated changes.
4. Run the affected suite.

### Commands

```bash
entroping architect refactor \
  --target "tests/**/*.hurl" \
  --prompt "Add X-Tenant-Id: {{tenant_id}} to all non-public requests."
entroping run --env local --tag regression --report html
```

Current alpha support applies to Architect-owned Hurl files and manual files that
opt into managed-block replacement with `# entroping: managed-begin <id>` and
`# entroping: managed-end <id>` markers.

### Success Criteria

- Comments and manual sections are preserved.
- Modified tests pass Hurl syntax validation.
- Affected suite passes or produces clear failures.

## 5. Legacy Rescue

### Trigger

An API lacks reliable tests or complete specs.

### Steps

1. Start `watch`.
2. Route traffic through proxy.
3. Exercise important user journeys.
4. Review redaction coverage.
5. Freeze captured session.
6. Review generated Hurl.
7. Run regression suite.
8. Export dependency map.

### Commands

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping report redaction --output md
entroping freeze --name checkout_flow --golden
entroping run --env local --tag regression --report html
entroping map --export mermaid
```

### Success Criteria

- Captured traffic is redacted.
- Redaction review reports counts and categories only.
- Generated tests are parameterized.
- Golden assertions avoid unstable fields unless explicitly locked.
- Dependency map reveals external services.

## 6. Component Isolation with Mocks

### Trigger

A service must be tested while upstream or downstream dependencies are unavailable, costly, flaky, or unsafe.

### Steps

1. Record a successful flow.
2. Freeze dependency behavior as mocks.
3. Run service under test against mocks.
4. Run Entroping suite.

### Commands

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name refund_flow --mock payments
entroping run --env local --tag component --report html
```

### Success Criteria

- WireMock mappings represent observed dependency behavior.
- Component tests can run without the real dependency.
- Mocked behavior is documented and reviewable.

## 7. CI Quality Gate

### Trigger

A pull request or deployment pipeline needs a deterministic API gate.

### Steps

1. Install dependencies.
2. Run `doctor`.
3. Run suite in CI mode.
4. Publish JUnit and HTML reports.
5. Block merge on failures.

### Commands

```bash
entroping doctor
entroping run --env ci --ci --parallel --report junit --report html
```

For a copyable GitHub Actions workflow, use
`docs/user/GITHUB_ACTIONS_STARTER.md`.

### Success Criteria

- Non-zero exit on blocking failures.
- JUnit appears in CI test summary.
- Failed gates include rule IDs.

## 8. Governance Rollout

### Trigger

An architect wants to apply shared policy across multiple services.

### Steps

1. Create central rules repo.
2. Import rules into service QAnstitutions.
3. Run `doctor` in each service.
4. Start new rules as `warn` where blast radius is uncertain.
5. Promote to `block` after teams fix issues.

### Example

```yaml
imports:
  - "../central-quality/security.yaml"
  - "../central-quality/performance.yaml"
```

### Success Criteria

- Effective policy is inspectable.
- Teams can see which imported rule failed.
- Local overrides are intentional and reviewable.

## 9. Failure Handoff

### Trigger

An Entroping run fails and needs a bug ticket.

### Steps

1. Run or inspect latest report.
2. Generate bug report.
3. Attach sanitized request/response evidence.
4. Link issue to known failure only if a temporary exception is approved.

### Commands

```bash
entroping report bug
```

### Success Criteria

- Bug includes exact repro command.
- Failure includes expected vs actual behavior.
- If ignored, the exception has issue ID and expiry.

## 10. Traceability Review

### Trigger

An architect, QA lead, or product stakeholder wants to verify which runtime
tests are linked to story or business-system references.

### Steps

1. Ensure important Hurl files contain `# entroping: story_id=...`.
2. Add `# entroping: owner=...` and `# entroping: doc_url=...` where useful.
3. Generate the local traceability report.
4. Fix missing story IDs or conflicting doc links before release review.

### Command

```bash
entroping report traceability --output md
```

### Success Criteria

- Critical tests are linked to stable story IDs.
- External document links do not map to conflicting story IDs.
- No business-system API sync is required for the local review.

## 11. Production Smoke

### Trigger

An SRE or platform team wants minimal confidence after deploy.

### Steps

1. Maintain a small `smoke` tag suite.
2. Use prod-safe variables.
3. Run with CI mode.
4. Block dangerous operations through policy.

### Command

```bash
entroping run --env prod-smoke --tag smoke --ci --report junit
```

### Success Criteria

- Suite is fast.
- Suite is safe.
- Failure points to a specific endpoint or gate.
