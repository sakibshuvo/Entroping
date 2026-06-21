# Entroping Command Cheat Sheet

**Command Surface Version:** 4.1
**Maturity:** Locked Alpha; stable-core compatibility is not promised until the graduation blockers close.
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
entroping architect refactor --target <glob> --prompt <text> [--preview]
entroping architect audit [--focus <logic|auditor>] [--output <json|md>] [--changed-from <ref>]

entroping watch [--port <port>] [--target <url>] [--scope-host <host> ...] [--scope-url-prefix <url> ...]
entroping freeze --name <flow> [--golden] [--mock <service>] [--dry-run] [capture filters]
entroping map [--export <mermaid|dot|md|png>] [capture filters]

entroping studio [--env <name>]
entroping run [--env <name>] [--suite <name>] [--tag <tag>] [--tag-expression <expr>] [--operation-id <id>] [--ci] [--parallel] [--fail-fast] [--dry-run] [--report <html|junit|json|drift> ...] [--drift-check] [--changed-from <ref>] [--rerun-failures]
entroping report bug
entroping report failure-bundle [--output <directory>]
entroping report delta [--base <path>] [--current <path>] [--output <md|json>]
entroping report badges [--output <directory>] [--run-json <path>] [--policy-json <path>] [--openapi-json <path>] [--traceability-json <path>]
entroping report redaction [--output <md|html>] [--fail-on-unsafe]
entroping report capture-summary [--output <md|json>] [--fail-on-unredacted]
entroping report policy [--output <md|json>]
entroping report policy-diff [--base <path>] [--current <path>] [--output <md|json>] [--fail-on-change]
entroping report gate-coverage [--output <md|json>] [--fail-under <0-100>]
entroping report gate-injection --target <path> [--output <md|json>]
entroping report test-quality [--output <md|json>] [--fail-under <0-100>]
entroping report test-pyramid [--output <md|json>]
entroping report external-test-evidence [--output <md|json>]
entroping report artifact-manifest [--output <path>] [--fail-on-incomplete]
entroping report evidence-bundle [--output <path>]
entroping report design-partner-feedback [--output <path>]
entroping report runtime-card [--output <md|json>]
entroping report handoff [--output <md|json>] [--fail-on-insufficient]
entroping report notification-packet [--output <md|json>]
entroping report team-evidence-readiness [--output <md|json>]
entroping report team-access-control-plan [--output <md|json>]
entroping report integration-readiness [--output <md|json>]
entroping report devex-readiness [--output <md|json>]
entroping report evidence-cloud-readiness [--output <md|json>]
entroping report evidence-cloud-export [--output <md|json>]
entroping report evidence-cloud-workspace --manifest <path> [--output <md|json>]
entroping report evidence-links [--output <md|json>]
entroping report evidence-portal [--output <html|json>]
entroping report pr-evidence-card [--output <md|json>]
entroping report evidence-action-plan [--output <md|json>]
entroping report work-item-draft [--output <md|json>]
entroping report work-item-import-bundle [--output <json|csv>]
entroping report connector-intent [--output <md|json>]
entroping report observability-packet [--output <md|json>]
entroping report api-inventory [--output <md|json>]
entroping report mutation-readiness [--output <md|json>]
entroping report evidence-index [--output <md|json>]
entroping report qa-brain-seed [--output <md|json>]
entroping report qa-brain-eval-plan [--output <md|json>]
entroping report qa-brain-retrieval-plan [--output <md|json>]
entroping report qa-brain-prompt-plan [--output <md|json>]
entroping report qa-brain-fine-tune-readiness [--output <md|json>]
entroping report qa-brain-model-packaging-plan [--output <md|json>]
entroping report qa-brain-routing-plan [--output <md|json>]
entroping report pilot-metrics [--output <md|json>]
entroping report agent-bundle [--output <md|json>] [--role <builder|auditor|breaker>] [--scope <path>]
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
values or contacting providers. It also runs `hurl --version` locally and
reports whether the installed Hurl is compatible with Entroping's 4.3.0+
minimum, missing, unsupported, or unparsable; the reviewed CI examples pin Hurl
8.0.1. Add `--ci` to fail fast on CI-breaking setup such as missing or
unsupported Hurl, unsafe report paths, invalid or empty suite manifests,
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
`architect refactor --preview` validates the proposed Hurl edits and prints a
unified diff without writing target files. Treat it as review evidence, not
execution proof; run the affected Hurl tests or the full suite before merging.
For OpenAPI operations with security requirements and an explicit `401` or
`403` response, `architect build --new` also emits auth-negative tests under
`tests/generated/security/` for supported HTTP bearer/basic and API-key
header/query/cookie schemes. Unsupported security schemes are warning findings,
not guessed tests. Auth-negative files carry `negative_category=invalid-auth`,
`severity`, and safety metadata too.
For JSON request bodies with explicit `400` or `422` responses, it also emits
bounded negative-path Hurl under `tests/generated/negative/` for malformed JSON,
schema violations, boundary values, SQLi-like strings, and IDOR-style path
variants. These files are committed/reviewable Hurl with `negative_category`,
`severity`, category tags, and safety metadata; mutating generated negatives are
`safety=destructive` and protected runs block them before Hurl execution.

