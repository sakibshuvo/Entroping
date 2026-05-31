# Entroping Implementation Plan

**Date:** 2026-05-31
**Status:** v0.2 adoption and onboarding track

## Objective

Keep the open-source alpha credible by preserving the deterministic governance
loop while tightening the places that can create requirement drift, weak context
handoff, or multi-agent workflow friction:

```text
init -> validate QAnstitution -> discover Hurl tests -> inject gates into temp files -> run Hurl -> emit reports
```

The repo should remain usable as an Obsidian vault, a GitHub issue-driven
project, and a Codex workspace with fast context rehydration.

## Current Baseline

- Product, technical, user, architecture, and evolution docs are organized under `docs/`.
- Root `README.md` and `00_INDEX.md` are the main public and vault entry points.
- Python package and CLI implementation exist under `src/entroping/`.
- CLI command surface is locked to v4.1.
- Pydantic QAnstitution models and typed condition parsing are in place.
- Bridge compiler boundaries are implemented for OpenAPI-to-Hurl, policy-to-Hurl,
  traffic-to-Hurl, traffic-to-WireMock, traffic-to-graph, story traceability,
  and managed-block Hurl merges.
- CI runs `scripts/regression.sh --security`, `scripts/audit_quality.sh`, and
  the live Hurl demo smoke.
