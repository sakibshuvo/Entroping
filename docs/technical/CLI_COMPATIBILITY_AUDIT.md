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
entroping report pilot-outcome [--output <md|json>]
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

## Compatibility Decisions

| Area | Decision |
| --- | --- |
| Command naming | Keep the nested noun/verb shape: `config vendor-policy-pack`, `config test-policy-pack`, `architect build`, `architect refactor`, `report bug`, `report failure-bundle`, `report delta`, `report badges`, `report redaction`, `report capture-summary`, `report policy`, `report policy-diff`, `report gate-coverage`, `report gate-injection`, `report test-quality`, `report test-pyramid`, `report external-test-evidence`, `report artifact-manifest`, `report evidence-bundle`, `report design-partner-feedback`, `report runtime-card`, `report handoff`, `report notification-packet`, `report team-evidence-readiness`, `report team-access-control-plan`, `report integration-readiness`, `report devex-readiness`, `report evidence-cloud-readiness`, `report evidence-cloud-export`, `report evidence-cloud-workspace`, `report evidence-cloud-dashboard`, `report evidence-links`, `report evidence-portal`, `report pr-evidence-card`, `report evidence-action-plan`, `report work-item-draft`, `report work-item-import-bundle`, `report pilot-outcome`, `report connector-intent`, `report observability-packet`, `report api-inventory`, `report mutation-readiness`, `report evidence-index`, `report qa-brain-seed`, `report qa-brain-eval-plan`, `report qa-brain-retrieval-plan`, `report qa-brain-prompt-plan`, `report qa-brain-fine-tune-readiness`, `report qa-brain-model-packaging-plan`, `report qa-brain-routing-plan`, `report pilot-metrics`, `report agent-bundle`, `report traceability`, `report github-annotations`, `report sarif`, `report promote-drift-baseline`, `report review-summary`. |
| Aliases | No alias is compatibility-supported. Deprecated brainstorm names such as `gen`, `fix`, `scan`, `chaos`, `verify`, top-level `build`, `auth`, and `report --type` remain unavailable. |
| Global flags | Only Typer completion helpers and `--version` are current global flags. `--verbose` is not a product flag. `freeze --dry-run` and `run --dry-run` are command-scoped and do not create a global dry-run mode. |
| Init CI starter | `init --github-actions` is an explicit opt-in setup helper that writes the reviewed starter to `.github/workflows/entroping.yml`, refuses to overwrite an existing workflow, and does not add secrets, provider credentials, hosted-service coupling, or package-index readiness claims. |
| Determinism | `entroping run` remains deterministic, Hurl-backed, and LLM-free. |
| Doctor CI readiness | `doctor --ci` is a strict local preflight for PR gates. It validates Hurl availability, safe report paths, suite manifests, required Hurl variables, and provider-free `run --ci` expectations without calling CI provider APIs or mutating workflows. |
| Named suites | `run --suite <name>` loads committed `suites/<name>.yaml` manifests with schema `entroping.suite.v1`, root-bounded local path globs, tags, env, reports, parallel, fail-fast, and drift settings. It cannot be combined with ad hoc selectors; `--ci` remains allowed for exit behavior. |
| Fail-fast runs | `run --fail-fast` stops scheduling new tests after the first failing Hurl result while preserving deterministic source immutability, latest-run state, reports for executed tests, and selected/executed/not-scheduled summary evidence. Parallel fail-fast is bounded: already scheduled workers may complete, but no new work is scheduled after the first failure is observed. |
| Operation selection | `run --operation-id <id>` is a repeatable deterministic selector over committed Hurl `operation_id` metadata. It cannot be combined with `--suite`, `--changed-from`, `--rerun-failures`, `--tag`, or `--tag-expression`; run reports may include optional per-test `operation_id` evidence. |
| Failure reruns | `run --rerun-failures` selects failed source `.hurl` paths from `reports/run-latest.json` or `.entroping/latest-run.json`, reuses the report environment unless `--env` overrides it, and cannot be combined with `--suite`, `--changed-from`, `--tag`, `--tag-expression`, or `--operation-id`. It is fast feedback, not release proof. |
| Run dry-run preview | `run --dry-run` resolves the selected Hurl tests, effective and injected gates, environment name, variable preflight gaps, worker settings, and requested report paths without invoking Hurl, writing latest-run state, writing execution events, writing executed-result reports, or mutating source `.hurl`. When `--report json` is requested, it writes only `reports/run-plan.json` with schema `entroping.run-plan.v1`. |
| Effective policy diff | `report policy-diff --base <path> --current <path> --output md|json` compares two existing `entroping.effective-policy-report.v1` artifacts without loading policy files, fetching registries, calling providers, executing Hurl, or failing valid changed diffs by default. `--fail-on-change` is the explicit CI mode that exits `1` when the diff status is changed. |
| Architect generation | Deterministic `architect build --new` reads the configured local OpenAPI spec and validates generated Hurl before write. `--changed-from <ref>` limits that deterministic path to current added, modified, or renamed operations relative to the same spec at a Git base ref and reports removed operations for manual review. Prompt-backed `architect build` and `architect refactor` may call LiteLLM, but generated files must pass validation before write. `architect refactor --preview` renders a unified diff and writes only the value-free agent manifest, not target Hurl files; it is review evidence, not execution proof. `architect build` defaults to Builder and accepts `--agent breaker` for hostile/security generation; deterministic `architect audit --focus logic --output json` emits `entroping.openapi-audit.v1`, and `--changed-from <ref>` attaches an `entroping.openapi-breaking-diff.v1` nested report without writing tests; `architect audit --focus auditor` is the explicit Auditor review path. |
| Policy-pack vendoring | `config vendor-policy-pack` accepts reviewed local pack directories only. It copies the pack under `policy-packs/`, validates the manifest and QAnstitution entrypoint, appends a local import, and does not fetch from registries or remote URLs. |
| Policy-pack self-test | `config test-policy-pack` accepts reviewed local pack directories only. It validates safe local boundaries, manifest/entrypoint/gate/final-gate consistency, and consumer examples without copying files, editing `qanstitution.yaml`, fetching registries, or requiring provider keys. |
| Capture filters | `freeze`, `freeze --mock`, and `map` accept repeatable `--include-host`, `--exclude-host`, `--include-method`, `--exclude-method`, `--include-path`, and `--exclude-path` options. Filters apply only to already-redacted captured traffic; exclude rules win; path filters match request paths, not query strings. |
| Freeze preview | `freeze --dry-run` previews selected redacted records, proposed output paths, golden status, and redaction categories. It writes no generated tests, mocks, approval manifests, or source artifacts and must not render raw traffic values. |
| Studio | `studio` is read-only until mutation workflows are designed and accepted separately. |
| Redaction review | `report redaction --output md|html [--fail-on-unsafe]` reads existing redacted traffic state through the read-only store path and writes counts-only redaction evidence without rendering raw traffic values. `--fail-on-unsafe` exits `1` after writing the report when unredacted or low-confidence records exist. |
| Capture summary | `report capture-summary --output md|json [--fail-on-unredacted]` reads existing redacted traffic state through the read-only store path and writes counts by derived session, method, host, dependency target, status family, and redaction category without rendering raw traffic values. `--fail-on-unredacted` exits `1` after writing the report when unredacted records exist. |
| Test pyramid | `report test-pyramid [--output <md|json>]` reads existing local report artifacts, classifies test/evidence layers, optionally folds in sanitized `reports/external-test-evidence.json` counts-only evidence with schema `entroping.external-test-evidence.v1` when present, and highlights missing runtime-governance proof without running tests or Hurl, calling providers, uploading artifacts, or embedding raw artifact contents. |
| External test evidence | `report external-test-evidence [--output <md|json>]` reads fixed local JUnit, coverage XML, LCOV, and SARIF artifacts under `reports/external-tests/`, emits counts-only unit/integration/component/contract/e2e evidence, and does not run tests, execute Hurl, call providers, upload artifacts, parse raw traffic state, mutate external systems, change `entroping run`, or render raw test names, paths, URLs, headers, bodies, cookies, stack traces, source snippets, coverage file names, SARIF messages or locations, stdout/stderr, prompts, provider outputs, credentials, environment values, webhook URLs, full artifact contents, or raw traffic. |
| Artifact manifest | `report artifact-manifest [--output <path>] [--fail-on-incomplete]` writes checksum and audit-chain evidence for local report artifacts without embedding artifact contents. `--fail-on-incomplete` exits `1` after writing when expected artifacts are missing or audit verification is not `verified`. |
| Handoff packet | `report handoff [--output <md|json>] [--fail-on-insufficient]` writes a value-free local handoff packet without embedding report contents. `--fail-on-insufficient` exits `1` after writing when no source evidence artifacts are present. |
| Notification packet | `report notification-packet [--output <md|json>]` writes value-free local messages for work-management, chat, automation, and agent surfaces without calling vendor APIs or mutating tickets/chat. |
| Team evidence readiness | `report team-evidence-readiness [--output <md|json>]` writes a value-free local readiness packet for future team evidence cloud promotion from existing sanitized report artifacts without uploading, calling providers, changing access control, or embedding raw contents. |
| Team access-control plan | `report team-access-control-plan [--output <md|json>]` writes a value-free local role/action/boundary/audit plan for future team evidence surfaces without implementing hosted access control, uploading artifacts, calling providers, mutating external systems, or embedding raw contents. |
| Integration readiness | `report integration-readiness [--output <md|json>]` writes a value-free local readiness packet for issue tracker, chat, enterprise automation, cross-surface continuity, observability, and API governance surfaces without calling vendor APIs, uploading artifacts, mutating tickets/chat, reading provider keys, syncing repos/vaults, or embedding raw contents. |
| Developer experience readiness | `report devex-readiness [--output <md|json>]` writes a value-free local readiness packet for CLI, VS Code/editor, local workbench, PR runtime card, desktop, cloud, and mobile surfaces without implementing apps/extensions, calling external APIs, running tests, executing Hurl, syncing repos/vaults/worktrees, or embedding raw contents. |
| Evidence Cloud readiness | `report evidence-cloud-readiness [--output <md|json>]` writes a value-free local readiness packet for future Evidence Cloud upload/export promotion from fixed optional sanitized report artifacts without calling Evidence Cloud hosted APIs, uploading artifacts, syncing remote state, creating accounts, configuring SSO/RBAC, calling vendor APIs, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| Evidence Cloud export | `report evidence-cloud-export [--output <md|json>]` writes a value-free local export manifest for future explicit Evidence Cloud upload review from fixed optional sanitized report artifacts without calling hosted APIs, uploading artifacts, syncing remote state, creating accounts, configuring SSO/RBAC, mutating tickets/chat, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| Evidence Cloud workspace | `report evidence-cloud-workspace --manifest <path> [--output <md|json>]` writes a value-free local workspace dashboard packet from explicit Evidence Cloud export manifests without calling hosted APIs, uploading artifacts, syncing remote state, creating accounts, configuring SSO/RBAC, mutating tickets/chat, inspecting raw report artifacts beyond the explicit manifests, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| Evidence Cloud dashboard | `entroping report evidence-cloud-dashboard --manifest <path> [--output <html|json>]` writes a static value-free local workspace dashboard from explicit Evidence Cloud export manifests without hosted APIs, uploads, remote sync, external assets/scripts, Hurl/test execution, model calls, traffic parsing, `entroping run` changes, or raw artifact rendering. |
| Evidence links | `report evidence-links [--output <md|json>]` writes value-free cross-surface link targets for CLI, PR, desktop, cloud, mobile, and agent surfaces from fixed optional sanitized local evidence artifacts without registering protocol handlers, hosting pages, building UI surfaces, calling external APIs, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| Evidence portal | `report evidence-portal [--output <html|json>]` writes a static local value-free evidence dashboard from fixed optional sanitized report artifacts without hosting pages, external assets or scripts, registering protocol handlers, uploading artifacts, calling external APIs, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| PR evidence card | `report pr-evidence-card [--output <md|json>]` writes a local value-free PR review card from fixed optional sanitized report artifacts without creating or updating pull requests, calling GitHub APIs, hosting pages, uploading artifacts, calling external APIs, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| Evidence action plan | `report evidence-action-plan [--output <md|json>]` writes a local value-free prioritized action plan from fixed optional sanitized evidence-loop artifacts without creating or updating pull requests, tickets, chat, dashboards, hosted state, uploading artifacts, calling external APIs, running tests, executing Hurl, invoking models, parsing traffic state, changing `entroping run`, or embedding raw contents. |
| Work item draft | `report work-item-draft [--output <md|json>]` writes local read-only tracker draft rows from fixed optional sanitized evidence artifacts without creating, updating, syncing, assigning, labeling, commenting on, or posting to tickets, chat, automation, hosted state, PRs, dashboards, uploads, external APIs, Hurl/tests, model providers, traffic state, `entroping run`, source Hurl, raw report contents, or provider keys. |
| Work item import bundle | `report work-item-import-bundle [--output <json|csv>]` writes local read-only tracker import rows from the fixed optional work-item draft packet with spreadsheet-safe CSV cells, without creating, importing, updating, syncing, assigning, labeling, commenting on, or posting to tickets, chat, automation, hosted state, PRs, dashboards, uploads, external APIs, Hurl/tests, model providers, traffic state, `entroping run`, source Hurl, raw report contents, or provider keys. |
| Pilot outcome | `report pilot-outcome [--output <md|json>]` writes a local value-free design-partner pilot outcome packet from fixed optional sanitized evidence artifacts without creating, importing, updating, syncing, assigning, labeling, commenting on, or posting to tickets, chat, automation, hosted state, PRs, dashboards, uploads, external APIs, Hurl/tests, model providers, traffic state, `entroping run`, source Hurl, raw report contents, design-partner private notes, or provider keys. |
| Connector intent | `report connector-intent [--output <md|json>]` writes value-free future connector intents for issue tracker, chat, enterprise automation, enterprise AI, observability, and developer-experience surfaces without calling external APIs, invoking model providers, executing Hurl, running tests, mutating external systems, syncing repos/vaults/worktrees, or embedding raw contents. |
| Observability packet | `report observability-packet [--output <md|json>]` writes value-free local signal summaries for OpenTelemetry, Datadog, Splunk, Grafana, and generic observability surfaces without calling vendor APIs or mutating dashboards/monitors. |
| API inventory | `report api-inventory [--output <md|json>]` writes value-free local API style summaries for REST/OpenAPI, GraphQL, SOAP/XML, gRPC/proto, and unknown HTTP signals without generating tests or parsing traffic state. |
| Mutation readiness | `report mutation-readiness [--output <md|json>]` writes value-free local mutation/fuzz readiness summaries from generated-Hurl and optional local report evidence without executing Hurl, mutating tests, generating tests, calling providers, or parsing traffic state. |
| Evidence index | `report evidence-index [--output <md|json>]` writes value-free local evidence artifact index rows from canonical report inventory states without executing Hurl, running tests, calling providers, uploading artifacts, parsing traffic state, or embedding raw artifact contents. |
| QA brain seed | `report qa-brain-seed [--output <md|json>]` writes deterministic value-free seed metadata for future QA Brain retrieval and eval design without calling providers, fine-tuning models, running tests, executing Hurl, or embedding raw artifact contents. |
| QA brain eval plan | `report qa-brain-eval-plan [--output <md|json>]` writes deterministic value-free eval-case plan metadata for future QA Brain evaluation before retrieval or fine-tuning, without calling providers, running evals, running tests, executing Hurl, or embedding raw artifact contents. |
| QA brain retrieval plan | `report qa-brain-retrieval-plan [--output <md|json>]` writes deterministic value-free retrieval-plan metadata for future QA Brain retrieval before embeddings, vector stores, provider calls, or fine-tuning, without calling providers, running evals, running tests, executing Hurl, or embedding raw artifact contents. |
| QA brain prompt plan | `report qa-brain-prompt-plan [--output <md|json>]` writes deterministic value-free prompt-plan metadata for future QA Brain prompt design before prompt execution, provider calls, or fine-tuning, without calling providers, running evals, running tests, executing Hurl, or embedding raw artifact contents. |
| QA brain fine-tune readiness | `report qa-brain-fine-tune-readiness [--output <md|json>]` writes deterministic value-free fine-tune readiness metadata for future QA Brain proprietary-model experiments before dataset export, training, provider calls, or model packaging, without calling providers, running evals, running tests, executing Hurl, or embedding raw artifact contents. |
| QA brain model-packaging plan | `report qa-brain-model-packaging-plan [--output <md|json>]` writes deterministic value-free model-packaging plan metadata for future hosted, local, and enterprise QA Brain Pro surfaces before endpoints, packages, provider calls, dataset export, training, or model packaging, without calling providers, running evals, running tests, executing Hurl, or embedding raw artifact contents. |
| QA brain routing plan | `report qa-brain-routing-plan [--output <md|json>]` writes deterministic value-free routing-readiness metadata for future LiteLLM/OpenAI-compatible hosted, local, and enterprise QA Brain Pro surfaces before config changes, endpoints, provider calls, model invocation, dataset export, training, or model packaging, without calling providers, running evals, running tests, executing Hurl, or embedding raw artifact contents. |
| Report formats | `run --report` is repeatable and owns run artifact creation. `report bug`, `report failure-bundle`, `report delta`, `report badges`, `report redaction`, `report capture-summary`, `report policy`, `report policy-diff`, `report gate-coverage`, `report gate-injection`, `report test-quality`, `report test-pyramid`, `report external-test-evidence`, `report artifact-manifest`, `report evidence-bundle`, `report design-partner-feedback`, `report runtime-card`, `report handoff`, `report notification-packet`, `report team-evidence-readiness`, `report team-access-control-plan`, `report integration-readiness`, `report devex-readiness`, `report evidence-cloud-readiness`, `report evidence-cloud-export`, `report evidence-cloud-workspace`, `report evidence-cloud-dashboard`, `report evidence-links`, `report evidence-portal`, `report pr-evidence-card`, `report evidence-action-plan`, `report work-item-draft`, `report work-item-import-bundle`, `report pilot-outcome`, `report connector-intent`, `report observability-packet`, `report api-inventory`, `report mutation-readiness`, `report evidence-index`, `report qa-brain-seed`, `report qa-brain-eval-plan`, `report qa-brain-retrieval-plan`, `report qa-brain-prompt-plan`, `report qa-brain-fine-tune-readiness`, `report qa-brain-model-packaging-plan`, `report qa-brain-routing-plan`, `report pilot-metrics`, `report agent-bundle`, `report traceability`, `report github-annotations`, `report sarif`, `report promote-drift-baseline`, and `report review-summary` are handoff/reporting commands, not test execution commands. |

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
| `0` | Successful command, successful run, or non-CI no-match run that is informational. | `--help`, `--version`, passing `run`, passing `report delta` with no added/changed failures, passing `report badges`, passing `report failure-bundle`, passing `report redaction`, passing `report redaction --fail-on-unsafe` with zero unredacted and low-confidence records, passing `report capture-summary`, passing `report capture-summary --fail-on-unredacted` with zero unredacted records, passing `report policy`, passing `report policy-diff` without `--fail-on-change`, passing `report policy-diff --fail-on-change` with an unchanged diff, passing `report gate-coverage`, passing `report gate-coverage --fail-under` when matched-gate coverage meets the threshold, passing `report gate-injection`, passing `report test-quality`, passing `report test-quality --fail-under` when the score meets the threshold, passing `report test-pyramid`, generated `report external-test-evidence` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, covered, or blocked states, passing `report artifact-manifest`, passing `report artifact-manifest --fail-on-incomplete` with zero missing artifacts and verified audit status, ready `report evidence-bundle`, passing `report runtime-card`, generated `report handoff` evidence with present, missing, invalid, unsafe, or insufficient source states when `--fail-on-insufficient` is not set, generated `report notification-packet` evidence with present, missing, invalid, unsafe, or insufficient source states, generated `report team-evidence-readiness` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, attention, or blocked states, generated `report team-access-control-plan` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, attention, or blocked role states, generated `report integration-readiness` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, attention, or blocked family states, generated `report devex-readiness` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, attention, or blocked family states, generated `report evidence-cloud-readiness` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, attention, or blocked states, generated `report evidence-cloud-workspace` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, or blocked states, generated `report evidence-links` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, or blocked link states, generated `report evidence-portal` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, or blocked card states, generated `report pr-evidence-card` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, attention, or blocked checklist states, generated `report evidence-action-plan` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, attention, or blocked source states, generated `report work-item-draft` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, high, medium, or low draft states, generated `report work-item-import-bundle` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, high, medium, or low import states, generated `report pilot-outcome` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, high, medium, low, yes, no, or unclear states, generated `report connector-intent` evidence with ready, partial, insufficient, present, missing, invalid, unsafe, ready, attention, or blocked intent states, generated `report observability-packet` evidence with present, missing, invalid, unsafe, or insufficient source states, generated `report api-inventory` evidence with present, missing, invalid, unsafe, or insufficient source states, generated `report mutation-readiness` evidence with present, missing, invalid, unsafe, partial, or insufficient source states, generated `report evidence-index` evidence with present, missing, invalid, unsafe, partial, or insufficient artifact states, generated `report qa-brain-seed` evidence with ready, partial, insufficient, missing, or attention eval-slice states, generated `report qa-brain-eval-plan` evidence with ready, partial, insufficient, missing, or attention case states, generated `report qa-brain-retrieval-plan` evidence with ready, partial, insufficient, missing, or attention retrieval-plan states, generated `report qa-brain-prompt-plan` evidence with ready, partial, insufficient, missing, or attention prompt-plan states, generated `report qa-brain-fine-tune-readiness` evidence with ready, partial, insufficient, missing, or attention readiness states, generated `report qa-brain-model-packaging-plan` evidence with ready, partial, insufficient, missing, or attention packaging states, generated `report qa-brain-routing-plan` evidence with ready, partial, insufficient, missing, or attention routing states, generated `report pilot-metrics` evidence with known, unknown, or manual-input states, passing `report agent-bundle` with no error findings, passing `report traceability`, passing `report github-annotations`, passing `report sarif`, passing `report promote-drift-baseline`, passing `report review-summary`. |
| `1` | Runtime, configuration, report, Hurl, drift, or quality failure. | Invalid QAnstitution, missing Hurl, failing Hurl suite, drift finding with `--drift-check`, `report delta` with added or changed failures, changed effective-policy diff with `report policy-diff --fail-on-change`, malformed evidence for `report policy-diff`, missing source report for `report badges`, no failure available for `report bug` or `report failure-bundle`, missing traffic state for `report redaction` or `report capture-summary`, `report redaction --fail-on-unsafe` with unredacted or low-confidence records, `report capture-summary --fail-on-unredacted` with unredacted records, `report gate-coverage --fail-under` below the configured threshold, unreadable generated tests for `report test-quality`, `report test-quality --fail-under` below the configured threshold, local evidence read/write failure for `report test-pyramid`, unsafe output path or secret-like `report external-test-evidence` output, `report artifact-manifest --fail-on-incomplete` with missing artifacts or broken audit verification, not-ready `report evidence-bundle`, failed or attention `report runtime-card`, unsafe output path or secret-like `report handoff` output, `report handoff --fail-on-insufficient` with zero present source artifacts, unsafe output path or secret-like `report notification-packet` output, unsafe output path or secret-like `report team-evidence-readiness` output, unsafe output path or secret-like `report team-access-control-plan` output, unsafe output path or secret-like `report integration-readiness` output, unsafe output path or secret-like `report devex-readiness` output, unsafe output path or secret-like `report evidence-cloud-readiness` output, unsafe output path or secret-like `report evidence-cloud-workspace` output, unsafe output path or secret-like `report evidence-links` output, unsafe output path or secret-like `report evidence-portal` output, unsafe output path or secret-like `report pr-evidence-card` output, unsafe output path or secret-like `report evidence-action-plan` output, unsafe output path or secret-like `report work-item-draft` output, unsafe output path or secret-like `report work-item-import-bundle` output, unsafe output path or secret-like `report pilot-outcome` output, unsafe output path or secret-like `report connector-intent` output, unsafe output path or secret-like `report observability-packet` output, unsafe output path or secret-like `report api-inventory` output, unsafe output path or secret-like `report mutation-readiness` output, unsafe output path or secret-like `report evidence-index` output, unsafe output path or secret-like `report qa-brain-seed` output, unsafe output path or secret-like `report qa-brain-eval-plan` output, unsafe output path or secret-like `report qa-brain-retrieval-plan` output, unsafe output path or secret-like `report qa-brain-prompt-plan` output, unsafe output path or secret-like `report qa-brain-fine-tune-readiness` output, unsafe output path or secret-like `report qa-brain-model-packaging-plan` output, unsafe output path or secret-like `report qa-brain-routing-plan` output, unsafe or secret-like `report pilot-metrics` output, failed `report agent-bundle` findings. |
| `2` | CLI usage or unsupported-mode error. | Unknown commands, unsupported `architect build --strategy`, unsupported `report delta --output`, unsupported `report policy-diff --output`, unsupported `report redaction --output`, unsupported `report capture-summary --output`, unsupported `report gate-coverage --output`, invalid `report gate-coverage --fail-under`, unsupported `report test-quality --output`, invalid `report test-quality --fail-under`, unsupported `report test-pyramid --output`, unsupported `report external-test-evidence --output`, unsupported `report runtime-card --output`, unsupported `report handoff --output`, unsupported `report notification-packet --output`, unsupported `report team-evidence-readiness --output`, unsupported `report team-access-control-plan --output`, unsupported `report integration-readiness --output`, unsupported `report devex-readiness --output`, unsupported `report evidence-cloud-readiness --output`, unsupported `report evidence-cloud-workspace --output`, missing `report evidence-cloud-workspace --manifest`, unsupported `report evidence-links --output`, unsupported `report evidence-portal --output`, unsupported `report pr-evidence-card --output`, unsupported `report evidence-action-plan --output`, unsupported `report work-item-draft --output`, unsupported `report work-item-import-bundle --output`, unsupported `report pilot-outcome --output`, unsupported `report connector-intent --output`, unsupported `report observability-packet --output`, unsupported `report api-inventory --output`, unsupported `report mutation-readiness --output`, unsupported `report evidence-index --output`, unsupported `report qa-brain-seed --output`, unsupported `report qa-brain-eval-plan --output`, unsupported `report qa-brain-retrieval-plan --output`, unsupported `report qa-brain-prompt-plan --output`, unsupported `report qa-brain-fine-tune-readiness --output`, unsupported `report qa-brain-model-packaging-plan --output`, unsupported `report qa-brain-routing-plan --output`, unsupported `report pilot-metrics --output`, unsupported `report agent-bundle --output`, unsupported `report agent-bundle --role`, unsupported `report traceability --output`, unsupported `report review-summary --output`, unsupported `run --report`. |

