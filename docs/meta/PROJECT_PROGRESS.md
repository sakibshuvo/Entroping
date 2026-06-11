---
title: Project Progress
type: dashboard
status: active
tags:
  - progress
  - roadmap
  - obsidian
  - alpha
---

# Project Progress

This is the daily dashboard. GitHub Issues track individual tasks; this note
keeps the current direction, next queue, and release evidence easy to scan.

## Daily Dashboard

1. Open this note first in Obsidian or GitHub.
2. Use the GitHub Project board for issue status.
3. Use [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]] for each implementation slice.
4. Use [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] before changing roadmap,
   progress, public docs, specs, ADRs, or context files.
5. Keep this note short. Completed issue history belongs in GitHub, release
   evidence, and `.context/changelog.md`.

## Current Target

**Goal:** finish the v0.4 integration path without reopening completed onboarding/product-depth work; stable-core readiness stays tied to external evidence.

Current local queue: only review-proven local gaps should be worked; no ready local cleanup queue remains.

Current public board: [Entroping Public Roadmap](https://github.com/users/sakibshuvo/projects/1)
Current deterministic loop:

```text
init -> doctor -> load QAnstitution -> discover Hurl tests -> inject gates -> run Hurl -> JSON/JUnit/HTML/review evidence
```

## Next Three Issues

With #517-#523 and #548 closed, keep local work limited to review-proven defects or product gaps; do not create filler work.

| Order | Issue | Why next |
| --- | --- | --- |
| 1 | #303-#306 | Package-index proof and real downstream feedback after TestPyPI/PyPI credentials and protection are ready. |
| 2 | #308-#310 | Stable-core compatibility decision and non-GitHub CI proof after repeated release/package evidence and runner access. |
| 3 | New local issue only if discovered | Real defect/regression or ready product gap; no filler cleanup queue. |

Promote a new local issue here only when a real defect/regression or ready product gap is discovered.

## External Stable-Core Blockers

Stable-core readiness remains blocked by evidence that cannot be manufactured entirely inside this repo.

| Blocker | Tracking | Needed proof |
| --- | --- | --- |
| Package-index proof | #303, #304, #305 | TestPyPI/PyPI publish, install, and smoke evidence from the package index. |
| Real downstream feedback | #306 | At least one sanitized external project feedback artifact. |
| stable-core compatibility decision | #308 | Explicit compatibility policy and repeated evidence across supported versions. |
| Non-GitHub CI proof | #309, #310 | Real GitLab/Buildkite/CircleCI runner proof before provider-native templates. |

## Latest Evidence
| Evidence | Status | Anchor |
| --- | --- | --- |
| [Test evidence taxonomy](https://github.com/sakibshuvo/Entroping/issues/590) | Done | `scripts/test_taxonomy.py --strict` now writes schema-versioned `reports/test-taxonomy.json` with behavior, docs-compliance, script-integrity, integration, smoke, regression, and security categories; `scripts/audit_quality.sh` includes the artifact before coverage/Radon/Vulture gates so 100 percent coverage remains auditable by evidence type. |
| [Spec contract versus package release versioning](https://github.com/sakibshuvo/Entroping/issues/592) | Done | README, Product Spec, TDS, and Roadmap now state that v4.1 is the product/spec/CLI contract generation, not the Python package release version; package releases remain alpha Git tags and PEP 440 package metadata tracked from `pyproject.toml`. |
| [Real-Hurl CLI E2E proof](https://github.com/sakibshuvo/Entroping/issues/593) | Done | A pytest integration now skips cleanly when Hurl is unavailable; when present, it starts a localhost API, drives `entroping init` plus `entroping run --ci --report json --report junit` through the installed console script, validates JSON/JUnit reports and injected QAnstitution rule IDs, and proves the source `.hurl` file is unchanged. |
| [GitHub Actions bootstrap install strategy](https://github.com/sakibshuvo/Entroping/issues/570) | Done | Generated starters now install through `ENTROPING_INSTALL_SPEC`, defaulting to the latest GitHub source branch while preserving explicit tag pinning through one workflow env value and documented migration guidance for older pinned starters. |
| [Hurl binary discovery trust policy](https://github.com/sakibshuvo/Entroping/issues/611) | Done | Bare binary names intentionally trust parent `PATH`, explicit absolute Hurl paths are normalized so pinned CI/high-assurance callers can bypass hostile earlier `PATH` entries, relative binary paths fail closed, missing Hurl does not claim version-check evidence, and child subprocess `PATH` minimization remains tested. |
| [AI worker queue safety](https://github.com/sakibshuvo/Entroping/issues/609) | Done | `scripts/ai_jobs.py run-next` now atomically claims queued jobs, quarantines corrupt queued artifacts, fails stale `running/` jobs after their timeout grace window, and preserves proposal-only worker artifacts for Codex validation. |
| [Hurl runner chaos regression matrix](https://github.com/sakibshuvo/Entroping/issues/610) | Done | `tests/test_hurl_runner.py` now covers empty output, signal-like exit codes, binary/non-UTF-8 stream decoding, truncation boundaries, redaction plus truncation, partial stdout/stderr on subprocess errors, variable-file cleanup after `OSError`, and unstable retry evidence without changing runtime behavior. |
| [Direct DeepSeek worker engine](https://github.com/sakibshuvo/Entroping/issues/581) | Done | `scripts/ai_jobs.py submit --engine deepseek-api` can route queued review or patch-proposal jobs through `scripts/deepseek_worker.py`, using `DEEPSEEK_API_KEY` only from the environment and writing ignored local artifacts for Codex validation without applying patches or touching product runtime paths. |
| [Run CLI validation extraction](https://github.com/sakibshuvo/Entroping/issues/561) | Done | Run option conflicts and report-format normalization now live in direct-tested core validation helpers while the Typer adapter preserves user-facing errors. |
| [Policy-diff CI failure mode](https://github.com/sakibshuvo/Entroping/issues/565) | Done | `entroping report policy-diff --fail-on-change` keeps the default review report successful for valid changed diffs while giving CI an explicit nonzero gate for effective-policy drift. |
| [traffic approval manifest redaction confidence](https://github.com/sakibshuvo/Entroping/issues/499) | Done | `reports/approvals/*.json` records `low_confidence_records`, the published approval schema requires it, and strict-doc plus Hurl formatter CI checks were repaired. |
| [Redaction-confidence artifact gate](https://github.com/sakibshuvo/Entroping/issues/495) | Done | Traffic redaction now marks low/high confidence at body and exchange level, redaction reviews expose low-confidence counts without raw values, and `freeze`, `freeze --mock`, and `map --export png` fail closed before writing artifacts from low-confidence records. |
| [Known-failure CI validation](https://github.com/sakibshuvo/Entroping/issues/491) | Done | `ignore_failures[].expires` now fails policy loading when malformed, `doctor --ci` fails expired known-failure exceptions before readiness passes, and runtime/report gate-injection paths share the same expiry validator. |
| [Read-only dependency traffic-state access](https://github.com/sakibshuvo/Entroping/issues/489) | Done | `entroping map` and run dependency-drift observations read existing redacted traffic state through the read-only SQLite path, preserve missing/empty-state behavior, and prove evidence review does not open the write-capable traffic store. |
| [Run dry-run execution plan](https://github.com/sakibshuvo/Entroping/issues/417) | Done | `entroping run --dry-run` now resolves selected Hurl tests, tag or changed-file filters, effective and injected gates, env name, missing variable names, worker settings, and requested report paths without invoking Hurl, writing latest-run state, writing execution events, writing executed-result reports, or mutating source `.hurl`; `--report json` writes only `reports/run-plan.json` with schema `entroping.run-plan.v1`. |
| [Hurl version compatibility in doctor](https://github.com/sakibshuvo/Entroping/issues/418) | Done | `entroping doctor` now runs `hurl --version` through the bounded local subprocess boundary, reports compatible, missing, unsupported, and unparsable Hurl version states in human and JSON output, keeps normal warning exit compatibility, and makes `doctor --ci` fail when Hurl compatibility cannot be proven. |
| [Multi-agent review bundle](https://github.com/sakibshuvo/Entroping/issues/467) | Done | `entroping report agent-bundle --output md|json` summarizes sanitized `.entroping/agent-runs/*.json` evidence for configured Builder, Breaker, and Auditor roles, supports role and scope filters, writes schema-versioned `reports/agent-bundle.*` artifacts, reports missing config/evidence, invalid provider-output validation, missing generated-Hurl validation, unsafe manifests, and multi-role output-path conflicts without calling providers, Hurl, or `run`. |
| [Architect refactor preview](https://github.com/sakibshuvo/Entroping/issues/419) | Done | `entroping architect refactor --preview` validates provider edits through the same managed-block merge and Hurl parser path as write mode, prints a redacted unified diff, writes only the value-free agent run manifest, and leaves target Hurl files unchanged. |
| [Latest failure reruns](https://github.com/sakibshuvo/Entroping/issues/420) | Done | `entroping run --rerun-failures` selects failed source `.hurl` files from `reports/run-latest.json` or `.entroping/latest-run.json`, reuses the report environment unless `--env` overrides it, runs through the normal deterministic workflow, and remains feedback acceleration rather than release proof. |
| [Policy gate coverage matrix](https://github.com/sakibshuvo/Entroping/issues/421) | Done | `entroping report gate-coverage --output md|json` maps each effective QAnstitution gate to committed Hurl test files, tags, operation IDs, request methods, and redacted request paths, lists unmatched gates, and does not execute Hurl, inject assertions, call providers, or print full URLs, query strings, headers, bodies, variables, or captured traffic values. |
| [Gate-injection explanation report](https://github.com/sakibshuvo/Entroping/issues/428) | Done | `entroping report gate-injection --target <path> --output md|json` explains effective QAnstitution gates that would be injected into selected local Hurl files, including source policy path, condition, enforcement, final/group provenance, and known-failure skips without running Hurl or mutating source files. |
| [Fail-fast execution mode](https://github.com/sakibshuvo/Entroping/issues/429) | Done | `entroping run --fail-fast` stops scheduling after the first failing Hurl result, keeps source `.hurl` files immutable, and records selected, executed, not-scheduled, and fail-fast summary evidence in latest-run state and reports. |
| [Sanitized run event log](https://github.com/sakibshuvo/Entroping/issues/430) | Done | `entroping run` now writes `.entroping/latest-run-events.jsonl` with schema `entroping.run-events.v1`, covering run start, selected tests, redacted results, artifact writes, no-match/error events, and completion status without variables or raw passing stdout/stderr. |
| [Freeze dry-run preview](https://github.com/sakibshuvo/Entroping/issues/432) | Done | `entroping freeze --dry-run` now previews selected redacted records, proposed Hurl or WireMock output paths, golden status, and counts-only redaction categories without writing generated tests, mocks, approval manifests, or source artifacts. |
| [Explicit watch capture scope allowlists](https://github.com/sakibshuvo/Entroping/issues/433) | Done | `entroping watch` now requires an explicit capture scope through `--target`, `--scope-host`, or `--scope-url-prefix`; out-of-scope and malformed flow URLs are ignored before persistence, and count-only summaries report ignored traffic without rendering sensitive URLs. |
| [Lossless decision registry](https://github.com/sakibshuvo/Entroping/issues/468) | Done | `docs/meta/DECISION_REGISTRY.yaml` now indexes durable decisions with source pointers, `scripts/source_preservation_check.py` validates local source-history anchors and registry links, and `scripts/context_pack.sh` surfaces the registry for agent handoff without replacing raw history. |
| [Story traceability gap summary](https://github.com/sakibshuvo/Entroping/issues/434) | Done | `entroping report traceability --output md|json` now links Hurl `story_id` metadata to local `docs/stories/*.md` story documents and reports missing local stories, Markdown stories without tests, duplicate story IDs, malformed story metadata, and unsafe story paths without business-system API calls. |
| [OpenAPI operation run selection](https://github.com/sakibshuvo/Entroping/issues/435) | Done | `entroping run --operation-id <id>` now selects existing Hurl tests by exact committed `operation_id` metadata, rejects selector conflicts before execution, and records operation ID evidence in JSON/JUnit/HTML reports. |
| [Runtime known-failure guardrails](https://github.com/sakibshuvo/Entroping/issues/436) | Done | Selected-test `ignore_failures` entries now fail before Hurl execution when their rule ID does not match an injected QAnstitution gate; filtered-out test exceptions remain outside the current subset. |
| [OpenAPI breaking-change diff audit](https://github.com/sakibshuvo/Entroping/issues/437) | Done | `architect audit --focus logic --changed-from <ref>` now attaches `entroping.openapi-breaking-diff.v1` findings for deterministic OpenAPI evolution review without generating or deleting tests. |
| [Captured-artifact approval manifests](https://github.com/sakibshuvo/Entroping/issues/449) | Done | `freeze`, `freeze --mock`, and `map --export png` now write value-free approval manifests under `reports/approvals/` with generated paths, checksums, deterministic source fingerprints, and counts-only redaction summaries without raw traffic values. |
| [Provider budget evidence](https://github.com/sakibshuvo/Entroping/issues/448) | Done | Prompt-backed Architect build, refactor, and Auditor review paths expose provider, latency, token counts when available, and configured cost estimates in CLI/review output and value-free agent run manifests without prompts, secrets, or raw provider responses. |
| [Reusable QAnstitution gate groups](https://github.com/sakibshuvo/Entroping/issues/447) | Done | `gate_groups` expands local reusable gates into ordinary runtime rules, rejects missing references and cycles before execution, preserves import/final semantics, and shows source group provenance in effective-policy reports. |
| [CI-readiness doctor mode](https://github.com/sakibshuvo/Entroping/issues/446) | Done | `entroping doctor --ci` validates Hurl availability, safe `.entroping/` and `reports/` paths, suite manifests, required Hurl variables, and provider-free `run --ci` expectations without CI provider APIs, workflow mutation, or env-value disclosure. |
| [Coverage badges from local reports](https://github.com/sakibshuvo/Entroping/issues/445) | Done | `entroping report badges` writes local Shields endpoint JSON for policy-gate, OpenAPI operation, and story-traceability coverage from existing JSON reports; `report traceability --output json` provides the badge source without hosted services or network calls. |
| [Run-to-run regression delta](https://github.com/sakibshuvo/Entroping/issues/444) | Done | `entroping report delta --base <path> --current <path> --output md|json` compares two local JSON run reports, emits schema-versioned added/resolved/changed/unchanged failure, latency, and policy-gate deltas, exits nonzero for added or changed failures, and never renders raw stdout/stderr. |
| [Traffic-vs-OpenAPI route audit](https://github.com/sakibshuvo/Entroping/issues/443) | Done | `architect audit --focus logic` now opportunistically reads redacted Eye traffic state, compares captured route summaries to OpenAPI templates, flags undocumented observed routes, and reports documented/spec-only route evidence without raw query strings, headers, cookies, bodies, host userinfo, or captured values. |
| [Local policy-pack self-test](https://github.com/sakibshuvo/Entroping/issues/431) | Done | `config test-policy-pack --pack <path> [--output text|json]` validates local packs before vendoring or publishing without copying files, editing `qanstitution.yaml`, network access, provider keys, registry claims, or premium catalog behavior. |
| [OpenAPI security-scheme coverage generation](https://github.com/sakibshuvo/Entroping/issues/442) | Done | `architect build --new` now emits deterministic missing/invalid auth tests under `tests/generated/security/` for OpenAPI operations with supported HTTP bearer/basic or API-key header/query/cookie schemes and explicit `401`/`403` responses; unsupported schemes are warning findings, not guessed tests. |
| [Timeout evidence per test](https://github.com/sakibshuvo/Entroping/issues/441) | Done | JSON/JUnit/HTML/review-summary artifacts now include effective per-test `timeout_ms`; Hurl subprocess timeouts use status `timeout`, exit code `124`, timeout-specific JUnit failure typing, and timeout findings distinct from assertion failures. |
| [Tag-expression run selection](https://github.com/sakibshuvo/Entroping/issues/440) | Done | `entroping run --tag-expression "smoke and not slow"` now uses a deterministic `and`/`or`/`not` parser over Hurl metadata tags, reports selected/skipped counts, rejects invalid expressions before Hurl execution, and preserves repeatable `--tag` OR semantics. |
| [Sanitized agent run manifests](https://github.com/sakibshuvo/Entroping/issues/427) | Done | Prompt-backed Architect build, Breaker build, merge-build, refactor, and Auditor review paths now write `.entroping/agent-runs/*.json` with value-free role/model/persona/prompt-hash/output/validation/usage evidence. |
| [Changed OpenAPI operation generation](https://github.com/sakibshuvo/Entroping/issues/404) | Done | `architect build --new --changed-from <ref>` compares the configured local OpenAPI spec with the same file at a Git base ref, regenerates only current added/modified/renamed operations, and reports removed operations for manual review. |
| [Named suite manifests](https://github.com/sakibshuvo/Entroping/issues/402) | Done | `run --suite <name>` loads committed `suites/<name>.yaml` manifests, validates `entroping.suite.v1`, resolves root-bounded Hurl path globs, and applies suite-defined env, tags, reports, parallel, and drift settings. |
| [Local policy-pack vendoring](https://github.com/sakibshuvo/Entroping/issues/401) | Done | `config vendor-policy-pack` copies reviewed local packs under `policy-packs/`, validates manifest/entrypoint evidence, preserves final-gate behavior, and appends a local import without remote registry coupling. |
| [Open-source license and package metadata](https://github.com/sakibshuvo/Entroping/issues/58) | Done | Apache-2.0 public core and package metadata are explicit. |
| [Public clean-checkout onboarding smoke](https://github.com/sakibshuvo/Entroping/issues/185) | Done | `scripts/release_check.sh --require-live-demo` passed from a fresh public clone. |
| Public docs site decision | Done | MkDocs Material publishes existing canonical docs without duplicating the tree. |
| PyPI/TestPyPI trusted publishing workflow | Done | Manual protected workflow exists; package-index proof is still separate. |
| Homebrew tap prototype | Done | Prototype stays blocked until PyPI alpha proof exists. |
| Distribution path recommendation | Done | `uv tool install` first, PyPI next, Homebrew after PyPI, standalone later. |
| Standalone binary distribution decision | Deferred | Nuitka/PyInstaller automation waits for demand and signing runbooks. |
| Non-GitHub CI provider recipes | Done | Provider docs exist; native templates wait for real runner evidence. |
| Organization QAnstitution import controls | Done | ADR-0011 defines local-first import provenance and final-gate behavior. |
| [Brand terminology and QAnstitution naming decision](https://github.com/sakibshuvo/Entroping/issues/349) | Done | ADR-0012 keeps `qanstitution.yaml` canonical, preserves the core philosophy, and rejects unplanned aliases or autonomous-swarm positioning. |
| [Practical watch TLS and proxy limits](https://github.com/sakibshuvo/Entroping/issues/350) | Done | User docs now set expectations for mitmproxy CA setup, corporate VPN/proxy conflicts, certificate pinning, proxy bypass, session headers, and capture authorization. |
| [OWASP API Top 10 starter policy pack](https://github.com/sakibshuvo/Entroping/issues/351) | Done | A local OWASP API Security Top 10-inspired starter pack now proves the policy-pack path without claiming endorsement, certification, or complete compliance. |
| [Shared symlink component path-safety helper](https://github.com/sakibshuvo/Entroping/issues/344) | Done | Common symlink component traversal is centralized while config imports now reject symlinked local imports and adapters keep domain-specific errors. |
| [Traffic-store retention SQL pruning](https://github.com/sakibshuvo/Entroping/issues/345) | Done | Local Eye state now deletes stale traffic rows with a SQL-level delete while keeping newest-event retention and insertion-order reads. |
| [No-Hurl CLI smoke script](https://github.com/sakibshuvo/Entroping/issues/346) | Done | `scripts/cli_smoke.sh` proves CLI boot, version, minimal init, and doctor behavior without requiring Hurl runtime execution. |
| [Read-only Studio applied-gate drilldowns](https://github.com/sakibshuvo/Entroping/issues/192) | Done | Studio links latest-run report rule IDs to QAnstitution gate definitions. |
| [Hardened XML report parsing](https://github.com/sakibshuvo/Entroping/issues/364) | Done | JUnit XML read paths for GitHub annotations and review summaries use `defusedxml` and reject DTD/entity constructs before rendering findings. |
| [Captured-traffic redaction hardening](https://github.com/sakibshuvo/Entroping/issues/365) | Done | Multipart request and response bodies are persisted only as redacted media-type summaries, and broad token patterns avoid short documentation placeholders. |
| [Breaker-backed prompt generation](https://github.com/sakibshuvo/Entroping/issues/392) | Done | `architect build --agent breaker --prompt ...` loads the configured Breaker persona/model and tags generated Hurl with `breaker`. |
| [Auditor-backed Architect review](https://github.com/sakibshuvo/Entroping/issues/393) | Done | `architect audit --focus auditor` loads the configured Auditor persona/model, validates review JSON, and writes no files. |
| [Hurl variable preflight](https://github.com/sakibshuvo/Entroping/issues/396) | Done | `entroping run` fails before Hurl execution when selected tests reference unresolved variables, while reporting only missing names. |
| [Changed Hurl test runs](https://github.com/sakibshuvo/Entroping/issues/397) | Done | `entroping run --changed-from <ref>` selects existing changed `.hurl` files from Git diff for fast local or agent feedback. |
| [SARIF report output](https://github.com/sakibshuvo/Entroping/issues/398) | Done | `entroping report sarif` writes SARIF 2.1.0 from local JUnit, drift, and optional traceability findings for code-scanning import. |
## Source Of Truth

| Question | Source |
| --- | --- |
| What work is next? | GitHub Issues, milestones, and Project board. |
| What is public direction? | `ROADMAP.md`. |
| What shipped and why? | `.context/changelog.md`, release evidence, PRs, and ADRs. |
| What is product history? | `docs/meta/VAULT_INDEX.md`, `docs/evolution/`, and curated source exports. |
| What should agents read first? | `AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, and `scripts/context_pack.sh`. |

## Update Rules

- Update this file only for current target, next queue, stable-core blockers, or durable evidence anchors.
- Do not duplicate the completed issue table here.
- Do not use this file as the backlog; GitHub Issues remain the backlog.
- Keep roadmap edits behind the roadmap change gate in [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]].
- Keep historical context in the vault and `.context/changelog.md`, not here.