- Security scan completed on 2026-05-29 and found one low-severity optional proxy dependency issue; the proxy dependency floor was raised to `mitmproxy>=12.2.3`, vulnerable transitives were refreshed, and the all-extras audit is now clean.
- Project-local `AGENTS.md` now captures repository-specific implementation rules.
- `docs/meta/AUTONOMOUS_DEVELOPMENT.md` defines the Codex-first loop, Spec Kit pilot path, and future OpenCode/oMLX worker plan.
- `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, `.github/pull_request_template.md`, and `scripts/feature_gate.sh` define the executable delivery gates for feature work.
- `docs/meta/ISSUE_TRACKING.md`, `docs/meta/TEST_STRATEGY.md`, `docs/meta/PROJECT_PROGRESS.md`, `scripts/regression.sh`, and `scripts/audit_quality.sh` define issue tracking, regression coverage, quality audit coverage, and simple phase-level progress tracking.
- `scripts/community_profile_audit.sh` and `.github/workflows/scorecard.yml` provide public trust-signal hygiene without adding a pull-request gate.
- Apache-2.0 licensing and package metadata are in place for the public core; keep future commercial cloud, model, policy-pack, or enterprise surfaces outside the open core unless explicitly relicensed.
- `scripts/start_issue.sh` creates issue-scoped worktrees and deterministic session prompts for multi-session Codex/OpenCode work; `scripts/finish_issue.sh` verifies merged PRs and safely removes completed local worktrees.
- Eye capture now has security-first traffic models, pre-persistence redaction, bounded SQLModel-backed SQLite state, and capture-only `watch` wiring through a lazy-loaded mitmproxy adapter.
- Issues #1 through #85, plus validation fixes #95 and #97, are integrated.
  The shipped alpha covers init/doctor, QAnstitution loading/import validation,
  Hurl discovery and metadata, gate injection, deterministic Hurl subprocess
  execution, JSON/JUnit/HTML/drift reports, bug templates, OpenAPI generation
  and audit, env-file variables, live Hurl CI smoke, Brain/LiteLLM prompt
  generation and refactor paths, managed-block merges, architecture boundary
  tests, capture-only `watch`, `freeze`, WireMock mocks, dependency maps,
  package artifact checks, bounded parallel run, and a read-only Studio status
  shell.

## Completed Milestone: Deterministic Core

The deterministic path is available and should remain the regression anchor:

1. Make `entroping init` create a minimal `qanstitution.yaml` and safe project skeleton. **Done in issue #1.**
2. Make `entroping doctor` validate local config, Hurl availability, and optional tools without network calls. **Done in issue #1.**
3. Add QAnstitution file loading and local import handling. **Done in issue #1.**
4. Implement Hurl test discovery and metadata parsing. **Done in issue #2.**
5. Implement QAnstitution gate matching and gate-to-Hurl assertion compilation. **Done in issue #3.**
6. Implement Hurl subprocess execution with timeout, bounded output, cleanup, and redaction. **Done in issue #4.**
7. Emit JSON and JUnit reports. **Done in issue #5.**
8. Wire the checkout demo into README quickstart. **Done in issue #6.**

## Current Milestone: Validation And Hardening

1. Keep public alpha license and package metadata explicit. **Done in issue #58.**
2. Keep capture-only `watch` separate from `freeze` and `map`. **Done in issue #60.**
3. Design traffic-to-Hurl and dependency export before implementation. **Done in issue #59.**
4. Publish `v0.1.0-alpha` only after local and CI release evidence. **Done from commit `abd08c0`.**
5. Keep post-alpha additions small, issue-backed, release-gated, and reflected in
   this context file.
6. Use the validation queue to remove drift, workflow friction, and maintenance
   hotspots before adding larger product surface.

Issue #59 outcome leaves behind `docs/technical/FREEZE_MAP_PLAN.md`, ADR-0008,
and focused implementation issues #66, #67, #68, and #69 for
filtering/sessioning, traffic-to-Hurl freeze generation, safe `freeze` CLI
writes, and dependency map exports. Issues #66 through #69 are implemented;
issue #75 adds WireMock-compatible `freeze --mock` output, and issue #80 adds
optional Graphviz-backed PNG dependency map rendering.
Issues #82 through #85 added package install polish, bounded parallel Hurl
execution, deterministic drift reporting, and the read-only Studio shell.
Issues #95 and #97 removed the remaining generic Architect build placeholder
path and ignored validation coverage artifacts. Issue #93 added the heavier
local quality audit gate for coverage, complexity, maintainability, and
dead-code discovery checks. Issue #94 added the symmetric finish workflow for
post-merge worktree, local branch, label, and project-board cleanup.
Issue #91 implemented the bridge-level story traceability report for Hurl
metadata without adding business-system API clients. Issue #106 exposed that
local report through `entroping report traceability --output md` while keeping
external sync out of scope.
Issue #109 added community-profile auditing and a scheduled/manual OpenSSF
Scorecard workflow without making Scorecard a required pull-request check.
Issue #110 extended drift reports with optional value-free response fingerprints
for status code, selected stable headers, and JSON body shape paths.
Issue #176 extended drift reports with conservative material latency regression
warnings from reviewed `duration_ms` baselines, without adding flags or storing
response values.
Issue #108 added a text/SVG launch asset kit under `docs/assets/launch/`,
linked it from the README and Obsidian index, and documented the concrete
publish order in the growth plan without committing generated reports, GIFs, or
PNG screenshots.
Issue #166 removed maintainer-local temp paths from launch rebuild commands and
added a regression guard so public launch docs stay copy/paste portable.
Issue #168 made `scripts/context_pack.sh --mode source` source-archive paths
configurable through `ENTROPING_SOURCE_ROOT`, with a sibling `../entroping-specs`
default instead of a maintainer-local script constant.
Issue #170 replaced maintainer-local repo/source paths in agent and Obsidian
workflow docs with `<repo-root>`, `<source-archive>`, and `ENTROPING_SOURCE_ROOT`
guidance so external agents and contributors can reuse the same flow.
Issue #172 refreshed the public README status language so it describes the repo
as the active alpha implementation without overclaiming production stability.
Issue #174 rewrote the README as a public open-source front door: sourced hype
and runtime-governance positioning first, two-minute live demo proof next, and
deep Obsidian/spec inventory later.
Issue #179 improved Architect validation UX for invalid provider JSON and
parser-rejected Hurl while preserving no-write behavior and raw output redaction.
Issue #90 moved deterministic run orchestration behind `core.run_workflow`,
leaving the CLI adapter responsible for option normalization, output, and exit
mapping.
Issue #184 added a good-first-issue walkthrough. Issue #189 added a downstream
GitHub Actions starter workflow. Issue #195 documents LiteLLM, local Qwen
through Ollama/oMLX, optional `api_base` and `api_key_env` agent metadata, and
the no-provider CI boundary.
Issue #186 adds the TestPyPI-first package-index release runbook, including
Trusted Publishing feasibility, token-free GitHub environments, PEP 440 alpha
versioning, PyPI publish policy, and yank/new-version rollback guidance.
Issue #188 chooses MkDocs Material for the public docs site, adds a minimal
`mkdocs.yml` plus `docs/index.md` scaffold, and keeps the canonical Markdown
tree as the source instead of duplicating docs.

Issue #96 is complete. PR #105 merged the post-alpha security review hardening on
2026-05-30 after fixing 14 validated candidates across Brain redaction, Hurl
subprocess isolation, filesystem symlink boundaries, traffic redaction/body
limits, OpenAPI compilation/audit safety, policy gate semantics, Markdown
escaping, generated Hurl writes, and live-demo workdir safety.

## Current Slice: Source Reconciliation, SQLModel State, And Agent Workflow Alignment

The 2026-05-29 NotebookLM Markdown export is the final current source snapshot.
Keep older Gemini and dated NotebookLM files as historical evidence unless a
specific contradiction is promoted into the canonical product docs or an ADR.

Implementation focus:

- Preserve SQLite as local `.entroping/state.db` runtime state.
- Use SQLModel as the typed persistence layer for traffic state.
- Keep traffic persistence redaction-first and bounded by retention.
- Refresh source-map and progress docs so future sessions do not follow stale
  paths or stale current-issue markers.
- Add deterministic context packs so Codex, Claude Code, OpenCode, Gemini,
  NotebookLM, and local Qwen can start from the same curated repo evidence.
- Keep Obsidian as the first brain while source exports remain archival until
  promoted into issues, ADRs, canonical docs, tests, or scripts.
- Document the open-source growth and open-core monetization path without
  weakening the Apache-2.0 public core.

Completed security-review context: repository-wide scan artifacts were written
under `/tmp/codex-security-scans/Entroping/eb08827323c6_20260530T160200Z`, all
14 deduplicated candidates have validation/verification ledgers, and no
unresolved finding remained in the merged branch.

Implemented boundaries:

- Prompt and provider-error redaction now catch cookie, API-key, password, Basic
  auth, token, and key-value secret shapes while allowing templated Hurl auth
  placeholders.
- Hurl execution uses a minimal subprocess environment instead of inheriting the
  parent shell environment.
- Env loading, report writing, drift reads/writes, traffic state, and generated
  Hurl writes reject symlinked path components before resolving or writing.
- Traffic redaction strips URL userinfo, handles JSON subtypes structurally, and
  caps textual body extraction before decode/redaction work.
- OpenAPI compilation rejects secret-like fallback variables and Hurl template
  delimiters in JSON object keys.
- OpenAPI audit coverage requires matching method/path evidence, not only
  spoofable `operation_id` metadata.
- Policy gates reject no-op comments and Hurl section headers.
- Markdown renderers for audit and traceability escape HTML metacharacters.
- The live demo smoke script refuses non-empty custom workdirs instead of
  deleting their contents.

Latest local evidence:

- `PYTHONPATH=src uv run pytest tests/test_openapi_loader.py tests/test_release_docs.py -q`: 15 passed.
- `PYTHONPATH=src uv run pytest tests/test_openapi_loader.py --cov=entroping.core.openapi_loader --cov-report=term-missing -q`: 10 passed; `core.openapi_loader` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_validator.py --cov=entroping.core.hurl_validator --cov-report=term-missing -q`: 5 passed; `core.hurl_validator` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_merge.py tests/test_architect_output_parser.py --cov=entroping.bridge.merge --cov=entroping.brain.output_parser --cov-report=term-missing -q`: 23 passed; `bridge.merge` and `brain.output_parser` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_to_graph.py --cov=entroping.bridge.traffic_to_graph --cov-report=term-missing -q`: 6 passed; `bridge.traffic_to_graph` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_report_writer.py --cov=entroping.core.report_writer --cov-report=term-missing -q`: 12 passed; `core.report_writer` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_redactor.py --cov=entroping.core.traffic_redactor --cov-report=term-missing -q`: 10 passed; `core.traffic_redactor` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_brain_prompt_builder.py --cov=entroping.brain.prompt_builder --cov-report=term-missing -q`: 16 passed; `brain.prompt_builder` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_story_traceability.py --cov=entroping.bridge.story_traceability --cov-report=term-missing -q`: 6 passed; `bridge.story_traceability` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_store.py --cov=entroping.core.traffic_store --cov-report=term-missing -q`: 10 passed; `core.traffic_store` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_brain_safety.py --cov=entroping.brain.safety --cov-report=term-missing -q`: 9 passed; `brain.safety` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_brain_persona_loader.py tests/test_litellm_client.py --cov=entroping.brain.persona_loader --cov=entroping.brain.litellm_client --cov-report=term-missing --cov-fail-under=100 -q`: 24 passed; Brain provider/persona boundary modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_metadata.py --cov=entroping.models.hurl --cov-report=term-missing -q`: 11 passed; `models.hurl` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_discovery.py --cov=entroping.core.hurl_discovery --cov-report=term-missing -q`: 11 passed; `core.hurl_discovery` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_policy_to_hurl.py --cov=entroping.bridge.policy_to_hurl --cov-report=term-missing -q`: 17 passed; `bridge.policy_to_hurl` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_gate_injector.py --cov=entroping.core.gate_injector --cov-report=term-missing -q`: 12 passed; `core.gate_injector` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_hurl_runner.py --cov=entroping.core.hurl_runner --cov-report=term-missing -q`: 20 passed; `core.hurl_runner` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_sessions.py tests/test_traffic_to_hurl.py tests/test_traffic_to_wiremock.py --cov=entroping.bridge.traffic_sessions --cov=entroping.bridge.traffic_to_hurl --cov=entroping.bridge.traffic_to_wiremock --cov-report=term-missing -q`: 38 passed; targeted traffic compiler modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_config_loader.py tests/test_config_writer.py tests/test_env_loader.py --cov=entroping.core.config_loader --cov=entroping.core.config_writer --cov=entroping.core.env_loader --cov-report=term-missing -q`: 58 passed; targeted config/env modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_openapi_to_hurl.py tests/test_architect_audit.py --cov=entroping.bridge.openapi_to_hurl --cov=entroping.bridge.openapi_audit --cov-report=term-missing -q`: 39 passed; `bridge.openapi_to_hurl` and `bridge.openapi_audit` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_safe_write.py --cov=entroping.core.safe_write --cov-report=term-missing -q`: 12 passed; `core.safe_write` at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_dependency_mapper.py tests/test_drift_report.py tests/test_traffic_models.py tests/test_studio_status.py --cov=entroping.core.dependency_mapper --cov=entroping.core.drift_report --cov=entroping.models.traffic --cov=entroping.studio.status --cov-report=term-missing --cov-fail-under=100 -q`: 49 passed; targeted support modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_traffic_proxy.py tests/test_freeze.py --cov=entroping.core.traffic_proxy --cov=entroping.core.freeze --cov-report=term-missing --cov-fail-under=100 -q`: 42 passed; Eye proxy/freeze modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_architect_prompt_build.py tests/test_architect_refactor.py tests/test_architect_writer.py --cov=entroping.brain.architect_build --cov=entroping.brain.architect_refactor --cov=entroping.brain.architect_writer --cov-report=term-missing --cov-fail-under=100 -q`: 57 passed; Architect workflow modules at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_cli.py --cov=entroping.cli.main --cov-report=term-missing --cov-fail-under=100 -q`: 85 passed; CLI adapter at 100 percent coverage.
- `PYTHONPATH=src uv run pytest tests/test_ci_workflow.py tests/test_release_docs.py tests/test_agent_workflow_docs.py -q`: 15 passed.
- `scripts/regression.sh --security`: 682 passed; Bandit and default/all-extras dependency audits passed.
- `scripts/audit_quality.sh`: 682 passed with the default 100 percent coverage gate, 100.00 percent total coverage, and passing Radon/Vulture gates.

