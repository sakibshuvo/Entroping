# Entroping Command Cheat Sheet

**Version:** 4.1 Stable  
**Rule:** Use this command surface as the implementation and user-facing source of truth.

Compatibility audit: [CLI_COMPATIBILITY_AUDIT.md](CLI_COMPATIBILITY_AUDIT.md).

## Locked Alpha Surface

```text
entroping init [--minimal]
entroping doctor
entroping config list
entroping config set --agent <builder|auditor|breaker> --model <model-id>

entroping architect build [--new] [--prompt <text>] [--strategy merge] [--tag <tag>] [--agent <builder|breaker>]
entroping architect refactor --target <glob> --prompt <text>
entroping architect audit [--focus <logic|auditor>] [--output <json|md>]

entroping watch [--port <port>] [--target <url>]
entroping freeze --name <flow> [--golden] [--mock <service>]
entroping map [--export <mermaid|dot|md|png>]

entroping studio [--env <name>]
entroping run [--env <name>] [--tag <tag>] [--ci] [--parallel] [--report <html|junit|json|drift> ...] [--drift-check]
entroping report bug
entroping report redaction [--output <md|html>]
entroping report policy [--output <md|json>]
entroping report traceability [--output md]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
entroping report review-summary [--output md] [--junit <path>] [--run-json <path>] [--drift <path>] [--traceability]
```

## Setup

Current alpha implementation supports `init`, `doctor`, `config list`, and
`config set` for non-secret Builder/Auditor/Breaker model routing. `config set`
updates `qanstitution.yaml`, creates a missing local persona Markdown template,
and does not store credentials or call model providers.

| Command | Purpose |
| --- | --- |
| `entroping init` | Create a standard Entroping project layout |
| `entroping init --minimal` | Create only the minimum required files |
| `entroping doctor` | Validate local setup, tools, config, and policies |
| `entroping config list` | Show effective non-secret configuration |
| `entroping config set --agent <name> --model <id>` | Configure model routing for an agent role |

Examples:

```bash
entroping init
entroping doctor
entroping config list
entroping config set --agent auditor --model openai/auditor-model
```

## Architect

Current alpha implementation supports deterministic `architect build --new` from a local
OpenAPI file configured at `sources.spec` in `qanstitution.yaml`, prompt-backed
`architect build --prompt`, Breaker-backed hostile prompt generation through
`architect build --agent breaker --prompt`, deterministic `architect audit --focus
logic`, Auditor-backed `architect audit --focus auditor`, and prompt-backed
`architect refactor` for Architect-owned Hurl files and manual files with explicit
managed blocks. Prompt-backed `architect build --strategy merge` is available for
existing Hurl targets. Remote specs remain planned.

| Command | Purpose |
| --- | --- |
| `entroping architect build --new` | Generate new Hurl tests from configured sources |
| `entroping architect build --prompt "<text>"` | Generate scoped tests from natural language |
| `entroping architect build --agent breaker --prompt "<text>"` | Generate hostile negative/security tests with the Breaker persona |
| `entroping architect build --strategy merge` | Merge generated changes into existing tests |
| `entroping architect build --tag <tag>` | Add a tag to generated tests |
| `entroping architect refactor --target <glob> --prompt "<text>"` | Safely update existing Hurl tests |
| `entroping architect audit --focus logic` | Audit OpenAPI coverage gaps |
| `entroping architect audit --focus auditor` | Run an explicit Auditor model review of coverage and policy risk |
| `entroping architect audit --output <json|md>` | Select audit output format |

Examples:

```bash
entroping architect build --new --tag smoke
entroping architect build --prompt "Add checkout smoke coverage" --tag ai
entroping architect build --agent breaker --prompt "Generate hostile auth bypass tests" --tag security
entroping architect build --strategy merge --prompt "Cover the new refund endpoint"
entroping architect refactor --target "tests/payments/*.hurl" --prompt "Add X-Tenant-Id header"
entroping architect audit --focus logic --output md
entroping architect audit --focus auditor --output json
```

## Observation

Current alpha implementation supports capture-only `watch`, basic Hurl
generation through `freeze --name <flow> [--golden]`, and dependency map export
through `map --export mermaid|dot|md|png`. `freeze --mock <service>` writes
WireMock-compatible mappings from redacted dependency traffic. PNG map rendering
uses local Graphviz `dot` when it is available.

| Command | Purpose |
| --- | --- |
| `entroping watch --port <port>` | Start local mitmproxy recorder |
| `entroping watch --target <url>` | Define upstream target for observation |
| `entroping freeze --name <flow>` | Convert captured session into Hurl tests |
| `entroping freeze --golden` | Add golden master assertions |
| `entroping freeze --mock <service>` | Generate WireMock mappings for a dependency |
| `entroping map --export <fmt>` | Export dependency map |

Examples:

```bash
entroping watch --port 8080 --target http://localhost:3000
entroping freeze --name checkout_flow --golden
entroping freeze --name refund_flow --mock payments
entroping map --export mermaid
```

## Execution

Current alpha implementation supports deterministic `run`, `--env`, `--tag`, `--ci`,
bounded `--parallel`, `--drift-check`, `--report html`, `--report json`,
`--report junit`, and `--report drift`. Before invoking Hurl, `run` checks
selected execution copies for unresolved `{{variable}}` references and reports
missing variable names without printing values.

| Command | Purpose |
| --- | --- |
| `entroping studio --env <name>` | Open read-only local Studio TUI |
| `entroping run --env <name>` | Run tests with environment variables |
| `entroping run --tag <tag>` | Run tests matching a tag |
| `entroping run --ci` | Strict CI mode |
| `entroping run --parallel` | Bounded parallel execution |
| `entroping run --report <html|junit|json|drift>` | Write report artifact; repeat for multiple formats |
| `entroping run --drift-check` | Compare runtime behavior against baseline |

Examples:

```bash
entroping studio --env local
entroping run --env local --tag smoke --report html --report json --report junit
entroping run --env ci --ci --parallel --report junit
entroping run --env staging --drift-check --report drift
```

`--report drift` writes both `reports/drift.json` and, when the Hurl suite
passes, `reports/drift-baseline.candidate.json`. Review the candidate before
copying it to `.entroping/drift-baseline.json`.

Variables can come from `envs/<name>.env`, explicit shell
`HURL_VARIABLE_<name>` entries, Hurl `[Options] variable` entries, or captures.

## Reporting

| Command | Purpose |
| --- | --- |
| `entroping report bug` | Generate a Markdown bug report from the latest failure |
| `entroping report redaction --output md` | Write a counts-only captured-traffic redaction review to `reports/redaction-review.md` |
| `entroping report redaction --output html` | Write a browser-readable redaction review to `reports/redaction-review.html` |
| `entroping report policy --output md` | Write effective QAnstitution gate provenance to `reports/effective-policy.md` |
| `entroping report policy --output json` | Write machine-readable effective policy evidence to `reports/effective-policy.json` |
| `entroping report traceability --output md` | Generate a local Markdown story/test traceability report |
| `entroping report github-annotations` | Emit GitHub Actions workflow-command annotations from local reports |
| `entroping report review-summary --output md` | Write a provider-neutral Markdown review summary to `reports/review-summary.md` |

Example:

```bash
entroping report bug
entroping report redaction --output md
entroping report policy --output md
entroping report traceability --output md
entroping report github-annotations --traceability
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
| `--verbose` / `--dry-run` | Future global flags only after spec update |