| Command | Purpose |
| --- | --- |
| `entroping architect build --new` | Generate new Hurl tests from configured sources |
| `entroping architect build --new --changed-from <ref>` | Generate only current OpenAPI operations changed from a Git base ref |
| `entroping architect build --prompt "<text>"` | Generate scoped tests from natural language |
| `entroping architect build --agent breaker --prompt "<text>"` | Generate hostile negative/security tests with the Breaker persona |
| `entroping architect build --strategy merge` | Merge generated changes into existing tests |
| `entroping architect build --tag <tag>` | Add a tag to generated tests |
| `entroping architect refactor --target <glob> --prompt "<text>"` | Safely update existing Hurl tests |
| `entroping architect refactor --target <glob> --prompt "<text>" --preview` | Preview validated Hurl edits as a unified diff without writing target files |
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
entroping architect refactor --target "tests/payments/*.hurl" --prompt "Add X-Tenant-Id header" --preview
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
`--tag`, `--tag-expression`, `--operation-id`, `--ci`, bounded `--parallel`, `--fail-fast`, `--dry-run`, `--drift-check`,
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
| `entroping run --dry-run` | Preview selected tests, gates, variables, and reports without running Hurl |
| `entroping run --report <html|junit|json|drift>` | Write report artifact; repeat for multiple formats |
| `entroping run --drift-check` | Compare runtime behavior against baseline |
| `entroping run --changed-from <ref>` | Fast local run for existing changed `.hurl` files |
| `entroping run --rerun-failures` | Fast local rerun of failed files from the latest local run report |

Every `entroping run` writes `.entroping/latest-run-events.jsonl`, a sanitized
JSONL progress log with schema `entroping.run-events.v1`. It records run start,
selected tests, redacted result events, artifact writes, no-match or error
events, and completion status for CI wrappers and coding agents. Concurrent
runs in the same project root fail fast before Hurl execution instead of
interleaving latest-run event evidence.

Examples:

```bash
entroping studio --env local
entroping run --suite smoke --ci
entroping run --env local --tag smoke --report html --report json --report junit
entroping run --tag-expression "smoke and not slow" --report json
entroping run --operation-id createCheckout --operation-id createRefund --report json
entroping run --changed-from origin/main --tag smoke
entroping run --rerun-failures --report json
entroping run --tag smoke --fail-fast --report json
entroping run --dry-run --tag smoke --report json
entroping run --env ci --ci --parallel --report junit
entroping run --env staging --drift-check --report drift
```

`entroping studio` includes a read-only evidence viewer for sanitized local
report artifacts. It uses stable evidence IDs such as `run-json`,
`capture-summary-json`, `test-quality-json`, and `runtime-card-json`, shows controlled
schema/count metadata, and does not render raw report contents, upload
artifacts, or edit tests, QAnstitution, reports, traffic state, or runtime
state.