## Completed Slice: Issue #90 Run Workflow Extraction

Outcome: `entroping run` no longer owns discovery, env loading, gate injection,
Hurl execution, report writes, drift comparison, and exit-code policy directly
inside the Typer adapter.

Implemented boundaries:

- `core.run_workflow.execute_run_workflow` owns the deterministic governance
  loop and returns a typed `RunWorkflowResult`.
- The CLI still normalizes `--tag` and `--report`, prints user-facing messages,
  and maps no-match behavior to CI/non-CI exit codes.
- JSON, JUnit, HTML, drift, latest-run state, parallel workers, environment
  variables, temporary execution cleanup, and drift exit-code behavior are
  preserved.
- Focused core tests cover report writing, no-match handling, temporary cleanup,
  and drift exit-code policy.
- `entroping run` CLI complexity dropped from Radon E(34) to C(14).

## Completed Slice: Issue #91 Story Traceability Bridge

Outcome: the dedicated `story_traceability.py` bridge is no longer a placeholder
and the docs now match the shipped local behavior.

Implemented boundaries:

- Discovered Hurl metadata compiles into story/test records with story IDs,
  owners, external doc URLs, tags, and linked test paths.
- Missing `story_id` metadata is reported deterministically.
- One external `doc_url` mapped to multiple story IDs is reported as a
  traceability conflict, while repeated tests for the same story remain valid.
