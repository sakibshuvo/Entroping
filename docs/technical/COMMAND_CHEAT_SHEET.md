# Entroping Command Cheat Sheet

**Version:** 4.1 Stable  
**Rule:** Use this command surface as the implementation and user-facing source of truth.

Compatibility audit: [CLI_COMPATIBILITY_AUDIT.md](CLI_COMPATIBILITY_AUDIT.md).

## Locked Alpha Surface

```text
entroping init [--minimal] [--github-actions]
entroping doctor [--ci] [--output <text|json>]
entroping config list
entroping config set --agent <builder|auditor|breaker> --model <model-id>
entroping config vendor-policy-pack --pack <path> [--name <dir>]
entroping config test-policy-pack --pack <path> [--output <text|json>]

entroping architect build [--new] [--changed-from <ref>] [--prompt <text>] [--strategy merge] [--tag <tag>] [--agent <builder|breaker>]
entroping architect refactor --target <glob> --prompt <text>
entroping architect audit [--focus <logic|auditor>] [--output <json|md>] [--changed-from <ref>]

entroping watch [--port <port>] [--target <url>] [--scope-host <host> ...] [--scope-url-prefix <url> ...]
entroping freeze --name <flow> [--golden] [--mock <service>] [--dry-run] [capture filters]
entroping map [--export <mermaid|dot|md|png>] [capture filters]

entroping studio [--env <name>]
entroping run [--env <name>] [--suite <name>] [--tag <tag>] [--tag-expression <expr>] [--operation-id <id>] [--ci] [--parallel] [--fail-fast] [--report <html|junit|json|drift> ...] [--drift-check] [--changed-from <ref>]
entroping report bug
entroping report failure-bundle [--output <directory>]
entroping report delta [--base <path>] [--current <path>] [--output <md|json>]
entroping report badges [--output <directory>] [--run-json <path>] [--policy-json <path>] [--openapi-json <path>] [--traceability-json <path>]
entroping report redaction [--output <md|html>]
entroping report policy [--output <md|json>]
entroping report gate-coverage [--output <md|json>]
entroping report gate-injection --target <path> [--output <md|json>]
entroping report artifact-manifest [--output <path>]
entroping report traceability [--output <md|json>]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
entroping report sarif [--output <path>] [--junit <path>] [--drift <path>] [--traceability]
entroping report promote-drift-baseline [--candidate <path>] [--output <path>]
entroping report review-summary [--output md] [--junit <path>] [--run-json <path>] [--drift <path>] [--traceability]
```

## Setup

Current alpha implementation supports `init`, `doctor`, `config list`,
`config set`, `config vendor-policy-pack`, and `config test-policy-pack`.
`init --github-actions` installs the reviewed GitHub Actions starter workflow
to `.github/workflows/entroping.yml` and refuses to overwrite an existing file.
`config set` updates `qanstitution.yaml`, creates a missing local persona
Markdown template, and does not store credentials or call model providers.
`config vendor-policy-pack` copies a reviewed local pack under `policy-packs/`,
validates its manifest and QAnstitution entrypoint, then appends a local import
without remote fetches or registry behavior. `config test-policy-pack` validates
a local pack before vendoring or publishing it, emits text or JSON pass/fail
evidence, and writes nothing to the consumer project. `doctor` validates any
configured agent persona files with the same safety rules used by Architect and
reports whether configured `api_key_env` names are present without printing
values or contacting providers. Add `--ci` to fail fast on CI-breaking setup
such as missing Hurl, unsafe report paths, invalid or empty suite manifests,
unresolved Hurl variables, or accidental assumptions that `run --ci` needs
model-provider access.

| Command | Purpose |
| --- | --- |
| `entroping init` | Create a standard Entroping project layout |
| `entroping init --minimal` | Create only the minimum required files |
| `entroping init --github-actions` | Install the reviewed GitHub Actions starter workflow |
| `entroping doctor` | Validate local setup, tools, config, and policies |
| `entroping doctor --output json` | Emit versioned machine-readable setup health |
| `entroping doctor --ci --output json` | Emit strict CI-readiness evidence without provider calls |
| `entroping config list` | Show effective non-secret configuration |
| `entroping config set --agent <name> --model <id>` | Configure model routing for an agent role |
| `entroping config vendor-policy-pack --pack <path>` | Vendor a reviewed local policy pack and append a local import |
| `entroping config test-policy-pack --pack <path>` | Validate a local policy pack without writing files |

Examples:

```bash
entroping init
entroping init --minimal --github-actions
entroping doctor
entroping config list
entroping config set --agent auditor --model openai/auditor-model
entroping config test-policy-pack --pack ../entroping-policy-pack-api-baseline --output json
entroping config vendor-policy-pack --pack ../entroping-policy-pack-api-baseline --name api-baseline
```