`--suite <name>` reads `suites/<name>.yaml` with schema version
`entroping.suite.v1`. Suite manifests can define `env`, `tags`, `paths`,
`reports`, `parallel`, `fail_fast`, `drift_check`, `protected`, and `safety`.
Suite paths are root-bounded local globs. `protected: true` forces the
protected-environment safety preflight, and `safety` can default selected tests
to `read-only`, `idempotent`, `teardown-backed`, or `destructive`. `--suite`
cannot be combined with ad hoc run selectors such as `--env`, `--tag`,
`--tag-expression`, `--operation-id`, `--report`, `--parallel`, `--fail-fast`,
`--drift-check`, `--changed-from`, or `--rerun-failures`; keep `--ci` for
strict exit behavior. `--tag-expression`
supports `and`, `or`, `not`, and parentheses over Entroping metadata tags. It
cannot be combined with repeatable `--tag`; use `--tag` for simple OR selection
and `--tag-expression` for ad hoc boolean selection.

`--operation-id` selects existing committed `.hurl` files by exact
`# entroping: operation_id=<id>` metadata. It is repeatable, reports
selected/skipped counts, records operation IDs in run reports, and cannot be
combined with `--tag`, `--tag-expression`, `--suite`, `--changed-from`, or
`--rerun-failures`.

`--rerun-failures` reads `reports/run-latest.json` first, then
`.entroping/latest-run.json`, selects failed source `.hurl` files that still
exist, and reruns them through the normal deterministic run workflow. It reuses
the report environment unless `--env` is provided. It cannot be combined with
`--tag`, `--tag-expression`, `--operation-id`, `--suite`, or `--changed-from`.

`--changed-from` and `--rerun-failures` are developer and agent feedback
shortcuts. Keep full-suite `entroping run --ci` as the release gate.

`--dry-run` prints a deterministic execution plan without invoking Hurl, writing
`.entroping/latest-run.json`, writing execution events, or producing executed
run reports. It still loads QAnstitution, resolves selectors, previews
temporary gate injection counts, and checks variable availability. If
`--report json` is included, dry-run writes `reports/run-plan.json` with schema
`entroping.run-plan.v1`; requested run report paths remain listed as
`would_write` evidence only.

Run reports include per-test `timeout_ms` evidence. Hurl subprocess timeouts
use status `timeout`, exit code `124`, a timeout-specific JUnit failure type,
and review-summary timeout findings.

`--report drift` writes both `reports/drift.json` and, when the Hurl suite
passes, `reports/drift-baseline.candidate.json`. Review the candidate before
promoting it to `.entroping/drift-baseline.json`.

Variables can come from `envs/<name>.env`, explicit shell
`HURL_VARIABLE_<name>` entries, Hurl `[Options] variable` entries, or captures.

## Reporting

`entroping report --help` groups commands by launch readiness and audience:
first-hour handoff commands appear under `Launch-Critical Reports`, durable
local evidence commands under `Stable Public Reports`, operator/debug commands
under `Maintainer And Baseline Tools`, and design-partner pilot evidence under
`Experimental Design-Partner Evidence`. The command names remain stable; the
grouping is only a discovery aid.

Launch-critical report commands:

| Command | Purpose |
| --- | --- |
| `entroping report bug` | Generate a Markdown bug report from the latest failure |
| `entroping report failure-bundle` | Write a sanitized issue handoff bundle to `reports/failure-bundle/manifest.json` |
| `entroping report runtime-card` | Write a concise PR/runtime evidence card to `reports/runtime-card.md` |
| `entroping report review-summary --output md` | Write a provider-neutral Markdown review summary to `reports/review-summary.md` |

Stable public report commands:

| Command | Purpose |
| --- | --- |
| `entroping report delta --base <path> --current <path>` | Compare two JSON run reports and emit deterministic Markdown or JSON delta output |
| `entroping report redaction --output md` | Write a counts-only captured-traffic redaction review to `reports/redaction-review.md` |
| `entroping report redaction --output html` | Write a browser-readable redaction review to `reports/redaction-review.html` |
| `entroping report redaction --fail-on-unsafe` | Write the report, then exit `1` when redaction evidence contains unredacted or low-confidence records |
| `entroping report capture-summary --output md` | Write a safe captured-traffic session summary to `reports/capture-summary.md` |
| `entroping report capture-summary --output json` | Write machine-readable capture summary evidence to `reports/capture-summary.json` |
| `entroping report capture-summary --fail-on-unredacted` | Write the report, then exit `1` when capture evidence contains unredacted records |
| `entroping report policy --output md` | Write effective QAnstitution gate provenance to `reports/effective-policy.md` |
| `entroping report policy --output json` | Write machine-readable effective policy evidence to `reports/effective-policy.json` |
| `entroping report policy-diff --base <path> --current <path>` | Compare two effective-policy JSON artifacts and emit Markdown or JSON to stdout; add `--fail-on-change` to make effective-policy drift fail CI |
| `entroping report gate-coverage --output md` | Write a policy gate coverage matrix to `reports/gate-coverage.md` |
| `entroping report gate-coverage --output json` | Write machine-readable gate coverage evidence to `reports/gate-coverage.json` |
| `entroping report gate-coverage --fail-under <0-100>` | Write the report, then exit `1` when matched-gate coverage is below the reviewed threshold |
| `entroping report traceability --output md` | Generate a local Markdown story/test traceability report |
| `entroping report traceability --output json` | Emit machine-readable traceability JSON for badges or downstream tools |
| `entroping report github-annotations` | Emit GitHub Actions workflow-command annotations from local reports |
| `entroping report sarif` | Write SARIF 2.1.0 code-scanning evidence to `reports/entroping.sarif` |