- Markdown rendering escapes table cells for safe local review.
- No Jira, Notion, Linear, monday.com, or other business-system clients are
  introduced in the bridge layer.

## Completed Slice: Issue #106 Traceability Report CLI

Outcome: the story traceability bridge is available through the reporting CLI
without expanding into external business-system integrations.

Implemented boundaries:

- `entroping report traceability --output md` renders the local Markdown
  story/test traceability report from discovered Hurl metadata.
- Empty suites return a successful report with no story-linked tests.
- Missing `story_id` metadata and conflicting external `doc_url` links return a
  failing exit code for CI or reviewer use.
- Unsupported output formats are rejected; Markdown is the only public format.
- Focused CLI coverage remains at 100 percent for `entroping.cli.main`.

## Completed Slice: Issue #94 Finish-Issue Workflow

Outcome: completed issue sessions can be cleaned up deterministically after PR
merge instead of relying on manual branch/worktree judgement.

Implemented boundaries:

- `scripts/finish_issue.sh <issue-number>` verifies the GitHub issue is closed,
  identifies its closing PR, confirms the PR is merged, and checks reported CI
  statuses before local deletion.
- The script refuses dirty, unregistered, branch-mismatched, or current
  worktree removal.
- Squash-merged local branches are deleted only after the closing PR and checks
  are verified.
- GitHub issue labels and Project status are updated on a best-effort basis,
  with warnings when permissions are unavailable.
- Temporary-repo tests cover dry-run output, unsafe dirty worktree rejection,
  and successful clean worktree plus squash-merged branch cleanup.

## Completed Slice: Issue #93 Quality Audit Gate

Outcome: marathon validation and release hardening now have a repeatable local
quality audit separate from the faster regression suite.

Implemented boundaries:

- `scripts/audit_quality.sh` runs the full suite with `pytest-cov` and a default
  100 percent coverage threshold.
- Radon cyclomatic complexity and maintainability-index checks are enforced with
  documented environment thresholds.
- Vulture dead-code discovery runs with a curated confidence threshold.
- Coverage and static-analysis JSON outputs are written only under ignored
  `reports/`, and transient `.coverage` state is removed on exit.
- The script has help, dry-run, and unknown-option smoke tests.

## Completed Slice: Issue #148 CI Security And Quality Enforcement

Outcome: GitHub Actions no longer treats the security and quality gates as
local-only marathon proof.

Implemented boundaries:

- The primary CI checks job runs `scripts/regression.sh --security`, so Bandit
  and default/all-extras dependency audits are part of pull-request and `main`
  push verification.
- The workflow runs `scripts/audit_quality.sh` in a separate `quality-audit`
  job after the fast security regression job.
- The quality-audit job uploads ignored `reports/` artifacts for review when
  available.
- README and `docs/meta/TEST_STRATEGY.md` now distinguish CI-enforced gates from
  local release-owner package/live-demo release checks.

## Completed Slice: Issue #150 Live-Demo Hurl Checksum Pinning

Outcome: the CI live-demo job no longer trusts a `.sha256` sidecar downloaded
from the same upstream release at runtime.

Implemented boundaries:

- `.github/workflows/ci.yml` pins `HURL_VERSION` and the reviewed
  `HURL_SHA256` value for the Linux archive used by `live-demo-smoke`.
- The workflow keeps bounded archive download retries but verifies the archive
  against the in-repo checksum before extracting it.
- The release checklist documents the Hurl bump process: update version,
  compute `sha256sum` locally, update `HURL_SHA256`, and let CI prove the demo
  path.

## Completed Slice: Issue #149 Atomic Artifact Writes

Outcome: core artifact writers now share one durable, symlink-safe write path
instead of maintaining separate direct-write and temp-file implementations.

Implemented boundaries:

- `core.safe_write` writes text and binary artifacts through destination-local
  temporary files, flushes and fsyncs them, rejects symlinked targets and parent
  components, and atomically replaces final targets.
- Existing targets are preserved when temporary writes or replacements fail.
- Freeze-generated Hurl, WireMock mappings, PNG dependency maps, drift reports,
  JSON/JUnit/HTML run reports, and bug reports all route through the shared
  helper while preserving their module-specific public error types.
- `core.safe_write` and `core.report_writer` have 100 percent focused module
  coverage for the touched behavior.

## Completed Slice: Issue #146 Deterministic Support-Module Coverage

Outcome: the remaining deterministic support modules from the issue #112
coverage queue now have focused 100 percent coverage without provider calls,
live network, or UI sessions.

Implemented boundaries:

- `core.dependency_mapper` coverage includes missing state, unsupported export
  values, all printable export modes, traffic-store error wrapping, internal PNG
  misuse protection, Graphviz `OSError`, empty renderer output, and existing PNG
  safety behavior.