## Architect

Current alpha implementation supports deterministic `architect build --new` from a local
OpenAPI file configured at `sources.spec` in `qanstitution.yaml`, focused
OpenAPI regeneration with `architect build --new --changed-from <ref>`,
prompt-backed `architect build --prompt`, Breaker-backed hostile prompt
generation through `architect build --agent breaker --prompt`, deterministic
`architect audit --focus logic`, Auditor-backed `architect audit --focus auditor`,
and prompt-backed `architect refactor` for Architect-owned Hurl files and manual
files with explicit managed blocks. Prompt-backed `architect build --strategy
merge` is available for existing Hurl targets. Successful prompt-backed
Builder, Breaker, refactor, merge, and Auditor review runs write value-free
manifests under `.entroping/agent-runs/` with provider, latency, token, and
configured cost-estimate evidence. Remote specs remain planned.
For OpenAPI operations with security requirements and an explicit `401` or
`403` response, `architect build --new` also emits auth-negative tests under
`tests/generated/security/` for supported HTTP bearer/basic and API-key
header/query/cookie schemes. Unsupported security schemes are warning findings,
not guessed tests.

| Command | Purpose |
| --- | --- |
| `entroping architect build --new` | Generate new Hurl tests from configured sources |
| `entroping architect build --new --changed-from <ref>` | Generate only current OpenAPI operations changed from a Git base ref |
| `entroping architect build --prompt "<text>"` | Generate scoped tests from natural language |
| `entroping architect build --agent breaker --prompt "<text>"` | Generate hostile negative/security tests with the Breaker persona |
| `entroping architect build --strategy merge` | Merge generated changes into existing tests |
| `entroping architect build --tag <tag>` | Add a tag to generated tests |
| `entroping architect refactor --target <glob> --prompt "<text>"` | Safely update existing Hurl tests |
| `entroping architect audit --focus logic` | Audit OpenAPI coverage gaps and, when redacted traffic exists, undocumented live routes |
| `entroping architect audit --changed-from <ref>` | Report deterministic OpenAPI breaking-change diffs from a Git base ref without generating tests |
| `entroping architect audit --focus auditor` | Run an explicit Auditor model review of coverage and policy risk |
| `entroping architect audit --output <json|md>` | Select audit output format |
| `.entroping/agent-runs/*.json` | Local value-free evidence for prompt-backed Architect runs |

Examples:

```bash
entroping architect build --new --tag smoke
entroping architect build --new --changed-from origin/main --tag smoke
entroping architect build --prompt "Add checkout smoke coverage" --tag ai
entroping architect build --agent breaker --prompt "Generate hostile auth bypass tests" --tag security
entroping architect build --strategy merge --prompt "Cover the new refund endpoint"
entroping architect refactor --target "tests/payments/*.hurl" --prompt "Add X-Tenant-Id header"
entroping architect audit --focus logic --output md
entroping architect audit --focus logic --changed-from origin/main --output json
entroping architect audit --focus auditor --output json
```

Logic audit output includes covered, uncovered, and ambiguous operation rows
plus stale committed `operation_id` references. If redacted Eye traffic state
exists, it also reports documented observed routes, undocumented observed
routes, and spec-only OpenAPI operations without raw query strings, headers,
cookies, bodies, or captured values. JSON output uses
`schema_version: entroping.openapi-audit.v1` with an optional nested
`entroping.traffic-openapi-audit.v1` route section. With
`--changed-from <ref>`, the same audit also attaches
`entroping.openapi-breaking-diff.v1` findings for removed operations, changed
status codes, newly required inputs, and practical JSON response-shape changes.

## Observation

Current alpha implementation supports capture-only `watch`, basic Hurl
generation through `freeze --name <flow> [--golden]`, and dependency map export
through `map --export mermaid|dot|md|png`. `freeze --mock <service>` writes
WireMock-compatible mappings from redacted dependency traffic. Written Hurl,
WireMock, and PNG dependency-map artifacts also get value-free approval
manifests under `reports/approvals/` with checksums, source fingerprints, and
counts-only redaction summaries. PNG map rendering uses local Graphviz `dot`
when it is available. `freeze --dry-run` previews selected records, output
paths, golden status, and redaction categories without writing tests, mocks, or
approval manifests. `freeze`, `freeze --mock`, and `map` accept repeatable
capture filters:

- `--include-host` / `--exclude-host`
- `--include-method` / `--exclude-method`
- `--include-path` / `--exclude-path`

Include filters narrow the capture by host, method, and path; exclude filters
win. Host filters are exact, methods are normalized, and path filters match the
request path only, not query strings, headers, cookies, or bodies.