Maintainer and baseline tools:

| Command | Purpose |
| --- | --- |
| `entroping report badges` | Write local Shields endpoint JSON badges to `reports/badges/` |
| `entroping report gate-injection --target <path>` | Explain selected-file gate injection without running Hurl or mutating sources |
| `entroping report test-quality --output md` | Write a static generated-Hurl quality score to `reports/test-quality.md` |
| `entroping report test-quality --output json` | Write machine-readable generated-Hurl quality evidence to `reports/test-quality.json` |
| `entroping report test-quality --fail-under <0-100>` | Write the report, then exit `1` when the generated-test quality score is below the reviewed threshold |
| `entroping report test-pyramid --output md` | Write a local test-pyramid evidence summary to `reports/test-pyramid.md` |
| `entroping report test-pyramid --output json` | Write machine-readable test-pyramid evidence to `reports/test-pyramid.json` |
| `entroping report external-test-evidence --output md` | Write a counts-only external test evidence packet to `reports/external-test-evidence.md` |
| `entroping report external-test-evidence --output json` | Write machine-readable external test evidence metadata to `reports/external-test-evidence.json` |
| `entroping report artifact-manifest` | Write checksum evidence for local report artifacts to `reports/artifact-manifest.json` |
| `entroping report artifact-manifest --output <path>` | Write checksum evidence for local report artifacts to a custom manifest path |
| `entroping report artifact-manifest --fail-on-incomplete` | Write the manifest, then exit `1` when expected artifacts are missing or audit verification is broken |
| `entroping report promote-drift-baseline` | Promote a reviewed drift baseline candidate into `.entroping/drift-baseline.json` |

Experimental design-partner evidence commands:

| Command | Purpose |
| --- | --- |
| `entroping report evidence-bundle` | Write a sanitized local design-partner upload-readiness bundle to `reports/evidence-bundle.json` |
| `entroping report design-partner-feedback` | Write a sanitized local design-partner feedback template to `reports/design-partner-feedback.json` |
| `entroping report handoff --output md` | Write a local cross-surface evidence handoff packet to `reports/handoff.md` |
| `entroping report handoff --output json` | Write machine-readable cross-surface handoff evidence to `reports/handoff.json` |
| `entroping report handoff --fail-on-insufficient` | Write the handoff packet, then exit `1` when no source evidence artifacts are present |
| `entroping report notification-packet --output md` | Write a read-only work-management/chat notification packet to `reports/notification-packet.md` |
| `entroping report notification-packet --output json` | Write machine-readable notification evidence to `reports/notification-packet.json` |
| `entroping report team-evidence-readiness --output md` | Write read-only team evidence cloud readiness to `reports/team-evidence-readiness.md` |
| `entroping report team-evidence-readiness --output json` | Write machine-readable team evidence readiness to `reports/team-evidence-readiness.json` |
| `entroping report team-access-control-plan --output md` | Write a local team access-control and audit plan to `reports/team-access-control-plan.md` |
| `entroping report team-access-control-plan --output json` | Write machine-readable team access-control plan metadata to `reports/team-access-control-plan.json` |
| `entroping report integration-readiness --output md` | Write a local integration-readiness packet to `reports/integration-readiness.md` |
| `entroping report integration-readiness --output json` | Write machine-readable integration readiness metadata to `reports/integration-readiness.json` |
| `entroping report devex-readiness --output md` | Write a local developer experience readiness packet to `reports/devex-readiness.md` |
| `entroping report devex-readiness --output json` | Write machine-readable developer experience readiness metadata to `reports/devex-readiness.json` |
| `entroping report evidence-cloud-readiness --output md` | Write a local Evidence Cloud readiness packet to `reports/evidence-cloud-readiness.md` |
| `entroping report evidence-cloud-readiness --output json` | Write machine-readable Evidence Cloud readiness metadata to `reports/evidence-cloud-readiness.json` |
| `entroping report evidence-cloud-export --output md` | Write a local Evidence Cloud export manifest to `reports/evidence-cloud-export.md` |
| `entroping report evidence-cloud-export --output json` | Write machine-readable Evidence Cloud export metadata to `reports/evidence-cloud-export.json` |
| `entroping report evidence-cloud-workspace --manifest reports/evidence-cloud-export.json` | Write a local Evidence Cloud workspace packet |
| `entroping report evidence-cloud-dashboard --manifest <path> [--output <html|json>]` | Write a static local Evidence Cloud workspace dashboard |
| `entroping report evidence-links --output md` | Write a local cross-surface evidence links packet to `reports/evidence-links.md` |
| `entroping report evidence-links --output json` | Write machine-readable evidence links metadata to `reports/evidence-links.json` |
| `entroping report evidence-portal --output html` | Write a static local evidence portal dashboard to `reports/evidence-portal.html` |
| `entroping report evidence-portal --output json` | Write machine-readable evidence portal metadata to `reports/evidence-portal.json` |
| `entroping report pr-evidence-card --output md` | Write local PR evidence card Markdown |
| `entroping report pr-evidence-card --output json` | Write machine-readable PR evidence card JSON |
| `entroping report evidence-action-plan --output md` | Write local prioritized evidence action-plan Markdown |
| `entroping report evidence-action-plan --output json` | Write machine-readable evidence action-plan JSON |
| `entroping report work-item-draft --output md` | Write local read-only work item draft Markdown |
| `entroping report work-item-draft --output json` | Write machine-readable work item draft JSON |
| `entroping report work-item-import-bundle --output json` | Write machine-readable tracker import bundle JSON |
| `entroping report work-item-import-bundle --output csv` | Write spreadsheet-safe tracker import bundle CSV |
| `entroping report connector-intent --output md` | Write a local connector-intent packet to `reports/connector-intent.md` |
| `entroping report connector-intent --output json` | Write machine-readable connector intent metadata to `reports/connector-intent.json` |
| `entroping report observability-packet --output md` | Write a read-only observability signal packet to `reports/observability-packet.md` |
| `entroping report observability-packet --output json` | Write machine-readable observability evidence to `reports/observability-packet.json` |
| `entroping report api-inventory --output md` | Write a read-only API surface inventory to `reports/api-inventory.md` |
| `entroping report api-inventory --output json` | Write machine-readable API style evidence to `reports/api-inventory.json` |
| `entroping report mutation-readiness --output md` | Write a read-only mutation/fuzz readiness summary to `reports/mutation-readiness.md` |
| `entroping report mutation-readiness --output json` | Write machine-readable mutation/fuzz readiness evidence to `reports/mutation-readiness.json` |
| `entroping report evidence-index --output md` | Write a read-only local evidence artifact index to `reports/evidence-index.md` |
| `entroping report evidence-index --output json` | Write machine-readable evidence artifact index metadata to `reports/evidence-index.json` |
| `entroping report qa-brain-seed --output md` | Write read-only QA Brain seed metadata to `reports/qa-brain-seed.md` |
| `entroping report qa-brain-seed --output json` | Write machine-readable QA Brain seed metadata to `reports/qa-brain-seed.json` |
| `entroping report qa-brain-eval-plan --output md` | Write read-only QA Brain eval-plan metadata to `reports/qa-brain-eval-plan.md` |
| `entroping report qa-brain-eval-plan --output json` | Write machine-readable QA Brain eval-plan metadata to `reports/qa-brain-eval-plan.json` |
| `entroping report qa-brain-retrieval-plan --output md` | Write read-only QA Brain retrieval-plan metadata to `reports/qa-brain-retrieval-plan.md` |
| `entroping report qa-brain-retrieval-plan --output json` | Write machine-readable QA Brain retrieval-plan metadata to `reports/qa-brain-retrieval-plan.json` |
| `entroping report qa-brain-prompt-plan --output md` | Write read-only QA Brain prompt-plan metadata to `reports/qa-brain-prompt-plan.md` |
| `entroping report qa-brain-prompt-plan --output json` | Write machine-readable QA Brain prompt-plan metadata to `reports/qa-brain-prompt-plan.json` |
| `entroping report qa-brain-fine-tune-readiness --output md` | Write read-only QA Brain fine-tune readiness metadata to `reports/qa-brain-fine-tune-readiness.md` |
| `entroping report qa-brain-fine-tune-readiness --output json` | Write machine-readable QA Brain fine-tune readiness metadata to `reports/qa-brain-fine-tune-readiness.json` |
| `entroping report qa-brain-model-packaging-plan --output md` | Write read-only QA Brain model-packaging plan metadata to `reports/qa-brain-model-packaging-plan.md` |
| `entroping report qa-brain-model-packaging-plan --output json` | Write machine-readable QA Brain model-packaging plan metadata to `reports/qa-brain-model-packaging-plan.json` |
| `entroping report qa-brain-routing-plan --output md` | Write read-only QA Brain routing-plan metadata to `reports/qa-brain-routing-plan.md` |
| `entroping report qa-brain-routing-plan --output json` | Write machine-readable QA Brain routing-plan metadata to `reports/qa-brain-routing-plan.json` |
| `entroping report pilot-metrics --output md` | Write local design-partner pilot metric inference to `reports/pilot-metrics.md` |
| `entroping report pilot-metrics --output json` | Write machine-readable pilot metric inference to `reports/pilot-metrics.json` |
| `entroping report agent-bundle --output md` | Write a local multi-agent review bundle to `reports/agent-bundle.md` |
| `entroping report agent-bundle --output json` | Write machine-readable Builder/Breaker/Auditor evidence to `reports/agent-bundle.json` |