- `core.drift_report` coverage includes malformed baseline JSON shapes, invalid
  baseline records, optional metadata defaults, non-file baseline paths, and
  existing symlink/report-write behavior.
- `models.traffic` coverage includes content-type, method, URL, header, tab
  allowance, and timezone-aware timestamp validation.
- `studio.status` coverage includes missing optional Textual dependency,
  missing QAnstitution, QAnstitution load errors, latest-run load errors,
  no-report rendering, and existing latest-run state rendering.

## Completed Slice: Issue #145 Eye Proxy And Freeze Coverage

Outcome: Eye capture and freeze edge cases now have focused 100 percent coverage
without live proxy sessions, external network traffic, or real mitmproxy
processes.

Implemented boundaries:

- `core.traffic_proxy` coverage includes WatchConfig bounds, missing and
  malformed mitmproxy runtime imports, flow-shape errors, target-scope matching,
  body/header variants, bounded text extraction, timestamp fallbacks, and fake
  `run_watch` addon registration.
- `core.freeze` coverage includes missing/empty state, successful Hurl and
  WireMock artifact generation, name/service validation, Hurl validation error
  wrapping, invalid WireMock JSON, path traversal/POSIX/suffix validation,
  non-file targets, resolved symlink escapes, and existing symlink/atomic-write
  protections.

## Completed Slice: Issue #144 Architect Workflow Coverage

Outcome: Architect prompt-build, refactor, and staged writer edge cases now have
focused 100 percent coverage without provider calls or live Hurl execution.

Implemented boundaries:

- `brain.architect_build` coverage includes merge-mode Architect-owned targets,
  manual managed-block merges, invalid and unknown managed blocks, tag metadata
  replacement/insertion, unsafe merge targets, size/encoding/read errors, and
  resolved symlink escapes.
- `brain.architect_refactor` coverage includes empty/unsafe target globs,
  resolved symlink escapes, directory targets, invalid managed blocks,
  stat/read/encoding/empty target errors, and selected-target enforcement
  before writes.
- `brain.architect_writer` coverage includes unsafe refactor paths, resolved
  escapes, symlink and non-file preflight failures, blank-header helpers,
  newline preservation, atomic replacement failures, and temporary-write
  failures.

## Completed Slice: Issue #157 Brain Provider And Persona Boundary Coverage

Outcome: the remaining Brain provider/persona boundaries now have focused 100
percent coverage without invoking LiteLLM providers or external networks.

Implemented boundaries:

- `brain.persona_loader` coverage includes URL/absolute/non-Markdown/missing
  persona sources, symlinked persona paths, stat/read failures, size limits,
  UTF-8 errors, empty content, control characters, and secret-like content.
- `brain.litellm_client` coverage includes optional dependency absence,
  installed modules without `completion`, provider boundary re-raise behavior,
  redacted provider exceptions, malformed choices/content responses, object
  attribute response shapes, usage type fallbacks, model defaulting, and lazy
  completion loading.

## Completed Slice: Issue #159 CLI Adapter Coverage

Outcome: the Typer CLI adapter now has focused 100 percent coverage without
changing the locked v4.1 command surface.

Implemented boundaries:

- Doctor/config coverage includes missing Hurl, missing/invalid QAnstitution,
  no-source/no-agent display, source field display, description display, and
  agent `max_tokens` display.
- Architect/watch/run/report coverage includes unsupported strategies, missing
  audit spec, keyboard-interrupted capture, no-match CI exit policy, failed
  stdout printing, report-bug no-failure handling, and report writer errors.
- Helper coverage includes audit focus normalization, remote/absolute spec
  reference handling, generated Hurl path rejection, symlinked generated output
  rejection, non-OpenAPI overwrite rejection, and outside-CWD path display.

## Completed Slice: Issue #112 100 Percent Coverage Release Gate

Outcome: 100 percent meaningful coverage is now the default quality-audit gate,
not only the target tracked by issue slices.

Implemented boundaries:

- `scripts/audit_quality.sh` defaults `ENTROPING_COVERAGE_FAIL_UNDER` to `100`
  and documents the default in help output.
- `docs/meta/TEST_STRATEGY.md` states that `scripts/audit_quality.sh` enforces
  the 100 percent default, and any lower threshold must be an explicit tracked
  override.
- The latest full local quality audit passed with 682 tests, 100.00 percent
  total coverage, and passing Radon plus Vulture gates.

## Completed Slice: Issue #85 Read-Only Studio Status Shell

Outcome: `entroping studio --env <name>` no longer uses the generic placeholder
for the supported local read-only path.

Implemented boundaries:

- The command requires the optional Studio/Textual extra and returns actionable
  `uv sync --extra studio` guidance when it is missing.
- The first status shell reads only local state: QAnstitution project, latest
  run summary, existing report artifacts, and traffic-state availability.
- No tests, config, `.entroping` state, or report files are mutated by Studio.
- Full interactive TUI navigation, failure drilldown, and traffic-session views
  remain later Studio work.

## Completed Slice: Issue #84 Deterministic Drift Report MVP

Outcome: `entroping run --drift-check` and `--report drift` compare the current
sanitized run report against a local baseline without invoking AI providers.

Implemented boundaries:

- The MVP baseline path is `.entroping/drift-baseline.json`; a reviewed
  `.entroping/latest-run.json` can be copied there as the first baseline.
- Drift comparison is deterministic and limited to current structured run-report
  fields: test path, Hurl status, exit code, injected QAnstitution rule IDs,
  and optional value-free response fingerprints.
- Missing baselines produce an actionable CLI message and a machine-readable
  `missing_baseline` finding when `--report drift` is requested.
