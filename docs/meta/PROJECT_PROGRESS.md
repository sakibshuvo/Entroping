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

Current issue: [#427](https://github.com/sakibshuvo/Entroping/issues/427)
writes sanitized agent run manifests after bounded retry/flake evidence and
capture filters landed.
Next local slices should keep moving useful runtime and developer workflow
features before returning to blocked external stable-core proof.

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
| 1 | [#427](https://github.com/sakibshuvo/Entroping/issues/427) | Write sanitized agent run manifests. |
| 2 | [#440](https://github.com/sakibshuvo/Entroping/issues/440) | Add tag-expression test selection for faster local loops. |
| 3 | [#441](https://github.com/sakibshuvo/Entroping/issues/441) | Add explicit timeout evidence per test. |

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
| [Include/exclude capture filters](https://github.com/sakibshuvo/Entroping/issues/414) | Done | `freeze`, `freeze --mock`, and `map` now filter already-redacted traffic by host, method, and request path before Hurl, WireMock, or dependency-map artifact generation; exclude rules win and empty filtered sessions fail before writes. |
| [Retry and flake evidence](https://github.com/sakibshuvo/Entroping/issues/405) | Done | `settings.retry` now drives bounded per-file Hurl subprocess retries, final attempt status remains authoritative, and JSON/JUnit/HTML/review-summary artifacts expose retry count, attempt status, exit code, duration, and unstable pass-after-retry signals without raw per-attempt output. |
| [Changed OpenAPI operation generation](https://github.com/sakibshuvo/Entroping/issues/404) | Done | `architect build --new --changed-from <ref>` compares the configured local OpenAPI spec with the same file at a Git base ref, regenerates only current added/modified/renamed operations, and reports removed operations for manual review. |
| [Sanitized failure bundles](https://github.com/sakibshuvo/Entroping/issues/403) | Done | `report failure-bundle` writes a local sanitized handoff directory with manifest, run JSON, bug Markdown, failed-test Hurl metadata, and reviewed report artifacts while refusing missing/passing runs, raw traffic state, env files, and unsafe artifact paths. |
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
| [OpenAPI-generated Hurl pre-write validation](https://github.com/sakibshuvo/Entroping/issues/342) | Done | `architect build --new` validates every compiled Hurl file before writing and leaves no partial files on parser failure. |
| [HTML run-summary escaping](https://github.com/sakibshuvo/Entroping/issues/343) | Done | `run --report html` escapes the summary header consistently with other rendered report fields. |
| [Slim public launch docs path](https://github.com/sakibshuvo/Entroping/issues/348) | Done | README and MkDocs lead with demo/user/policy/CI paths while vault/internal memory stays preserved behind project context. |
| [Brand terminology and QAnstitution naming decision](https://github.com/sakibshuvo/Entroping/issues/349) | Done | ADR-0012 keeps `qanstitution.yaml` canonical, preserves the core philosophy, and rejects unplanned aliases or autonomous-swarm positioning. |
| [Practical watch TLS and proxy limits](https://github.com/sakibshuvo/Entroping/issues/350) | Done | User docs now set expectations for mitmproxy CA setup, corporate VPN/proxy conflicts, certificate pinning, proxy bypass, session headers, and capture authorization. |
| [OWASP API Top 10 starter policy pack](https://github.com/sakibshuvo/Entroping/issues/351) | Done | A local OWASP API Security Top 10-inspired starter pack now proves the policy-pack path without claiming endorsement, certification, or complete compliance. |
| [Shared symlink component path-safety helper](https://github.com/sakibshuvo/Entroping/issues/344) | Done | Common symlink component traversal is centralized while config imports now reject symlinked local imports and adapters keep domain-specific errors. |
| [Traffic-store retention SQL pruning](https://github.com/sakibshuvo/Entroping/issues/345) | Done | Local Eye state now deletes stale traffic rows with a SQL-level delete while keeping newest-event retention and insertion-order reads. |
| [No-Hurl CLI smoke script](https://github.com/sakibshuvo/Entroping/issues/346) | Done | `scripts/cli_smoke.sh` proves CLI boot, version, minimal init, and doctor behavior without requiring Hurl runtime execution. |
| [Typer shell-completion onboarding](https://github.com/sakibshuvo/Entroping/issues/347) | Done | README and user guide now point to Typer's existing completion global options without adding an Entroping subcommand. |
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
| [CLI adapter test split](https://github.com/sakibshuvo/Entroping/issues/368) | Done | The former 3,374-line CLI adapter test file is split into command-focused files with shared CLI test helpers and the same 113 assertions preserved. |
| [Report writer module split](https://github.com/sakibshuvo/Entroping/issues/370) | Done | Report building keeps the existing facade while JSON serialization, response fingerprinting, JUnit/HTML/bug rendering, and report errors now live in focused modules. |
| [Vault/context archival cleanup](https://github.com/sakibshuvo/Entroping/issues/371) | Done | One-off demo-entrypoint context is marked archival, evolution docs are labeled historical evidence, and Obsidian/GitHub/source-promotion guides have explicit ownership boundaries. |
| [Read-only Studio applied-gate drilldowns](https://github.com/sakibshuvo/Entroping/issues/192) | Done | Studio links latest-run report rule IDs to QAnstitution gate definitions. |
| Read-only Studio traffic session browser | Done | The read-only traffic session browser uses redacted SQLModel-backed state, target/dependency grouping, and safe redaction categories and counts. It does not start `watch` and does not expose raw URLs with query values, headers, bodies, cookies, tokens, or secrets. |

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
- Keep historical context in the vault and `.context/changelog.md`, not in the
  daily dashboard.
