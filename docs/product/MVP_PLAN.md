# Entroping MVP Plan

**Version:** 4.1 Stable  
**Goal:** Build the smallest useful Hurl-native governance loop without losing the final product architecture.

## 1. MVP Definition

The MVP proves this loop:

```text
init -> define QAnstitution -> run Hurl with injected gates -> report deterministic results
```

After that loop is reliable, add AI generation and traffic observation.

The implementation path is solo-first. Prefer source-level debugging, editable `uv` installs, and narrow verified milestones over binary packaging or broad enterprise workflows.

## 2. Implementation Phases

### Phase 0: Repository and Context

Deliverables:

- Python package scaffold.
- `pyproject.toml`.
- Typer CLI entrypoint.
- Basic tests and lint/type tooling.
- Example `qanstitution.yaml`.

Exit criteria:

- `entroping --help` works.
- Test command runs in local environment.
- Package imports are clean.

### Phase 1: QAnstitution and Doctor

Deliverables:

- Pydantic v2 schema.
- Local import support.
- Effective policy merge.
- Basic condition parser and typed condition AST for the supported DSL subset.
- `entroping init`.
- `entroping doctor`.

Exit criteria:

- Invalid config and invalid gate conditions fail with actionable errors.
- Duplicate and final gate behavior is tested.
- Doctor reports Hurl availability and config health.

### Phase 2: Hurl Runner and Gate Injection

Deliverables:

- Hurl discovery.
- Subprocess runner with timeout and redaction.
- Test discovery.
- Tag filtering.
- Gate matching.
- Temporary execution files.
- `entroping run`.

Exit criteria:

- Source `.hurl` files are not mutated by run.
- Gates are injected into execution copies.
- Blocking gates produce non-zero exit.
- `warn` gates appear in reports without failing the run.

### Phase 3: Reports and CI

Deliverables:

- JSON run summary.
- JUnit XML.
- HTML report shell.
- `--ci` behavior.
- `report bug`.

Exit criteria:

- CI can publish JUnit.
- Failure report includes test path, rule ID, environment, and repro command.
- Reports redact secrets.

### Phase 4: Architect Minimal

Current implementation note: the deterministic pieces of this phase are landing before
LLM calls. `architect audit` already reports OpenAPI coverage gaps, and `config list`
/ `config set` manage non-secret Builder/Auditor/Breaker model routing in
`qanstitution.yaml`.

Deliverables:

- LiteLLM client wrapper.
- Local-first provider defaults with explicit cloud model configuration.
- Credential lookup through environment variables or OS credential storage.
- Agent config loading.
- Builder/Auditor/Breaker persona loading.
- Structured output validation.
- `architect audit`.
- `architect build --prompt` for scoped Hurl generation.
- `architect refactor` with Hurl validation.

Exit criteria:

- No dependency on external Gemini, Claude, or ChatGPT CLIs.
- Generated Hurl passes Hurl syntax validation.
- Refactor preserves manual comments in tested fixtures.
- LLM failures are explicit and do not corrupt files.

### Phase 5: OpenAPI Build

Deliverables:

- OpenAPI loader.
- Dedicated `bridge.openapi_to_hurl` compiler.
- Basic operation-to-Hurl generation.
- Common path/query/header/cookie parameter rendering.
- Request-body examples/defaults sourced from schemas.
- Schema/status/header assertions.
- `architect build --new`.
- Dedicated `bridge.merge` module for `--strategy merge`.

Exit criteria:

- A fixture OpenAPI spec generates passing syntax.
- Generated tests include tags and story metadata where available.
- Merge strategy avoids unrelated rewrites.

### Phase 6A: Eye Capture Spike

Deliverables:

- Minimal mitmproxy addon.
- SQLite traffic store.
- Redaction pipeline for headers, cookies, known token fields, and body limits.
- `watch` capture-only workflow.

Exit criteria:

- Captured secrets are redacted before persistence.
- Capture can run without `freeze` or `map`.
- Local state growth is bounded by retention settings.
- No captured raw traffic is sent to LLMs.

### Phase 6B: Freeze and Dependency Map

Deliverables:

- Dedicated `bridge.traffic_to_hurl` compiler.
- Traffic filtering for static assets, analytics, irrelevant hosts, and large binary bodies.
- Session stitching for recorded user flows.
- State retention settings for `.entroping/state.db`.
- `freeze`.
- `map`.

Exit criteria:

- Captured secrets are redacted before persistence.
- Captured calls can be grouped into coherent freeze sessions.
- Local state growth is bounded.
- Freeze produces valid Hurl.
- Map exports Mermaid or Markdown.

### Phase 7: Studio

Deliverables:

- Textual app.
- Suite explorer.
- Last-run summary.
- Failure detail view.
- Traffic session list.

Exit criteria:

- `entroping studio --env local` opens and reads local state.
- It does not become required for CI or headless use.

## 3. Suggested First Milestone

The first milestone should include only:

- `init`
- `doctor`
- `run`
- QAnstitution parser
- Hurl runner
- gate injection
- condition parser
- JSON/JUnit reports

This gives the product its core proof: executable law enforced by Hurl.

## 4. Deferred Until After MVP

- Bruno import/compiler.
- Native gRPC streaming.
- WebSocket state machine testing.
- Hosted Cloud.
- Advanced policy approval workflows.
- Full visual dashboard.
- Complex condition DSL with arbitrary expressions.

## 5. Quality Gates for Implementation

- Unit tests for pure domain logic.
- Subprocess tests that do not require live APIs unless explicitly marked.
- Fixture-based Hurl validation.
- Security tests for path traversal and redaction.
- No direct HTTP execution in the runner.
- No provider-specific LLM SDKs.
- No secret logging.
- Bridge compilers stay separate: OpenAPI, traffic, policy, traceability, and merge logic must not collapse into one module.