- `--drift-check` affects the final exit code only after Hurl execution
  completes, so Hurl failures are not hidden by baseline problems.

## Completed Slice: Issue #110 Structured Response Drift

Outcome: drift reports can compare optional response fingerprints without
storing brittle or sensitive response values.

Implemented boundaries:

- Run reports can include response status code, selected stable headers, and
  JSON body shape paths when Hurl output provides parseable response detail.
- Drift comparison ignores response details when the baseline has none, keeping
  older baselines compatible.
- Volatile headers and full response body values are not drift truth.
- Missing current response fingerprints are reported when the baseline expected
  one.

## Completed Slice: Issue #176 Latency Regression Drift

Outcome: drift reports can warn when a current Hurl test becomes materially
slower than a reviewed run baseline.

Implemented boundaries:

- Baselines copied from `.entroping/latest-run.json` now preserve optional
  `duration_ms` values per test.
- Latency findings require both a minimum 100 ms increase and a minimum 25
  percent increase from a positive baseline duration, keeping tiny local timing
  noise out of drift reports.
- Findings are warnings and include only duration/increase numbers, never
  response bodies, captured traffic, cookies, tokens, or raw provider data.

## Completed Slice: Issue #179 Architect Validation UX

Outcome: prompt-backed Architect failures are easier to act on without making
provider output or parser streams visible.

Implemented boundaries:

- Invalid provider JSON now reports that Architect output validation failed
  before write and names the expected `summary` / `warnings` / `edits[]` shape.
- Parser-rejected Hurl now reports that Hurl validation failed before write.
- Both paths still print the redacted root error, preserve all-or-nothing writes,
  and keep raw model output plus parser stdout/stderr out of the CLI.

## Completed Slice: Issue #83 Bounded Parallel Hurl Execution

Outcome: `entroping run --parallel` executes multiple Hurl files concurrently
without changing deterministic reporting semantics.

Implemented boundaries:

- Serial execution remains the default for `entroping run`.
- `--parallel` uses `settings.parallel_workers` from `qanstitution.yaml`, with
  a positive bounded worker count and no LLM involvement.
- Each file still goes through the existing subprocess boundary, timeout,
  output-bound, redaction, and variables-file cleanup behavior.
- Suite results are restored to input order before JSON, JUnit, HTML, latest-run,
  and CLI failure output are built.

## Completed Slice: Issue #82 Distribution Install Polish

Outcome: make the source-distributed alpha easier to evaluate without PyPI,
TestPyPI, Homebrew, or hosted-service credentials.

Implemented boundaries:

- `scripts/package_check.sh` removes `dist/`, builds wheel/sdist artifacts with
  `uv build`, and verifies release-critical metadata before any publishing
  claim.
- The release gate now runs package verification before regression/security
  checks and live demo proof.
- README, user guide, TDS, and release checklist document GitHub branch/tag
  install paths, local editable installs, and the fact that package-index
  publishing is not automated yet.

## Completed Slice: Issue #80 PNG Dependency Map Rendering

Outcome: `entroping map --export png` writes `reports/dependency-map.png` when
local Graphviz `dot` is available, while preserving actionable missing-renderer
errors when it is not.

Implemented boundaries:

- DOT text still comes from the pure `bridge.traffic_to_graph` compiler.
- PNG rendering lives in `core.dependency_mapper` as a subprocess adapter using
  argument arrays, binary stdin/stdout, a timeout, bounded errors, and atomic
  ignored report writes.
- Renderer failures do not echo raw DOT content, captured traffic, or secrets.
- CLI output prints only the generated artifact path.

## Completed Slice: Issue #58 License And Package Metadata

Outcome: make the public alpha legally explicit and package-index friendly.

Implemented boundaries:

- `LICENSE` contains the Apache License 2.0 text.
- `pyproject.toml` declares the SPDX license expression `Apache-2.0`, ships the root license file, and uses alpha-level classifiers without overclaiming maturity.
- `README.md` states the open-core boundary: Entroping Core is Apache-2.0, while future hosted, model, enterprise, policy-pack, and support offerings may use separate commercial terms.
- `docs/meta/PROJECT_PROGRESS.md` no longer treats license/package metadata as the remaining alpha blocker.

## Completed Slice: Issue #3 Gate Matching And Injection

Outcome: QAnstitution gates match discovered Hurl test metadata and compile into Hurl assertions in temporary execution copies without mutating source `.hurl` files.

Source-of-truth files:

- GitHub issue #3, `Phase 2B: QAnstitution gate matching and temporary Hurl injection`.
- `docs/product/MVP_PLAN.md`, Phase 2 Hurl Runner and Gate Injection.
- `docs/technical/TDS.md`, gate injection and Hurl execution design.
- `docs/technical/QANSTITUTION_REFERENCE.md`, gate syntax and metadata examples.
- `docs/meta/TEST_STRATEGY.md`, regression and security expectations.

Planned boundaries:

- Gate matching should operate on typed QAnstitution conditions and discovered Hurl metadata.
- Gate-to-Hurl compilation should live behind a policy compiler boundary and be tested with fixtures.
- Injection must write temporary execution copies and prove source `.hurl` fixtures are unchanged.

Implemented boundaries:

- `models.hurl` parses shallow request method, URL, and path metadata without executing requests.
- `bridge.policy_to_hurl` matches typed QAnstitution conditions and compiles rule ID, assertion, and enforcement metadata.
- `core.gate_injector` writes deterministic temporary execution copies with `# entroping-gate:` annotations while leaving source `.hurl` files unchanged.

## Completed Slice: Issue #4 Hurl Subprocess Runner