Example:

```bash
entroping report bug
entroping report failure-bundle
entroping report delta --base reports/run-base.json --current reports/run-latest.json
entroping report badges
entroping report redaction --output md
entroping report redaction --fail-on-unsafe
entroping report capture-summary --output md
entroping report capture-summary --output json --fail-on-unredacted
entroping report policy --output md
entroping report policy-diff --base reports/base-effective-policy.json --current reports/effective-policy.json
entroping report policy-diff --base reports/base-effective-policy.json --current reports/effective-policy.json --fail-on-change
entroping report gate-coverage --output md
entroping report gate-coverage --output json --fail-under 80
entroping report gate-injection --target tests/health.hurl --output md
entroping report test-quality --output md
entroping report test-quality --output json --fail-under 80
entroping report test-pyramid --output md
entroping report test-pyramid --output json
entroping report external-test-evidence --output json
entroping report artifact-manifest
entroping report artifact-manifest --fail-on-incomplete
entroping report evidence-bundle
entroping report design-partner-feedback
entroping report runtime-card
entroping report handoff --output json
entroping report handoff --fail-on-insufficient
entroping report notification-packet --output json
entroping report team-evidence-readiness --output json
entroping report team-access-control-plan --output json
entroping report integration-readiness --output json
entroping report devex-readiness --output json
entroping report evidence-cloud-readiness --output json
entroping report evidence-cloud-export --output json
entroping report evidence-links --output json
entroping report evidence-portal --output json
entroping report pr-evidence-card --output json
entroping report evidence-action-plan --output json
entroping report work-item-draft --output json
entroping report work-item-import-bundle --output csv
entroping report connector-intent --output json
entroping report observability-packet --output json
entroping report api-inventory --output json
entroping report mutation-readiness --output json
entroping report evidence-index --output json
entroping report qa-brain-seed --output json
entroping report qa-brain-eval-plan --output json
entroping report qa-brain-retrieval-plan --output json
entroping report qa-brain-prompt-plan --output json
entroping report qa-brain-fine-tune-readiness --output json
entroping report qa-brain-model-packaging-plan --output json
entroping report qa-brain-routing-plan --output json
entroping report pilot-metrics
entroping report agent-bundle --scope tests/generated
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