`watch` itself requires an explicit capture scope before persistence starts.
Use `--target` for the primary local service origin, repeat `--scope-host` for
additional host names, or repeat `--scope-url-prefix` for absolute URL prefixes.
Out-of-scope and malformed flow URLs are ignored before persistence, and the
watch summary reports only counts.

| Command | Purpose |
| --- | --- |
| `entroping watch --port <port> --target <url>` | Start local mitmproxy recorder for one target origin |
| `entroping watch --target <url>` | Define upstream target for observation |
| `entroping watch --scope-host <host>` | Capture only this host name |
| `entroping watch --scope-url-prefix <url>` | Capture only this absolute URL prefix |
| `entroping freeze --name <flow>` | Convert captured session into Hurl tests |
| `entroping freeze --golden` | Add golden master assertions |
| `entroping freeze --mock <service>` | Generate WireMock mappings for a dependency |
| `entroping freeze --dry-run` | Preview generated Hurl or WireMock artifacts without writing files |
| `entroping freeze --include-host <host>` | Freeze only traffic for a captured host |
| `entroping freeze --exclude-path <path>` | Remove noisy request paths before artifact generation |
| `entroping map --export <fmt>` | Export dependency map |
| `entroping map --include-method <method>` | Map only matching HTTP methods |
| `reports/approvals/*.json` | Local approval manifests for written traffic-derived artifacts |

Examples:

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name checkout_flow --golden --dry-run
entroping freeze --name checkout_flow --golden
entroping freeze --name checkout_flow --include-host api.example.test --exclude-path "/assets/*"
entroping freeze --name refund_flow --mock payments
entroping map --export mermaid --include-host api.example.test
```

## Execution

Current alpha implementation supports deterministic `run`, `--env`, `--suite`,
`--tag`, `--tag-expression`, `--operation-id`, `--ci`, bounded `--parallel`, `--fail-fast`, `--drift-check`,
`--report html`, `--report json`, `--report junit`, `--report drift`, and
`--changed-from <ref>` for changed Hurl files from Git diff. Before invoking Hurl, `run` checks
selected execution copies for unresolved `{{variable}}` references and reports
missing variable names without printing values.

| Command | Purpose |
| --- | --- |
| `entroping studio --env <name>` | Open read-only local Studio TUI |
| `entroping run --env <name>` | Run tests with environment variables |
| `entroping run --suite <name>` | Run a committed suite manifest from `suites/<name>.yaml` |
| `entroping run --tag <tag>` | Run tests matching a tag |
| `entroping run --tag-expression <expr>` | Run tests matching a boolean tag expression such as `smoke and not slow` |
| `entroping run --operation-id <id>` | Run tests with matching OpenAPI `operation_id` metadata; repeat for multiple operations |
| `entroping run --ci` | Strict CI mode |
| `entroping run --parallel` | Bounded parallel execution |
| `entroping run --fail-fast` | Stop scheduling after the first failing Hurl result |
| `entroping run --report <html|junit|json|drift>` | Write report artifact; repeat for multiple formats |
| `entroping run --drift-check` | Compare runtime behavior against baseline |
| `entroping run --changed-from <ref>` | Fast local run for existing changed `.hurl` files |

Every `entroping run` writes `.entroping/latest-run-events.jsonl`, a sanitized
JSONL progress log with schema `entroping.run-events.v1`. It records run start,
selected tests, redacted result events, artifact writes, no-match or error
events, and completion status for CI wrappers and coding agents.

Examples:

```bash
entroping studio --env local
entroping run --suite smoke --ci
entroping run --env local --tag smoke --report html --report json --report junit
entroping run --tag-expression "smoke and not slow" --report json
entroping run --operation-id createCheckout --operation-id createRefund --report json
entroping run --changed-from origin/main --tag smoke
entroping run --tag smoke --fail-fast --report json
entroping run --env ci --ci --parallel --report junit
entroping run --env staging --drift-check --report drift
```

`--suite <name>` reads `suites/<name>.yaml` with schema version
`entroping.suite.v1`. Suite manifests can define `env`, `tags`, `paths`,
`reports`, `parallel`, `fail_fast`, and `drift_check`. Suite paths are root-bounded local
globs. `--suite` cannot be combined with ad hoc run selectors such as `--env`,
`--tag`, `--tag-expression`, `--operation-id`, `--report`, `--parallel`, `--fail-fast`, `--drift-check`, or
`--changed-from`; keep `--ci` for strict exit behavior. `--tag-expression`
supports `and`, `or`, `not`, and parentheses over Entroping metadata tags. It
cannot be combined with repeatable `--tag`; use `--tag` for simple OR selection
and `--tag-expression` for ad hoc boolean selection.

`--operation-id` selects existing committed `.hurl` files by exact
`# entroping: operation_id=<id>` metadata. It is repeatable, reports
selected/skipped counts, records operation IDs in run reports, and cannot be
combined with `--tag`, `--tag-expression`, `--suite`, or `--changed-from`.

