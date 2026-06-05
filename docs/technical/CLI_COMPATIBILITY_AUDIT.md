---
title: CLI Compatibility Audit
type: technical
status: active
tags:
  - cli
  - compatibility
  - stable-core
  - governance
---

# CLI Compatibility Audit

This audit is the compatibility decision for the Entroping v4.1 alpha command
surface before stable-core claims. It compares the Typer app, README, technical
design, command cheat sheet, and tests.

Status: **Locked alpha**. These commands are not a v1 stability promise yet, but
they are the reviewed alpha contract. Do not rename commands, add aliases, remove
flags, or change report artifact paths without a GitHub issue, tests, docs
updates, and an explicit compatibility decision.

## Locked Command Surface

```text
entroping init [--minimal]
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
entroping report traceability [--output <md|json>]
entroping report github-annotations [--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]
entroping report sarif [--output <path>] [--junit <path>] [--drift <path>] [--traceability]
entroping report promote-drift-baseline [--candidate <path>] [--output <path>]
entroping report review-summary [--output md] [--junit <path>] [--run-json <path>] [--drift <path>] [--traceability]
```

## Compatibility Decisions

| Area | Decision |
| --- | --- |
| Command naming | Keep the nested noun/verb shape: `config vendor-policy-pack`, `config test-policy-pack`, `architect build`, `architect refactor`, `report bug`, `report failure-bundle`, `report delta`, `report badges`, `report redaction`, `report traceability`, `report github-annotations`, `report sarif`, `report promote-drift-baseline`, `report review-summary`. |
| Aliases | No alias is compatibility-supported. Deprecated brainstorm names such as `gen`, `fix`, `scan`, `chaos`, `verify`, top-level `build`, `auth`, and `report --type` remain unavailable. |
| Global flags | Only Typer completion helpers and `--version` are current global flags. `--verbose` is not a product flag. `freeze --dry-run` is command-scoped and does not create a global dry-run mode. |
| Determinism | `entroping run` remains deterministic, Hurl-backed, and LLM-free. |
| Doctor CI readiness | `doctor --ci` is a strict local preflight for PR gates. It validates Hurl availability, safe report paths, suite manifests, required Hurl variables, and provider-free `run --ci` expectations without calling CI provider APIs or mutating workflows. |
| Named suites | `run --suite <name>` loads committed `suites/<name>.yaml` manifests with schema `entroping.suite.v1`, root-bounded local path globs, tags, env, reports, parallel, fail-fast, and drift settings. It cannot be combined with ad hoc selectors; `--ci` remains allowed for exit behavior. |
| Fail-fast runs | `run --fail-fast` stops scheduling new tests after the first failing Hurl result while preserving deterministic source immutability, latest-run state, reports for executed tests, and selected/executed/not-scheduled summary evidence. Parallel fail-fast is bounded: already scheduled workers may complete, but no new work is scheduled after the first failure is observed. |
| Operation selection | `run --operation-id <id>` is a repeatable deterministic selector over committed Hurl `operation_id` metadata. It cannot be combined with `--suite`, `--changed-from`, `--tag`, or `--tag-expression`; run reports may include optional per-test `operation_id` evidence. |
| Architect generation | Deterministic `architect build --new` reads the configured local OpenAPI spec and validates generated Hurl before write. `--changed-from <ref>` limits that deterministic path to current added, modified, or renamed operations relative to the same spec at a Git base ref and reports removed operations for manual review. Prompt-backed `architect build` and `architect refactor` may call LiteLLM, but generated files must pass validation before write. `architect build` defaults to Builder and accepts `--agent breaker` for hostile/security generation; deterministic `architect audit --focus logic --output json` emits `entroping.openapi-audit.v1`, and `--changed-from <ref>` attaches an `entroping.openapi-breaking-diff.v1` nested report without writing tests; `architect audit --focus auditor` is the explicit Auditor review path. |
| Policy-pack vendoring | `config vendor-policy-pack` accepts reviewed local pack directories only. It copies the pack under `policy-packs/`, validates the manifest and QAnstitution entrypoint, appends a local import, and does not fetch from registries or remote URLs. |
| Policy-pack self-test | `config test-policy-pack` accepts reviewed local pack directories only. It validates safe local boundaries, manifest/entrypoint/gate/final-gate consistency, and consumer examples without copying files, editing `qanstitution.yaml`, fetching registries, or requiring provider keys. |
| Capture filters | `freeze`, `freeze --mock`, and `map` accept repeatable `--include-host`, `--exclude-host`, `--include-method`, `--exclude-method`, `--include-path`, and `--exclude-path` options. Filters apply only to already-redacted captured traffic; exclude rules win; path filters match request paths, not query strings. |
| Freeze preview | `freeze --dry-run` previews selected redacted records, proposed output paths, golden status, and redaction categories. It writes no generated tests, mocks, approval manifests, or source artifacts and must not render raw traffic values. |
| Studio | `studio` is read-only until mutation workflows are designed and accepted separately. |
| Report formats | `run --report` is repeatable and owns run artifact creation. `report bug`, `report failure-bundle`, `report delta`, `report badges`, `report redaction`, `report policy`, `report traceability`, `report github-annotations`, `report sarif`, `report promote-drift-baseline`, and `report review-summary` are handoff/reporting commands, not test execution commands. |

## Post-Alpha UX Decision Queue

These decisions close the current post-alpha UX questions without changing the
locked alpha command surface.

