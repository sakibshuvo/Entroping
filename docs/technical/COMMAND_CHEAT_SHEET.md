# Entroping Command Cheat Sheet

**Version:** 4.1 Stable  
**Rule:** Use this command surface as the implementation and user-facing source of truth.

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
OpenAPI file configured at `sources.spec` in `qanstitution.yaml`. Prompt generation,
remote specs, and `--strategy merge` remain planned.

| Command | Purpose |
| --- | --- |
| `entroping architect build --new` | Generate new Hurl tests from configured sources |
| `entroping architect build --prompt "<text>"` | Generate scoped tests from natural language |
| `entroping architect build --strategy merge` | Merge generated changes into existing tests |
| `entroping architect build --tag <tag>` | Add a tag to generated tests |
| `entroping architect refactor --target <glob> --prompt "<text>"` | Safely update existing Hurl tests |
| `entroping architect audit --focus logic` | Audit OpenAPI coverage gaps |
| `entroping architect audit --output <json|md>` | Select audit output format |

Examples:

```bash
entroping architect build --new --tag smoke
entroping architect build --prompt "Add negative tests for expired JWTs" --tag security
entroping architect build --strategy merge --prompt "Cover the new refund endpoint"
entroping architect refactor --target "tests/payments/*.hurl" --prompt "Add X-Tenant-Id header"
entroping architect audit --focus logic --output md
```

## Observation

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
`--report html`, `--report json`, and `--report junit`. `--parallel` and drift reports
remain part of the v4.1 contract but are not implemented yet.

| Command | Purpose |
| --- | --- |
| `entroping studio --env <name>` | Open local TUI |
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

## Reporting

| Command | Purpose |
| --- | --- |
| `entroping report bug` | Generate a Markdown bug report from the latest failure |

Example:

```bash
entroping report bug
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
entroping architect build --prompt "Generate hostile tests for auth bypass and IDOR" --tag security
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
| `chaos` | `architect build --prompt "<breaker intent>"` |
| `verify` | `run` |
| `explain` | Reports and audit output |
| top-level `build` | `architect build` |
| `report --type` | `run --report` or `report bug` |
| `auth` | Future credential UX; MVP uses env vars or OS credential storage |
| `--verbose` / `--dry-run` | Future global flags only after spec update |