Outcome: execute injected Hurl copies through the external Hurl binary with timeouts, bounded output, cleanup, redaction, and deterministic non-zero failure handling.

Implemented boundaries:

- `core.hurl_runner` invokes Hurl through subprocess argument arrays with `shell=False`.
- Runner results are typed, timeout-aware, redacted, and bounded before printing.
- `entroping run` loads QAnstitution, discovers Hurl files, creates temporary injected execution copies, runs Hurl, cleans run state, and exits deterministically.

## Completed Slice: Issue #5 JSON And JUnit Reports

Outcome: emit machine-consumable JSON and JUnit summaries from deterministic run results so CI and humans can inspect failures without rerunning Hurl.

Implemented boundaries:

- `core.report_writer` writes redacted JSON and JUnit XML from typed run results.
- `entroping run --report json --report junit` writes artifacts under `reports/` and always writes `.entroping/latest-run.json`.
- `entroping report bug` writes a Markdown handoff from the latest failing run or returns an actionable no-run/no-failure message.

## Completed Slice: Issue #6 Alpha Demo Quickstart

Outcome: make the checkout demo and README quickstart prove the deterministic alpha loop for a first-time user.

Implemented boundaries:

- `examples/checkout-api/demo_server.py` provides a tiny local API for the smoke Hurl file.
- The fixture Hurl file uses a literal localhost URL so the alpha quickstart does not depend on env-file loading.
- README and fixture docs show the deterministic run plus JSON/JUnit reports.

## Completed Slice: Issue #11 OpenAPI Architect Build

Outcome: make `entroping architect build --new` compile a local OpenAPI source configured at `sources.spec` into deterministic reviewable Hurl files under `tests/generated/`, without calling an LLM or collapsing bridge/compiler boundaries.

Implemented boundaries:

- `bridge.openapi_to_hurl` compiles supported OpenAPI operations into Hurl content without filesystem writes, Hurl execution, or adapter imports.
- `core.openapi_loader` loads local YAML/JSON OpenAPI documents and rejects remote URLs, unsupported schemes, symlinks, non-files, and non-mapping documents.
- `cli.architect build --new` loads QAnstitution, resolves `sources.spec`, writes generated files under `tests/generated/`, and refuses unsupported prompt/merge paths clearly.

## Completed Slice: Issue #13 Environment File Loading

Outcome: make `entroping run --env <name>` load gitignored `envs/<name>.env` files and pass variables to Hurl through subprocess argument arrays so generated OpenAPI tests using `{{base_url}}` are runnable.

Implemented boundaries:

- `core.env_loader` parses simple local dotenv files, rejects path traversal, symlinks, invalid lines, duplicate keys, and invalid variable names.
- Process environment overrides only matching file keys; unrelated process variables are not imported.
- `core.hurl_runner` passes variables to Hurl and redacts variable values from captured output; issue #15 hardens the transport away from secret-bearing argv.
- `cli.run` loads env variables only when `--env` is supplied and keeps missing env files actionable.

## Completed Slice: Issue #15 Hurl Variable Argv Hardening

Outcome: keep environment values out of Hurl process arguments by writing merged variables to a short-lived Hurl variables file and invoking Hurl with `--variables-file <path>`.

Implemented boundaries:

- `core.hurl_runner` writes sorted `KEY=value` lines to a temporary variables file only when variables are present.
- Hurl subprocess command arrays contain the variables-file path, not loaded variable values.
- The temporary variables file is removed after normal, failing, and timeout runs.
- Redaction still includes loaded variable values before outputs reach reports.

## Completed Slice: Issue #17 HTML Run Reports

Outcome: make `entroping run --report html` write a dependency-free human-readable report under `reports/run-latest.html` while preserving existing JSON and JUnit report behavior.

Implemented boundaries:

- `core.report_writer` renders escaped HTML from the existing typed `RunReport` model.
- `cli.run` accepts repeatable `--report html` alongside `json` and `junit`.
- HTML reports include project, environment, summary counts, test status, duration, rule IDs, and escaped Hurl output.

## Completed Slice: Issue #19 Live Hurl Demo Smoke In CI

Outcome: prove the user-facing demo path in GitHub Actions with the real Hurl binary:
start the checkout demo server, generate Hurl tests from OpenAPI, load `--env local`,
run smoke tests, and emit HTML/JSON/JUnit artifacts.

Planned boundaries:

- Keep live Hurl smoke separate from fast unit/regression checks.
- Do not commit generated Hurl tests, env files, reports, or runtime state.
- Keep logs actionable while preserving env-value redaction.

Implemented boundaries:

- `scripts/live_demo_smoke.sh` copies the checkout fixture into a temporary workspace,
  starts the demo server, generates OpenAPI Hurl tests, writes a local env file, runs
  smoke tests with HTML/JSON/JUnit reports, and optionally copies report artifacts.
- CI pins Hurl `8.0.1`, verifies the upstream release checksum, runs the live smoke
  after the fast regression job, and uploads generated reports as workflow artifacts.
- Local tests exercise the smoke script with a fake Hurl binary so contributors do not
  need Hurl installed for the normal regression suite.

## Completed Slice: Issue #23 OpenAPI Parameters And Schema Examples

Outcome: make `architect build --new` generate useful Hurl for common OpenAPI
operations with path, query, header, and cookie parameters plus source-grounded
request examples/defaults.

Planned boundaries:

- Keep the OpenAPI compiler pure: no filesystem writes, Hurl execution, adapter imports,
  or LLM calls.
- Use safe Hurl variables for parameter fallbacks and literal values only when OpenAPI
  provides examples, defaults, constants, or enums.