This contract is intentionally small. More granular exit codes can be introduced
only through a compatibility issue and migration note.

## Report Artifacts

| Command | Artifact |
| --- | --- |
| `entroping run` | `.entroping/latest-run.json` |
| Prompt-backed `entroping architect ...` | `.entroping/agent-runs/*.json` |
| `entroping freeze` / `freeze --mock` / `map --export png` | `reports/approvals/*.json` |
| `entroping run --report json` | `reports/run-latest.json` |
| `entroping run --dry-run --report json` | `reports/run-plan.json` |
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
| `entroping report redaction --fail-on-unsafe` | `reports/redaction-review.md` or `reports/redaction-review.html` |
| `entroping report capture-summary --output md` | `reports/capture-summary.md` |
| `entroping report capture-summary --output json` | `reports/capture-summary.json` |
| `entroping report policy --output md` | `reports/effective-policy.md` |
| `entroping report policy --output json` | `reports/effective-policy.json` |
| `entroping report policy-diff --output md|json` | `stdout Effective Policy Diff Markdown/JSON` |
| `entroping report gate-coverage --output md` | `reports/gate-coverage.md` |
| `entroping report gate-coverage --output json` | `reports/gate-coverage.json` |
| `entroping report gate-injection --output md` | `reports/gate-injection.md` |
| `entroping report gate-injection --output json` | `reports/gate-injection.json` |
| `entroping report test-quality --output md` | `reports/test-quality.md` |
| `entroping report test-quality --output json` | `reports/test-quality.json` |
| `entroping report test-pyramid --output md` | `reports/test-pyramid.md` |
| `entroping report test-pyramid --output json` | `reports/test-pyramid.json` |
| `entroping report external-test-evidence --output md` | `reports/external-test-evidence.md` |
| `entroping report external-test-evidence --output json` | `reports/external-test-evidence.json` |
| `entroping report artifact-manifest [--fail-on-incomplete]` | `reports/artifact-manifest.json`, or custom `--output` path |
| `entroping report evidence-bundle` | `reports/evidence-bundle.json` |
| `entroping report design-partner-feedback` | `reports/design-partner-feedback.json` |
| `entroping report runtime-card --output md` | `reports/runtime-card.md` |
| `entroping report runtime-card --output json` | `reports/runtime-card.json` |
| `entroping report handoff --output md` | `reports/handoff.md` |
| `entroping report handoff --output json` | `reports/handoff.json` |
| `entroping report notification-packet --output md` | `reports/notification-packet.md` |
| `entroping report notification-packet --output json` | `reports/notification-packet.json` |
| `entroping report team-evidence-readiness --output md` | `reports/team-evidence-readiness.md` |
| `entroping report team-evidence-readiness --output json` | `reports/team-evidence-readiness.json` |
| `entroping report team-access-control-plan --output md` | `reports/team-access-control-plan.md` |
| `entroping report team-access-control-plan --output json` | `reports/team-access-control-plan.json` |
| `entroping report integration-readiness --output md` | `reports/integration-readiness.md` |
| `entroping report integration-readiness --output json` | `reports/integration-readiness.json` |
| `entroping report devex-readiness --output md` | `reports/devex-readiness.md` |
| `entroping report devex-readiness --output json` | `reports/devex-readiness.json` |
| `entroping report evidence-cloud-readiness --output md` | `reports/evidence-cloud-readiness.md` |
| `entroping report evidence-cloud-readiness --output json` | `reports/evidence-cloud-readiness.json` |
| `entroping report evidence-cloud-export --output md` | `reports/evidence-cloud-export.md` |
| `entroping report evidence-cloud-export --output json` | `reports/evidence-cloud-export.json` |
| `entroping report evidence-cloud-workspace --manifest <path> --output md` | `reports/evidence-cloud-workspace.md` |
| `entroping report evidence-cloud-workspace --manifest <path> --output json` | `reports/evidence-cloud-workspace.json` |
| `entroping report evidence-cloud-dashboard --manifest <path> --output html` | `reports/evidence-cloud-dashboard.html` |
| `entroping report evidence-cloud-dashboard --manifest <path> --output json` | `reports/evidence-cloud-dashboard.json` |
| `entroping report evidence-links --output md` | `reports/evidence-links.md` |
| `entroping report evidence-links --output json` | `reports/evidence-links.json` |
| `entroping report evidence-portal --output html` | `reports/evidence-portal.html` |
| `entroping report evidence-portal --output json` | `reports/evidence-portal.json` |
| `entroping report pr-evidence-card --output md` | `reports/pr-evidence-card.md` |
| `entroping report pr-evidence-card --output json` | `reports/pr-evidence-card.json` |
| `entroping report evidence-action-plan --output md` | `reports/evidence-action-plan.md` |
| `entroping report evidence-action-plan --output json` | `reports/evidence-action-plan.json` |
| `entroping report work-item-draft --output md` | `reports/work-item-draft.md` |
| `entroping report work-item-draft --output json` | `reports/work-item-draft.json` |
| `entroping report work-item-import-bundle --output json` | `reports/work-item-import-bundle.json` |
| `entroping report work-item-import-bundle --output csv` | `reports/work-item-import-bundle.csv` |
| `entroping report pilot-outcome --output md` | `reports/pilot-outcome.md` |
| `entroping report pilot-outcome --output json` | `reports/pilot-outcome.json` |
| `entroping report connector-intent --output md` | `reports/connector-intent.md` |
| `entroping report connector-intent --output json` | `reports/connector-intent.json` |
| `entroping report observability-packet --output md` | `reports/observability-packet.md` |
| `entroping report observability-packet --output json` | `reports/observability-packet.json` |
| `entroping report api-inventory --output md` | `reports/api-inventory.md` |
| `entroping report api-inventory --output json` | `reports/api-inventory.json` |
| `entroping report mutation-readiness --output md` | `reports/mutation-readiness.md` |
| `entroping report mutation-readiness --output json` | `reports/mutation-readiness.json` |
| `entroping report evidence-index --output md` | `reports/evidence-index.md` |
| `entroping report evidence-index --output json` | `reports/evidence-index.json` |
| `entroping report qa-brain-seed --output md` | `reports/qa-brain-seed.md` |
| `entroping report qa-brain-seed --output json` | `reports/qa-brain-seed.json` |
| `entroping report qa-brain-eval-plan --output md` | `reports/qa-brain-eval-plan.md` |
| `entroping report qa-brain-eval-plan --output json` | `reports/qa-brain-eval-plan.json` |
| `entroping report qa-brain-retrieval-plan --output md` | `reports/qa-brain-retrieval-plan.md` |
| `entroping report qa-brain-retrieval-plan --output json` | `reports/qa-brain-retrieval-plan.json` |
| `entroping report qa-brain-prompt-plan --output md` | `reports/qa-brain-prompt-plan.md` |
| `entroping report qa-brain-prompt-plan --output json` | `reports/qa-brain-prompt-plan.json` |
| `entroping report qa-brain-fine-tune-readiness --output md` | `reports/qa-brain-fine-tune-readiness.md` |
| `entroping report qa-brain-fine-tune-readiness --output json` | `reports/qa-brain-fine-tune-readiness.json` |
| `entroping report qa-brain-model-packaging-plan --output md` | `reports/qa-brain-model-packaging-plan.md` |
| `entroping report qa-brain-model-packaging-plan --output json` | `reports/qa-brain-model-packaging-plan.json` |
| `entroping report qa-brain-routing-plan --output md` | `reports/qa-brain-routing-plan.md` |
| `entroping report qa-brain-routing-plan --output json` | `reports/qa-brain-routing-plan.json` |
| `entroping report pilot-metrics --output md` | `reports/pilot-metrics.md` |
| `entroping report pilot-metrics --output json` | `reports/pilot-metrics.json` |
| `entroping report agent-bundle --output md` | `reports/agent-bundle.md` |
| `entroping report agent-bundle --output json` | `reports/agent-bundle.json` |
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
