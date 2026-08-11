---
title: Entroping User Guide
description: "Learn the supported Entroping workflow from project setup through deterministic Hurl execution and reports."
type: guide
status: active
tags:
  - user-guide
  - onboarding
---

# Entroping User Guide

**Contract version:** 4.1
**Product maturity:** Alpha
**Audience:** Developers, QA engineers, SDETs, architects, and platform teams

## 1. What Entroping Does

Entroping helps you turn backend intent into enforced API quality. You define policy in `qanstitution.yaml`, the canonical QAnstitution file, keep tests as Hurl files, record real traffic when needed, and run deterministic checks locally or in CI.

The normal loop is:

```text
Define law -> Generate or record tests -> Run Hurl with gates -> Review evidence -> Commit reviewed tests and policy
```

## 2. Install

Entroping currently supports Python 3.12 or 3.13. Install
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) and
[Hurl 4.3.0 or newer](https://hurl.dev/docs/installation.html) using the
instructions for your operating system, then install Entroping below. The
reviewed CI examples pin Hurl 8.0.1 for repeatable setup evidence.

Linux and macOS run the deterministic Hurl-backed workflow. Windows is
currently a doctor-only alpha path; Hurl-backed `entroping run` on Windows is
not yet a public support claim.

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

- `hurl` 4.3.0 or newer.
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
For Hurl, it runs `hurl --version` locally and reports compatible, missing,
unsupported, or unparsable version states without making API requests.
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
The source-checkout onboarding flow remains: checkout, set up `uv` and Hurl,
and run `scripts/demo.sh`.

For a package-installed Aha proof, run `entroping demo --project <path>` with a
new or empty project directory. The command copies the reviewed checkout demo
fixture, starts the local fixture API, runs deterministic Entroping/Hurl proof,
and does not call model providers or external APIs.

## 3. New Project Quick Start

Initialize Entroping:

```bash
entroping init
```

For an onboarding-first proof from a package install, run:

```bash
entroping demo --project ./entroping-checkout-demo
```

For source-checkout release-smoke parity, run:

```bash
scripts/demo.sh
```

Both paths stay local-only and provider-free.

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

New QAnstitution files should use `version: "4.1"`. Existing unversioned policy
files remain valid when they match the current shape, but old or future version
markers fail validation instead of being migrated implicitly.

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
tests with `negative_category=invalid-auth`, severity, and safety metadata.
Unsupported schemes are printed as warnings instead of guessed.
When an operation has a JSON request body and an explicit `400` or `422`
validation response, `architect build --new` also writes bounded
negative-path Hurl under `tests/generated/negative/` for malformed JSON, schema
violations, boundary values, SQLi-like strings, and IDOR-style path variants.
These tests are ordinary committed Hurl files with category tags,
`negative_category`, `severity`, and safety metadata. Generated mutating
negative tests are marked `safety=destructive`, so protected runs block them
before Hurl execution until you review and intentionally change the test.

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

Preview the run plan before executing Hurl:

```bash
entroping run --dry-run --tag smoke --report json
```

Dry-run shows selected Hurl files, skipped counts, selectors, environment name,
requested report formats, effective and injected QAnstitution gate IDs,
worker/timeout/retry settings, and missing variable names. It does not invoke
Hurl, write `.entroping/latest-run.json`, write execution events, or produce
executed-result JSON/JUnit/HTML/drift reports. When `--report json` is present,
it writes the plan to `reports/run-plan.json` with schema
`entroping.run-plan.v1`; normal run report paths are listed only as
`would_write` evidence.

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
`--tag-expression`, `--suite`, `--changed-from`, or `--rerun-failures`.

After a failed local or CI run, rerun only failed files for fast feedback:

```bash
entroping run --rerun-failures --report json
```

This reads `reports/run-latest.json` first, then `.entroping/latest-run.json`,
selects failed source `.hurl` paths that still exist, and sends those files
through the normal deterministic run workflow. It reuses the report environment
unless `--env` is provided. Use it after making a fix; keep full-suite
`entroping run --ci` as release proof.

## 4. Existing Hurl Project

If you already have Hurl tests, Entroping should adopt them rather than replace them.

1. Add `qanstitution.yaml`.
2. Ensure tests live under `tests/`.
3. Add tags and story metadata where useful.
4. Run:

```bash
entroping run --env local --report html
```

If you want to confirm contract-only surfaces before runtime execution, you can
run the API inventory report in a fixture directory:

```bash
cd examples/webhook-api
uv run --project ../.. entroping report api-inventory --output md
```

This local inventory command surfaces webhook/event contract evidence even if no
fixture HTTP traffic has run yet.

To apply a safe bulk change:

```bash
entroping architect refactor \
  --target "tests/payments/*.hurl" \
  --prompt "Add the Authorization header using {{auth_token}} to every request."
```

To inspect the proposed edits first:

```bash
entroping architect refactor \
  --target "tests/payments/*.hurl" \
  --prompt "Add the Authorization header using {{auth_token}} to every request." \
  --preview
```

Current alpha support is intentionally narrow: refactor targets must either be
Architect-owned Hurl files marked with `# entroping: source=architect` or manual
Hurl files with explicit `# entroping: managed-begin <id>` and
`# entroping: managed-end <id>` blocks. For manual targets, Entroping replaces only
matching managed blocks and preserves surrounding content. Refactored Hurl is
validated before writing changes. Preview mode uses the same provider, parser,
merge, and validation path, then prints a unified diff without writing target
files. Treat preview output as review evidence, not execution proof; run the
affected Hurl tests or full suite before merging.

Self-healing maintenance is still human-reviewed. Use Architect proposals after
an explicit prompt, OpenAPI diff, failed deterministic run, or drift report, then
review the diff and the `.entroping/agent-runs/*.json` manifest before writing or
committing. Manifests record prompt and target evidence as hashes and paths, not
raw prompts, provider output, target Hurl contents, secrets, cookies, or tokens.

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
The `watch` startup output repeats this redaction-review reminder before capture
begins so the local storage boundary is visible in the terminal.
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

If any selected records have low redaction confidence, `run_freeze` and
`run_freeze_mock` block artifact writes, and `map --export png` blocks PNG
rendering. This keeps unknown or uncertain payload shapes from being promoted
to Hurl/WireMock/dependency map artifacts until you narrow filters or review
capture quality first.

Review what redaction categories fired before freezing or mapping:

```bash
entroping report redaction --output md
entroping report redaction --fail-on-unsafe
```

The redaction review writes `reports/redaction-review.md` by default and can
write `reports/redaction-review.html` with `--output html`. It contains counts
and categories only, not raw header, query, or body values.
Add `--fail-on-unsafe` in CI when redaction evidence must prove there are no
unredacted or low-confidence records; the report is still written before the
command exits nonzero.

Summarize what the Eye captured before choosing a freeze target:

```bash
entroping report capture-summary --output md
entroping report capture-summary --output json
entroping report capture-summary --output json --fail-on-unredacted
```

The capture summary reads existing redacted traffic state through a read-only
path and writes `reports/capture-summary.md` or `reports/capture-summary.json`.
It groups records into derived sessions and reports counts by method, host,
dependency target, status family, and redaction category without rendering raw
URLs, query values, headers, cookies, request bodies, response bodies, or
tokens.
Add `--fail-on-unredacted` in CI when captured-traffic evidence must prove every
stored record was redacted; the report is still written before the command
exits nonzero.

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

Compare effective QAnstitution evidence across branches or releases:

```bash
entroping report policy-diff \
  --base reports/base-effective-policy.json \
  --current reports/effective-policy.json \
  --output md
```

The policy diff command reads existing `report policy --output json` artifacts
only. It reports import and gate changes without loading policy files, running
Hurl, calling providers, or failing just because reviewed policy evidence
changed.

Map each effective gate to committed Hurl coverage:

```bash
entroping report gate-coverage --output md
entroping report gate-coverage --output json
entroping report gate-coverage --output json --fail-under 80
```

The gate coverage report writes `reports/gate-coverage.md` or
`reports/gate-coverage.json`. It shows which effective gates match committed
Hurl files, tags, operation IDs, request methods, and redacted request paths,
and it lists gates with no matching tests. It is not a run result: it does not
execute Hurl, inject assertions, evaluate pass/fail, call model providers, or
print full URLs, query strings, headers, bodies, variables, or traffic values.
Add `--fail-under <0-100>` in CI when a team has agreed on a minimum
matched-gate coverage floor; the report is still written before the command
exits nonzero.

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

Score generated Hurl tests before asking agents to repair them:

```bash
entroping report test-quality --output md
entroping report test-quality --output json
entroping report test-quality --output json --fail-under 80
```

The generated-test quality report writes `reports/test-quality.md` or
`reports/test-quality.json`. It statically reviews committed generated Hurl for
assertion strength, positional selectors, missing negative-path metadata,
missing auth/security metadata, shallow schema checks, overfitted examples, and
operation traceability gaps. It does not execute Hurl, inject QAnstitution
gates, call providers, upload artifacts, or print raw Hurl values. Use the
score to guide human or AI repair proposals; do not treat it as a replacement
for `entroping run` or QAnstitution enforcement. Add `--fail-under <0-100>` in
CI when a team has agreed on a minimum generated-test quality floor; the report
is still written before the command exits nonzero.

### Generated-test QA loop narrative

A local-first QA loop for AI-generated changes follows this evidence sequence:

1. `entroping report test-quality --output json` (generated-test quality)
2. `entroping report mutation-readiness --output json` (mutation/readiness)
3. `entroping report qa-brain-seed --output json` (seed contract)
4. `entroping report qa-brain-eval-plan --output json`
5. `entroping report qa-brain-retrieval-plan --output json`
6. `entroping report qa-brain-prompt-plan --output json`
7. `entroping report qa-brain-routing-plan --output json`
8. `entroping report qa-brain-repair-plan --output json`

Each packet is a read-only, deterministic evidence artifact. It does not auto-repair code or bypass Hurl enforcement. Human/Codex review is required before generated changes are accepted.

Summarize local test/evidence layers from existing reports:

```bash
entroping report test-pyramid --output md
entroping report test-pyramid --output json
```

The test-pyramid report writes `reports/test-pyramid.md` or
`reports/test-pyramid.json`. It classifies existing local artifacts into code
coverage, runtime API proof, policy governance, drift/contract,
static/security, and generated-test quality layers, then highlights missing
runtime-governance proof when run JSON, JUnit XML, or gate-coverage JSON is
missing, invalid, or unsafe. It does not run pytest or Hurl, parse source Hurl,
call providers, upload artifacts, or print raw report contents, raw traffic,
stdout/stderr, environment values, or source coverage file names.

Review API inventory evidence from local schema fixtures:

```bash
entroping report api-inventory --output md
entroping report api-inventory --output json
```

The API inventory report writes `reports/api-inventory.md` (default) or
`reports/api-inventory.json`. It scans local schema artifacts and annotated Hurl
metadata to produce a deterministic inventory before running checks. It does not run
`entroping run`, execute Hurl files, call providers, or mutate fixtures.
Use it to prove API surface evidence locally before execution workflows.
Tool-style HTTP APIs are governed as ordinary REST schema contracts here.

Write checksum evidence for the local report artifacts:

```bash
entroping report artifact-manifest
entroping report artifact-manifest --fail-on-incomplete
```

The artifact manifest writes `reports/artifact-manifest.json`. It lists
standard local report artifacts, schema versions when available, byte sizes,
and SHA-256 checksums; missing expected artifacts are recorded without failing
the command unless `--fail-on-incomplete` is set. Add
`--fail-on-incomplete` in CI when release evidence must prove all expected
artifacts are present and audit-chain verification is `verified`; the manifest
is still written before the command exits nonzero. Present artifacts are
rejected before full reads, checksums, or schema sniffing if they exceed the
local report-artifact size cap. It also records a value-free local audit event in
`.entroping/report-audit-chain.jsonl` and shows audit verification status in the
manifest so a later run can flag broken previous-hash linkage. Use it as CI
upload or release-review integrity evidence, not as a signature, notarization,
or attestation system.

Write a sanitized design-partner upload-readiness bundle:

```bash
entroping report evidence-bundle
entroping report evidence-bundle --output reports/evidence-bundle.md
```

The evidence bundle writes `reports/evidence-bundle.json` by default. When the
output path ends in `.md` or `.markdown`, it writes a reviewer-facing Markdown
summary from the same sanitized data model. The Markdown summary includes
status, required-artifact readiness, checksum and artifact-manifest audit
diagnostics, and next local commands for missing evidence; it does not embed
report contents, raw traffic, source Hurl contents, stdout/stderr, prompts,
provider outputs, credentials, environment values, or upload anything. If the
bundle status is `not_ready`, fix the missing, malformed, invalid, or
inconsistent local evidence before sharing it with a design partner or hosted
workflow.

## Design-Partner Pilot Kit

### Local evidence-loop demo

Use this local fixture when you want to exercise report packet generation end-to-end
before sharing anything externally:

```bash
./examples/evidence-loop/run-evidence-loop-demo.sh
```

The script prepares a temporary copy of `examples/checkout-api`, runs
`entroping doctor`, executes a local smoke run, and writes packet artifacts for:

- `runtime-card` (stabilized)
- `handoff` (stabilized)
- `design-partner-feedback` (design-partner packet)
- `evidence-links` (experimental)
- `notification-packet` (experimental)
- `evidence-portal` (experimental)

Artifacts are written under `$ENTROPING_DEMO_TMP_BASE` (default
`$HOME/.cache/entroping-demo`) and removed unless
`ENTROPING_DEMO_KEEP_ARTIFACTS=1`.

Use this pilot kit when a design partner wants to evaluate Entroping on
AI-generated backend/API changes. The pilot is a local-first evidence loop, not
a hosted product launch or a claim that demand has already been validated.

Target workflow:

1. Pick one service, one repo, and one recurring AI-assisted API change path.
2. Keep the team's existing CI, issue tracker, and review process in place.
3. Run Entroping locally or in CI after AI-generated code or Hurl changes land.
4. Attach only sanitized evidence to the review or pilot discussion:
   `reports/run-latest.json`, `reports/effective-policy.json`,
   `reports/artifact-manifest.json`, `reports/evidence-bundle.json`,
   `reports/design-partner-feedback.json`, and `reports/evidence-bundle.md`,
   `reports/runtime-card.md`, or `reports/pilot-metrics.md` when present.
5. Convert every product gap, confusing error, false positive, missing report,
   or adoption blocker into a narrow GitHub issue before expanding scope.

Setup steps:

```bash
entroping init
entroping doctor --ci
entroping run --ci --report json --report junit
entroping report policy --output json
entroping report artifact-manifest
entroping report evidence-bundle
entroping report evidence-bundle --output reports/evidence-bundle.md
entroping report runtime-card
entroping report pilot-metrics
entroping report design-partner-feedback
```

Design-partner evidence-bundle acceptance checks:

- `reports/evidence-bundle.json` uses schema
  `entroping.evidence-bundle.v1` and purpose
  `design-partner-upload-readiness`.
- Bundle status is `ready`, or every `not_ready` diagnostic has a local
  remediation hint that was followed or linked to a follow-up issue. Hints are
  local next-action commands only; Entroping does not execute them
  automatically or send evidence to hosted support.
- Required local evidence is present: latest run report, effective policy
  report, and artifact manifest.
- Required JSON artifacts pass their full v1 contracts; matching
  `schema_version` strings alone are not enough.
- Artifact paths are project-relative and checksums match the artifact
  manifest.
- Artifact-manifest audit status is reviewed before sharing.
- Shared evidence does not include raw traffic, source Hurl contents, prompts,
  provider outputs, credentials, environment values, stdout/stderr, cookies, or
  report artifact contents.

Pilot metrics:

- Run `entroping report pilot-metrics` for a local value-free summary before
  sharing pilot evidence. The report infers only what existing sanitized
  artifacts prove and marks the rest as `unknown` or
  `manual_input_required`.
- Locally inferred today: evidence-bundle `ready` rate from
  `reports/evidence-bundle.json` and manually waived gate count from
  run-report known-failure evidence.
- Manual input still required: setup time, useful failures, false positives,
  and human steering because those need design-partner or reviewer feedback.
- Track outside Entroping when needed: time from checkout to first
  `entroping run --ci` result, time from failed AI-generated change to a
  reviewer-understandable runtime card, escaped regressions, blocked
  regressions, commands retried, docs consulted, and maintainer help needed.
- Whether the engineering lead would pay for cross-repo evidence aggregation,
  premium policy packs, or managed policy workflows after seeing the local
  evidence loop.

Interview prompts:

- Which AI-generated API change did Entroping make safer to review?
- Which report or card changed a review, release, or rollback decision?
- Which QAnstitution rule felt like team policy instead of tool noise?
- What evidence was missing before a lead would trust hosted aggregation?
- Which `not_ready` diagnostic or setup step caused the most friction?
- What should stay local forever for security, privacy, or developer trust?

Feedback template:

```text
Pilot repo/service:
AI-assisted change type:
Entroping commands run:
Evidence bundle status:
Runtime card status:
Blocked regression or useful failure:
False positive or noisy gate:
Missing evidence:
Setup friction:
Security/privacy concern:
Follow-up GitHub issue:
Would pay for hosted aggregation? yes/no/unclear, with reason:
Would pay for premium policy packs? yes/no/unclear, with reason:
```

Design-partner feedback artifact:

Store sanitized pilot feedback, when collected, as
`reports/design-partner-feedback.json` with schema
`entroping.design-partner-feedback.v1`. This artifact is product-learning
evidence, not proof of validated demand. Start the local template with:

```bash
entroping report design-partner-feedback
```

The command writes a schema-valid sanitized template, derives value-free
evidence-bundle, runtime-card, and pilot-metrics statuses from existing local
report artifacts, and leaves command-history and manual feedback fields as
`null` or `manual input required`. Keep the shape close to the feedback
template: pilot repo/service, AI-assisted change type, Entroping commands run,
evidence-bundle status, runtime-card status, blocked regression or useful
failure, false positive or noisy gate, missing evidence, setup friction,
security/privacy concern, follow-up GitHub issue, and yes/no/unclear
pay-signal answers with short reasons.

Do not include customer secrets, raw traffic, credentials, environment values,
prompts, provider outputs, source Hurl contents, or private conversation dumps.
Free-text fields should be concise sanitized summaries, not copied chat, email,
support, or meeting transcripts. Use `null` for a required feedback category
when there is nothing to report.

No hosted aggregation, policy registry, premium model workflow, or enterprise
compliance claim is proven until repeated design-partner evidence shows the
local evidence loop is useful, safe to share, and worth coordinating across
repositories.

Write a concise PR/runtime evidence card:

```bash
entroping report runtime-card
entroping report runtime-card --output json
```

The runtime card writes `reports/runtime-card.md` or
`reports/runtime-card.json`. It requires `reports/run-latest.json` and
summarizes drift, redaction confidence from `reports/capture-summary.json`,
release evidence, design-partner pilot readiness from
`reports/evidence-bundle.json`, and agent provenance from existing sanitized
artifacts when they are present. A `pass` runtime card is intended for PR or
release review and therefore requires release anchors:
`reports/artifact-manifest.json` and `reports/evidence-bundle.json`. Missing
release anchors mark the card `attention` and make the CLI exit nonzero without
failing closed like missing run evidence. Pilot readiness shows only the
evidence-bundle status, missing-artifact count, invalid-artifact count,
checksum-mismatch count, diagnostic count, and artifact-manifest audit status.
Missing required run evidence writes a failed card, and missing redaction
evidence marks the card for reviewer attention. Malformed or unsafe
evidence-bundle artifacts are shown as `invalid` or `unsafe` pilot readiness
without rendering raw contents; other
malformed present artifacts fail before output is written. It does not execute
Hurl, call providers, upload artifacts, or render raw Hurl output, raw traffic,
prompts, provider responses, credentials, or environment values.

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
# entroping: auth_flow=login-capture
# entroping: auth_requires=user_email,user_password
# entroping: auth_produces=auth_token

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
- Declare auth flow metadata with variable names only when a test requires or
  produces tokens, cookies, or CSRF values.
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
settings. Suites can also set `protected: true` to force protected-run safety
checks and `safety: read-only|idempotent|teardown-backed|destructive` as a
reviewed default for selected tests. Test-level `# entroping: safety=...`
metadata wins over suite defaults. `--suite` cannot be combined with ad hoc
selectors such as `--env`, `--tag`, `--tag-expression`, `--report`,
`--parallel`, `--fail-fast`, `--drift-check`, `--changed-from`, or
`--rerun-failures`; use `--ci` only to choose strict exit behavior.

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
entroping report policy-diff --base reports/base-effective-policy.json --current reports/effective-policy.json --output json
entroping report gate-coverage --output json
entroping report gate-injection --target tests/health.hurl --output json
entroping report artifact-manifest
entroping report runtime-card --output json
entroping report pilot-metrics --output json
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
entroping report runtime-card
```

This writes `reports/review-summary.md` from the JSON run report, JUnit XML,
drift JSON, and optional local traceability metadata. Entroping does not call
GitHub, GitLab, Buildkite, Jira, Linear, or model providers to post it.
The runtime card writes `reports/runtime-card.md` from the same local evidence
family plus optional sanitized release and agent evidence so reviewers can see
the PR runtime proof at a glance.

After writing reports that you plan to upload, write a manifest for reviewers:

```bash
entroping report artifact-manifest
```

The manifest includes checksums and sizes for present report files, a
`missing_artifacts` list for expected files that were not produced in this run,
and an `audit` block with local chain status and diagnostics.

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

Use failure reruns after a fix when the latest run report already records the
failing files:

```bash
entroping run --rerun-failures --report json
```

This is also a feedback shortcut, not release proof.

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
- A read-only evidence viewer for report artifacts, with stable evidence IDs
  such as `run-json`, `capture-summary-json`, `test-quality-json`, and
  `runtime-card-json`.
- A read-only pilot readiness panel for `reports/evidence-bundle.json` that
  shows the schema, bundle status, required artifact counts,
  missing/invalid/unsafe diagnostic counts, checksum mismatch count, and
  artifact-manifest audit-chain status.
- A read-only traffic session browser over redacted SQLModel-backed state.
- Inferred target/dependency grouping, route counts, latency summaries, and safe redaction categories and counts.

Studio is intentionally read-only in the alpha. It does not update tests,
config, reports, or `.entroping` state. It also does not start `watch`, control
live capture, or render raw URLs with query values, headers, bodies, cookies,
tokens, or secrets.

The evidence viewer shows presence, invalid, and unsafe states for existing
sanitized local artifacts. Oversized, unreadable, malformed, or
schema-mismatched JSON artifacts are marked invalid without rendering contents.
It does not render raw report contents, does not upload artifacts, and does not
edit tests, QAnstitution, reports, traffic state, or runtime state. The stable
evidence IDs are intended to line up with CLI output, PR runtime cards, and
future editor or workbench surfaces without changing the locked CLI command
contract.

The pilot readiness panel is a value-free detail view over
`evidence-bundle-json`. It validates the bundle contract, summarizes ready,
not_ready, invalid, missing, and unsafe states, and displays only counts and
status labels. It does not open the artifact for raw inspection, does not render
referenced report contents, does not execute remediation hints, and does not
upload evidence.

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

Environment names `prod`, `production`, and `protected` are protected by
default through `settings.protected_environments`; teams can add names such as
`prod-smoke` there when needed. A suite manifest can also force the same
behavior:

```yaml
version: entroping.suite.v1
name: prod-smoke
env: prod-smoke
protected: true
tags:
  - smoke
reports:
  - junit
```

In protected runs, `GET`, `HEAD`, and `OPTIONS` are read-only. `POST`, `PUT`,
`PATCH`, and `DELETE` are blocked before Hurl execution unless the Hurl test or
suite declares reviewed safety metadata:

```hurl
# entroping: tags=smoke
# entroping: safety=idempotent

POST {{base_url}}/maintenance/reindex
HTTP 202
```

Use `read-only`, `idempotent`, or `teardown-backed` only after review. Mark
known unsafe tests as `destructive`; Entroping will block them in protected
environments even if the suite has a safer default.

Do not rely on a generated test to make unsafe production writes safe. Keep the
`smoke` tag reserved for read-only or explicitly idempotent tests, and use
QAnstitution gates for latency, status, and header expectations:

```yaml
gates:
  - id: "prod_smoke_latency"
    condition: "tags contains 'smoke'"
    gate: "duration < 500"
    enforcement: "block"
```

When Entroping blocks a protected run, requested JSON, JUnit, and HTML reports
show status `blocked`, the mutating method, and the value-free reason. Reports
do not include environment variable values, request bodies, headers, cookies,
or tokens.

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
- Keep API keys in environment variables, not plaintext config files. OS credential storage is future work.

The operational setup guide lives in `docs/user/AI_PROVIDER_SETUP.md`. It covers
LiteLLM installation, local Qwen through Ollama, local Qwen through oMLX
OpenAI-compatible endpoints, cloud model routing, and no-provider CI.

The Architect should generate only from configured sources: specs, stories, dependency specs, redacted traffic, or explicit prompt context. If you ask for exploratory negative tests, review them carefully and keep the resulting Hurl files in Git. `entroping run` never calls an LLM or performs hidden fuzzing.

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

Run `entroping doctor`. Install Hurl 4.3.0 or newer through your package
manager, then retry. On macOS, `brew install hurl` is the shortest path.
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

### Local-first traffic and evidence export FAQ

- **Where is data stored locally?**
  - Runtime state: `.entroping/state.db`
  - Reports and artifacts: `reports/`
  - Event log: `.entroping/latest-run-events.jsonl`
  - Latest run metadata: `.entroping/latest-run.json`

- **What is redacted before storage or report write?**
  Entroping redacts token-like values, URL userinfo/query fragments, request
  and response body fragments, headers, and cookies before persistence. Redacted
  summaries are kept for deterministic report generation.

- **What is never uploaded by default?**
  Raw traffic, secrets, source Hurl contents, env values, prompts, and provider
  responses are not uploaded by Entroping in the local examples or default
  commands.

- **Can a provider boundary receive runtime evidence?**
  `entroping run` is LLM-free by design. Provider calls occur only in Architect/
  Brain commands, and those commands only emit sanitized output and artifacts.

- **Can this be safely shared?**
  Share only curated artifacts (for example
  `reports/run-latest.json`, `reports/evidence-bundle.json`,
  `reports/pilot-metrics.json`, `reports/runtime-card.md`) and avoid sharing
  `.entroping/` directories.

- **Can I share evidence outside the repo?**
  Yes, after review. Use evidence artifacts that keep secrets out and keep
  sharing scope explicit, then document anything missing as `manual_input_required`
  in review packets instead of inventing raw fields.

### Evidence packet picker

Use this compact map before sharing or reviewing local packets:

| User question | Packet surface | Command | Output artifact | Required prior evidence |
| --- | --- | --- | --- | --- |
| Is the PR ready for merge review? | Launch-critical | `entroping report runtime-card --output json` | `reports/runtime-card.json` | `reports/run-latest.json`, `reports/effective-policy.json` |
| Is API quality evidence complete? | Launch-critical | `entroping report test-quality --output json` | `reports/test-quality.json` | `reports/run-latest.json` |
| Do we have safe upload-ready evidence? | Maintainer/Stable | `entroping report evidence-bundle --output json` | `reports/evidence-bundle.json` | `reports/run-latest.json`, `reports/effective-policy.json`, `reports/artifact-manifest.json` |
| Where are external-facing links and IDs? | Stable | `entroping report evidence-links --output md` | `reports/evidence-links.md` | `reports/evidence-index.json`, `reports/run-latest.json` |
| What did the AI evidence loop imply? | Experimental | `entroping report design-partner-feedback` | `reports/design-partner-feedback.json` | `reports/evidence-bundle.json`, `reports/runtime-card.json` |
| Which experiment or QA packet is next? | Experimental | `entroping report qa-brain-repair-plan` | `reports/qa-brain-repair-plan.json` | `reports/test-quality.json`, `reports/mutation-readiness.json`, `reports/devex-readiness.json`, `reports/action-plan.json` |

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