- Reject unsafe parameter names, locations, control characters, and unsupported
  parameter value shapes before emitting Hurl.
- Exercise the behavior through unit tests, CLI adapter tests, and the checkout demo
  fixture used by the live CI smoke.

Implemented boundaries:

- `bridge.openapi_to_hurl` supports common path/query/header/cookie parameter rendering
  and schema example/default/const/enum request bodies.
- OpenAPI literal rendering rejects Hurl template delimiters, non-finite numbers, unsafe
  parameter names, and fallback variable collisions before emitting `.hurl`.
- The checkout demo now includes a parameterized lookup endpoint covered by the live CI
  Hurl smoke.

## Completed Slice: Issue #25 Deterministic Architect Audit Coverage

Outcome: make `architect audit` report OpenAPI operations that do not have committed
Hurl coverage, without calling an LLM or executing Hurl.

Implemented boundaries:

- Keep audit comparison in a pure bridge module.
- Use discovered executable Hurl tests with metadata comments, especially `source=openapi`
  and `operation_id`, as the coverage signal.
- Support Markdown and raw JSON output while preserving machine-readable JSON.
- Exit successfully when all operations are covered and non-zero when gaps are found.

## Completed Slice: Issue #29 Non-Secret Agent Config Commands

Outcome: make `config list` and `config set` real deterministic commands for
Builder/Auditor/Breaker model routing, without storing credentials or calling model
providers.

Implemented boundaries:

- Keep updates in a core filesystem adapter that validates the effective QAnstitution
  before mutation and validates the updated temp file before replacing the original.
- Reject empty, control-character, and secret-looking model identifiers through the
  domain schema.
- Preserve existing agent persona source, temperature, and max token settings when only
  changing the model.
- Create missing roles with `agents/<role>.md`, `temperature: 0.0`, and the requested
  model.
- Use exclusive random same-directory temporary files so predictable symlink paths
  cannot receive config content.
- Keep CLI output human-readable and non-secret.

## Completed Slice: Issue #31 Architect Brain Foundation

Outcome: add deterministic Brain foundations for future LLM-backed Architect commands
without calling providers from `entroping run` or tests.

- Added a lazy LiteLLM boundary without wiring it into `entroping run`.
- Loaded Builder/Auditor/Breaker persona files through validated non-secret config.
- Defined structured output models for generated Hurl edits before making provider calls.
- Added prompt package assembly that rejects secret-shaped content and unsafe context paths.
- Keep all model invocation outside deterministic CI/run paths.

## Completed Slice: Issue #35 Architect Prompt Build

Outcome: wire `architect build --prompt` to the Brain foundation while keeping
`entroping run` deterministic and LLM-free.

- Loaded the configured Builder persona and model routing from the effective
  QAnstitution.
- Built a redaction-checked prompt package with scoped intent and requested tags.
- Invoked LiteLLM only through the Brain adapter boundary.
- Parsed raw provider JSON into `ArchitectEditSet` before filesystem writes.
- Reused the staged Architect writer so generated Hurl files are marked
  `# entroping: source=architect` and non-Architect files are not overwritten.
- Redacted untrusted provider summaries, warnings, and errors before CLI output.

## Completed Slice: Issue #37 Prompt Hurl Validation

Outcome: validate prompt-generated Hurl through `hurlfmt --out json` before
Architect writes generated files.

- Added a `core.hurl_validator` subprocess adapter with argument arrays,
  timeouts, temporary file cleanup, and no raw provider-content echo on failure.
- Validated every prompt-generated edit after structured parsing and tag injection
  but before staged filesystem writes.
- Kept validation all-or-nothing: one invalid edit prevents every generated file
  from being written.
- Hardened Architect edit paths against control characters.

## Current Validation Queue

Use these issues as the next marathon targets. Keep each one narrow, tested, and
merged through GitHub before starting the next branch:

- Issue #183: evaluate Homebrew tap or standalone binary distribution.
- After those adoption slices land, move to v0.3 product-depth issues such as
  Studio drilldowns, reviewed baseline workflows, redaction review UX, and
  stronger Architect remediation guidance.

## Explicitly Deferred

- Complete non-prompt `architect build --strategy merge` if product demand justifies it.
- Full interactive Studio TUI beyond the read-only status shell.
- Nuitka packaging.
- Hosted/cloud features.
- Graphify-generated artifacts in Git.

## Working Context Loop

At the start of a new Codex thread, read:

1. `AGENTS.md`
2. `README.md`
3. `00_INDEX.md`
4. `.context/plan.md`
5. `docs/product/MVP_PLAN.md`
6. `docs/technical/TDS.md`
7. `docs/meta/AUTONOMOUS_DEVELOPMENT.md`
8. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`
9. `docs/meta/PROJECT_PROGRESS.md`
10. `docs/meta/ISSUE_TRACKING.md`
11. `docs/meta/TEST_STRATEGY.md`

For product history, open Obsidian and start with `00_INDEX.md`.

To start an implementation or review session from an issue, dry-run the launcher first:

```bash
scripts/start_issue.sh <issue-number> <type>/<short-kebab-description> --dry-run
```

## Constraints

- Preserve the locked command namespace.
- Keep `entroping run` deterministic and LLM-free.
- Keep Hurl as the only API execution engine.
- Do not send secrets or raw traffic to LLM providers.
- Keep generated state, reports, local env files, and Graphify output out of Git.
- Treat security and quality checks as release gates.
- Use the feature delivery checklist for TDD, regression, architecture, security, multi-agent, documentation, and commit-readiness gates.
- Use GitHub Issues for individual work items and `docs/meta/PROJECT_PROGRESS.md` for simple Obsidian progress tracking.