| Question | Decision | Rationale | Future change gate |
| --- | --- | --- | --- |
| Environment input | Named environments remain the supported runtime contract. `--env <name>` resolves reviewed `envs/<name>.env` presets; arbitrary env-file paths remain deferred. | Named presets keep CI reproducible, avoid accidental local secret paths in copied commands, and match current tests/docs. | A future `--env-file` or equivalent needs a compatibility issue, path-safety tests, secret-handling docs, and explicit precedence rules. |
| Generated Hurl output | `tests/generated/` remains the only generated Hurl output root for Architect and freeze output. | A single reviewed root makes path validation, symlink defense, human review, and cleanup predictable. | A configurable output root needs a QAnstitution setting or reviewed config field, migration notes, and tests proving generated files cannot escape the project. |
| Historical brainstorm commands | Historical brainstorm commands remain unavailable. Deprecated names such as `gen`, `fix`, `scan`, `chaos`, and `report --type` are documented for translation only. | The nested v4.1 shape is deliberate; aliases increase support surface and weaken compatibility evidence. | Friendly guidance may be added without adding aliases if it preserves exit code `2`, does not execute hidden behavior, and has regression tests for each rejected invocation. |
| QAnstitution schema migration | QAnstitution schema compatibility is not package versioning. Policy-file migration rules live in [QANSTITUTION_REFERENCE.md](QANSTITUTION_REFERENCE.md), while Python/package releases follow `pyproject.toml` and PEP 440. | Policy authors need clear validation and migration behavior independent of install-channel versions. | Any breaking policy shape change needs a migration issue, regenerated schema, examples, tests, and release notes. |

## Exit Code Contract

| Exit code | Meaning | Examples |
| --- | --- | --- |
| `0` | Successful command, successful run, or non-CI no-match run that is informational. | `--help`, `--version`, passing `run`, passing `report delta` with no added/changed failures, passing `report badges`, passing `report failure-bundle`, passing `report redaction`, passing `report traceability`, passing `report github-annotations`, passing `report sarif`, passing `report promote-drift-baseline`, passing `report review-summary`. |
| `1` | Runtime, configuration, report, Hurl, drift, or quality failure. | Invalid QAnstitution, missing Hurl, failing Hurl suite, drift finding with `--drift-check`, `report delta` with added or changed failures, missing source report for `report badges`, no failure available for `report bug` or `report failure-bundle`, missing traffic state for `report redaction`. |
| `2` | CLI usage or unsupported-mode error. | Unknown commands, unsupported `architect build --strategy`, unsupported `report delta --output`, unsupported `report redaction --output`, unsupported `report traceability --output`, unsupported `report review-summary --output`, unsupported `run --report`. |

This contract is intentionally small. More granular exit codes can be introduced
only through a compatibility issue and migration note.

## Report Artifacts

| Command | Artifact |
| --- | --- |
| `entroping run` | `.entroping/latest-run.json` |
| Prompt-backed `entroping architect ...` | `.entroping/agent-runs/*.json` |
| `entroping freeze` / `freeze --mock` / `map --export png` | `reports/approvals/*.json` |
| `entroping run --report json` | `reports/run-latest.json` |
| `entroping run --report junit` | `reports/junit.xml` |
| `entroping run --report html` | `reports/run-latest.html` |
| `entroping run --report drift` | `reports/drift.json` |
| `entroping run --report drift` | `reports/drift-baseline.candidate.json` |
| `entroping report promote-drift-baseline` | `.entroping/drift-baseline.json` |
| `entroping report bug` | `reports/bug.md` |
| `entroping report failure-bundle` | `reports/failure-bundle/manifest.json` |
| `entroping report delta --output md|json` | `stdout Run Delta Markdown/JSON` |
| `entroping report badges` | `reports/badges/*.json` |
| `entroping report redaction --output md` | `reports/redaction-review.md` |
| `entroping report redaction --output html` | `reports/redaction-review.html` |
| `entroping report policy --output md` | `reports/effective-policy.md` |
| `entroping report policy --output json` | `reports/effective-policy.json` |
| `entroping architect audit --output json` | `stdout Architect OpenAPI audit JSON` |
| `entroping report traceability --output md|json` | `stdout Markdown/JSON` |
| `entroping report github-annotations` | `stdout GitHub Actions annotations` |
| `entroping report sarif` | `reports/entroping.sarif` |
| `entroping report review-summary` | `reports/review-summary.md` |

Report paths are compatibility-relevant because downstream CI, examples, docs,
and automation scripts can depend on them.

Machine-readable JSON report payloads must also carry the versioned schemas in
`docs/technical/REPORT_SCHEMAS.md`. Additive optional fields can stay within the
current schema version; required-field, rename, removal, or type changes need a
new schema version and migration note.

## Audit Evidence

| Surface | Evidence |
| --- | --- |
| Typer app | `src/entroping/cli/main.py` defines all locked commands and flags. |
| README | `README.md` exposes the same compact command surface for public onboarding. |
| TDS | `docs/technical/TDS.md` lists CLI contracts, report artifacts, and execution boundaries. |
| Cheat sheet | `docs/technical/COMMAND_CHEAT_SHEET.md` is the practical command reference. |
| Tests | `tests/test_cli_compatibility_audit.py` checks docs, Typer help, deprecated aliases, exit-code policy, and report artifact documentation. |

## Stable-Core Rule

No command reaches stable status without:

1. Exact signature in README, TDS, command cheat sheet, and this audit.
2. Typer help coverage proving documented flags exist.
3. Deprecated-alias regression coverage when a brainstorm name could return.
4. Exit-code behavior documented or explicitly deferred.
5. Report artifacts documented when the command writes or emits machine-readable output.
6. `scripts/regression.sh --security` and CI passing.