`--changed-from` is a developer and agent feedback shortcut. Keep full-suite
`entroping run --ci` as the release gate.

Run reports include per-test `timeout_ms` evidence. Hurl subprocess timeouts
use status `timeout`, exit code `124`, a timeout-specific JUnit failure type,
and review-summary timeout findings.

`--report drift` writes both `reports/drift.json` and, when the Hurl suite
passes, `reports/drift-baseline.candidate.json`. Review the candidate before
promoting it to `.entroping/drift-baseline.json`.

Variables can come from `envs/<name>.env`, explicit shell
`HURL_VARIABLE_<name>` entries, Hurl `[Options] variable` entries, or captures.

## Reporting

| Command | Purpose |
| --- | --- |
| `entroping report bug` | Generate a Markdown bug report from the latest failure |
| `entroping report failure-bundle` | Write a sanitized issue handoff bundle to `reports/failure-bundle/manifest.json` |
| `entroping report delta --base <path> --current <path>` | Compare two JSON run reports and emit deterministic Markdown or JSON delta output |
| `entroping report badges` | Write local Shields endpoint JSON badges to `reports/badges/` |
| `entroping report redaction --output md` | Write a counts-only captured-traffic redaction review to `reports/redaction-review.md` |
| `entroping report redaction --output html` | Write a browser-readable redaction review to `reports/redaction-review.html` |
| `entroping report policy --output md` | Write effective QAnstitution gate provenance to `reports/effective-policy.md` |
| `entroping report policy --output json` | Write machine-readable effective policy evidence to `reports/effective-policy.json` |
| `entroping report gate-coverage --output md` | Write a policy gate coverage matrix to `reports/gate-coverage.md` |
| `entroping report gate-coverage --output json` | Write machine-readable gate coverage evidence to `reports/gate-coverage.json` |
| `entroping report gate-injection --target <path>` | Explain selected-file gate injection without running Hurl or mutating sources |
| `entroping report artifact-manifest` | Write checksum evidence for local report artifacts to `reports/artifact-manifest.json` |
| `entroping report traceability --output md` | Generate a local Markdown story/test traceability report |
| `entroping report traceability --output json` | Emit machine-readable traceability JSON for badges or downstream tools |
| `entroping report github-annotations` | Emit GitHub Actions workflow-command annotations from local reports |
| `entroping report sarif` | Write SARIF 2.1.0 code-scanning evidence to `reports/entroping.sarif` |
| `entroping report promote-drift-baseline` | Promote a reviewed drift baseline candidate into `.entroping/drift-baseline.json` |
| `entroping report review-summary --output md` | Write a provider-neutral Markdown review summary to `reports/review-summary.md` |

Example:

```bash
entroping report bug
entroping report failure-bundle
entroping report delta --base reports/run-base.json --current reports/run-latest.json
entroping report badges
entroping report redaction --output md
entroping report policy --output md
entroping report gate-coverage --output md
entroping report gate-injection --target tests/health.hurl --output md
entroping report artifact-manifest
entroping report traceability --output md
entroping report traceability --output json > reports/traceability.json
entroping report github-annotations --traceability
entroping report sarif --traceability
entroping report promote-drift-baseline
entroping report review-summary --traceability
```

Run artifacts are produced by repeatable `entroping run --report <html|junit|json|drift>` flags. The older `entroping report --type <fmt>` wording from the Gemini transcript is not the v4.1 primary contract.

## Common Workflows

### New API

```bash
entroping init
entroping architect build --new --tag smoke
entroping run --tag smoke --report json --report junit
```

### Legacy API

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name checkout_flow --golden
entroping run --env local --tag regression --report html
```

### CI Gate

```bash
entroping doctor
entroping run --env ci --ci --parallel --report junit
```

### Security Expansion

```bash
entroping architect build --agent breaker --prompt "Generate hostile tests for auth bypass and IDOR" --tag security
entroping run --env local --tag security --report html
```

## Deprecated or Non-Primary Names

Do not document these as primary v4.1 commands:

| Name | Replacement |
| --- | --- |
| `gen` | `architect build` |
| `fix` | `architect refactor` |
| `ui` | `studio` |
| `scan` | `architect audit` |
| `chaos` | `architect build --agent breaker --prompt "<breaker intent>"` |
| `verify` | `run` |
| `explain` | Reports and audit output |
| top-level `build` | `architect build` |
| `report --type` | `run --report` or `report bug` |
| `auth` | Future credential UX; MVP uses env vars or OS credential storage |
| `--verbose` | Future global flag only after spec update |
| `freeze --dry-run` | Preview selected freeze artifacts without writing files |
