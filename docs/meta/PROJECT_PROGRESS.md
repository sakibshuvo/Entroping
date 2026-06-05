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
3. Use [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]] for
   each implementation slice.
4. Use [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] before changing roadmap,
   progress, public docs, specs, ADRs, or context files.
5. Keep this note short. Completed issue history belongs in GitHub, release
   evidence, and `.context/changelog.md`.

## Current Target

**Goal:** finish the v0.4 integration path without reopening completed
onboarding/product-depth work, while keeping stable-core readiness tied to
external evidence instead of green local tests alone.

Current issue: [#421](https://github.com/sakibshuvo/Entroping/issues/421) adds a policy gate coverage matrix.

Current public board: [Entroping Public Roadmap](https://github.com/users/sakibshuvo/projects/1)

Current deterministic loop:

```text
init -> doctor -> load QAnstitution -> discover Hurl tests -> inject gates -> run Hurl -> JSON/JUnit/HTML/review evidence
```

## Next Three Issues

These are autonomous local marathon targets. Blocked external evidence issues
remain below.

| Order | Issue | Why next |
| --- | --- | --- |
| 1 | [#421](https://github.com/sakibshuvo/Entroping/issues/421) | Add policy gate coverage matrix. |
| 2 | [#420](https://github.com/sakibshuvo/Entroping/issues/420) | Rerun failures from the latest local report. |
| 3 | [#419](https://github.com/sakibshuvo/Entroping/issues/419) | Preview Architect refactor patches without writing files. |

If one of these closes, promote the next highest-value ready issue from GitHub.
Do not expand this table beyond three rows.

## External Stable-Core Blockers

Stable-core readiness remains blocked by evidence that cannot be manufactured
entirely inside this repo.

| Blocker | Tracking | Needed proof |
| --- | --- | --- |
| Package-index proof | #303, #304, #305 | TestPyPI/PyPI publish, install, and smoke evidence from the package index. |
| Real downstream feedback | #306 | At least one sanitized external project feedback artifact. |
| Compatibility discipline | #308 | Explicit compatibility policy and repeated evidence across supported versions. |
| Non-GitHub CI proof | #309, #310 | Real GitLab/Buildkite/CircleCI runner proof before provider-native templates. |

## Latest Evidence

| Evidence | Status | Anchor |
| --- | --- | --- |
| [GitHub Actions starter install](https://github.com/sakibshuvo/Entroping/issues/422) | Done | `entroping init --github-actions` installs the reviewed starter workflow at `.github/workflows/entroping.yml`, refuses existing workflows, keeps the packaged template aligned with `examples/github-actions/entroping-ci.yml`, and adds no secrets, provider credentials, hosted-service coupling, or package-index readiness claims. |
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
| [Slim public launch docs path](https://github.com/sakibshuvo/Entroping/issues/348) | Done | README and MkDocs lead with demo/user/policy/CI paths while vault/internal memory stays preserved behind project context. |
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
| [Doctor agent readiness](https://github.com/sakibshuvo/Entroping/issues/394) | Done | `entroping doctor` validates configured agent persona files and reports configured `api_key_env` readiness without printing values or calling providers. |
| [Doctor JSON health output](https://github.com/sakibshuvo/Entroping/issues/395) | Done | `entroping doctor --output json` emits schema version `entroping.doctor.v1` for CI and agent setup health without provider calls. |
| [Hurl variable preflight](https://github.com/sakibshuvo/Entroping/issues/396) | Done | `entroping run` fails before Hurl execution when selected tests reference unresolved variables, while reporting only missing names. |
| [Changed Hurl test runs](https://github.com/sakibshuvo/Entroping/issues/397) | Done | `entroping run --changed-from <ref>` selects existing changed `.hurl` files from Git diff for fast local or agent feedback. |
| [SARIF report output](https://github.com/sakibshuvo/Entroping/issues/398) | Done | `entroping report sarif` writes SARIF 2.1.0 from local JUnit, drift, and optional traceability findings for code-scanning import. |
| [Reviewed drift baseline promotion](https://github.com/sakibshuvo/Entroping/issues/399) | Done | `entroping report promote-drift-baseline` validates a reviewed candidate before atomically writing `.entroping/drift-baseline.json`. |
| [OpenAPI operation-to-Hurl coverage matrix](https://github.com/sakibshuvo/Entroping/issues/400) | Done | `architect audit --focus logic --output md|json` now shows covered, uncovered, ambiguous, and stale OpenAPI operation mappings. |
| [`py.typed` package marker](https://github.com/sakibshuvo/Entroping/issues/366) | Done | Built wheel and sdist artifacts now include `entroping/py.typed`, and `scripts/package_check.sh` fails if either artifact omits it. |
| [Run workflow integration proof](https://github.com/sakibshuvo/Entroping/issues/367) | Done | A Python integration test invokes `entroping run` with a fake `hurl` executable, proving discovery, gate injection, subprocess execution, source immutability, and JSON/JUnit reports together. |
| [Shell script quality gate](https://github.com/sakibshuvo/Entroping/issues/369) | Done | `scripts/shell_quality.sh` now runs `bash -n` over tracked shell scripts, runs ShellCheck when available, and is wired into the feature gate before Python checks. |

## Source Of Truth

| Question | Source |
| --- | --- |
| What work is next? | GitHub Issues, milestones, and Project board. |
| What is public direction? | `ROADMAP.md`. |
| What shipped and why? | `.context/changelog.md`, release evidence, PRs, and ADRs. |
| What is product history? | `docs/meta/VAULT_INDEX.md`, `docs/evolution/`, and curated source exports. |
| What should agents read first? | `AGENTS.md`, `docs/meta/AGENT_CONTROL_PLANE.md`, and `scripts/context_pack.sh`. |

## Update Rules

- Update this file only for current target, next queue, stable-core blockers,
  or durable evidence anchors.
- Do not duplicate the completed issue table here.
- Do not use this file as the backlog; GitHub Issues remain the backlog.
- Keep roadmap edits behind the roadmap change gate in
  [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]].
- Keep historical context in the vault and `.context/changelog.md`, not here.
