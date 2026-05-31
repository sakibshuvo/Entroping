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

This is the simple human dashboard. GitHub Issues track individual work items; this note tracks phase-level progress and the current marathon target.

## Daily Use

1. Open this note first in Obsidian.
2. Pick the one **Current** issue.
3. Run the feature through [[docs/meta/FEATURE_DELIVERY_CHECKLIST|FEATURE_DELIVERY_CHECKLIST]].
4. Use [[docs/meta/OBSIDIAN_VS_GITHUB|OBSIDIAN_VS_GITHUB]] when deciding where an idea, bug, or status update belongs.
5. Use [[docs/meta/DOCS_GOVERNANCE|DOCS_GOVERNANCE]] to decide whether roadmap or docs need updates.
6. Update this note only when phase-level status changes.

Do not duplicate every issue here. The detailed queue lives in GitHub.

## Status Key

- **Done:** committed, pushed, and CI green.
- **Current:** active implementation target.
- **Next:** queued after the current target.
- **Later:** planned after deterministic alpha.
- **Deferred:** intentionally out of scope for alpha.

## Current Target

**Goal:** finish the v0.2 adoption path by turning the proven public demo,
contributor path, downstream CI gate, and provider setup into clear packaging
and docs-site decisions.

GitHub Project: [Entroping Public Roadmap](https://github.com/users/sakibshuvo/projects/1)

GitHub milestones:

- [v0.1.1-alpha public cleanup](https://github.com/sakibshuvo/Entroping/milestone/11)
- [v0.2.0-alpha adoption and onboarding](https://github.com/sakibshuvo/Entroping/milestone/12)
- [v0.3.0-alpha product depth](https://github.com/sakibshuvo/Entroping/milestone/14)
- [v0.4.0-alpha integrations](https://github.com/sakibshuvo/Entroping/milestone/15)
- [v1.0 stable core](https://github.com/sakibshuvo/Entroping/milestone/13)

```text
init -> doctor -> load QAnstitution -> discover Hurl tests -> inject gates -> run Hurl -> JSON/JUnit report
```

## Milestone Progress

| Slice | Status | Evidence | Next proof |
| --- | --- | --- | --- |
| Repo and context scaffold | Done | CI, docs, Obsidian vault, `scripts/feature_gate.sh` | Keep context docs current |
| Issue tracking and progress system | Done | Issue templates, regression script, progress dashboard, CI regression command, issue session launcher | Keep the queue and dashboard current |
| [`init`, `doctor`, and QAnstitution loading](https://github.com/sakibshuvo/Entroping/issues/1) | Done | Minimal init, doctor config validation, local import loading, and tests | Keep docs and examples aligned |
| [Hurl discovery and metadata](https://github.com/sakibshuvo/Entroping/issues/2) | Done | Metadata parsing, recursive discovery, generated-state ignores, tag-filter validation, and tests | Feed discovery into gate injection |
| [Gate matching and injection](https://github.com/sakibshuvo/Entroping/issues/3) | Done | Policy compiler, request metadata parsing, temporary execution copies, source-immutability regression tests | Feed injected copies into Hurl subprocess runner |
| [Hurl subprocess runner](https://github.com/sakibshuvo/Entroping/issues/4) | Done | Argument-array subprocess runner, timeout handling, bounded/redacted output, temp cleanup, CLI run integration, and tests | Feed run results into reports |
| [JSON/JUnit reports](https://github.com/sakibshuvo/Entroping/issues/5) | Done | Redacted JSON, JUnit XML, latest-run state, `report bug`, and tests | Wire reports into the demo quickstart |
| [README demo quickstart](https://github.com/sakibshuvo/Entroping/issues/6) | Done | Local checkout demo server, literal Hurl fixture, README quickstart, fixture docs, and tests | Keep quickstart aligned with runner/report changes |
| [OpenAPI Architect build](https://github.com/sakibshuvo/Entroping/issues/11) | Done | Deterministic local `sources.spec` to `tests/generated/*.hurl` generation | Use `--env` to run generated variable-based tests |
| [OpenAPI compiler/audit coverage](https://github.com/sakibshuvo/Entroping/issues/143) | Done | `bridge.openapi_to_hurl` and `bridge.openapi_audit` have 100 percent focused module coverage for malformed specs, safe fallbacks, schema examples, and audit evidence matching | Keep compiler and audit behavior grounded in generated Hurl and executable exchange evidence |
| [Environment file loading](https://github.com/sakibshuvo/Entroping/issues/13) | Done | `run --env` loads `envs/<name>.env` and passes variables to Hurl | Keep variable passing hardened |
| [Hurl variable argv hardening](https://github.com/sakibshuvo/Entroping/issues/15) | Done | Hurl variables are passed through a temp `--variables-file` instead of secret-bearing argv | Keep env handling redacted |
| [HTML run reports](https://github.com/sakibshuvo/Entroping/issues/17) | Done | `run --report html` writes escaped human-readable reports | Use in demo and CI proof |
| [Live Hurl demo smoke in CI](https://github.com/sakibshuvo/Entroping/issues/19) | Done | Live smoke script and GitHub Actions job added | Keep demo path green |
| [CI Hurl download retries](https://github.com/sakibshuvo/Entroping/issues/77) | Done | Live smoke Hurl archive and checksum downloads retry transient failures before checksum verification | Keep pinned binary verification strict |
| [OpenAPI parameters and schema examples](https://github.com/sakibshuvo/Entroping/issues/23) | Done | Path/query/header/cookie parameters and request examples/defaults are supported | Keep generated demo path green |
| [Deterministic Architect audit coverage](https://github.com/sakibshuvo/Entroping/issues/25) | Done | OpenAPI coverage audit for committed executable Hurl tests is supported | Keep audit output machine-readable |
| [Non-secret agent config commands](https://github.com/sakibshuvo/Entroping/issues/29) | Done | `config list` / `config set` manage non-secret agent model routing | Keep credentials out of config |
| [Architect brain foundation](https://github.com/sakibshuvo/Entroping/issues/31) | Done | Persona loading, prompt packaging, structured edit models, and lazy LiteLLM adapter are in place | Keep provider calls outside deterministic run |
| [Architect output parser and staged writer](https://github.com/sakibshuvo/Entroping/issues/33) | Done | Provider JSON is parsed into validated edits and staged as Architect-owned Hurl files | Keep overwrite and symlink protections tested |
| [Architect prompt build happy path](https://github.com/sakibshuvo/Entroping/issues/35) | Done | `architect build --prompt` loads Builder persona/model routing, calls LiteLLM through Brain, parses JSON edits, and writes Architect-owned Hurl files | Keep prompt generation reviewable |
| [Prompt-generated Hurl validation](https://github.com/sakibshuvo/Entroping/issues/37) | Done | Prompt edits are validated through `hurlfmt` before any generated file is written | Keep parser failures non-echoing |
| [Config persona template creation](https://github.com/sakibshuvo/Entroping/issues/39) | Done | `config set` creates a missing local persona Markdown template after path safety checks | Keep setup commands usable end-to-end |
| [Architect refactor happy path](https://github.com/sakibshuvo/Entroping/issues/41) | Done | `architect refactor` safely updates selected Architect-owned Hurl files through the Brain and parser validation boundaries | Keep manual-file merge behavior explicit |
| [Architecture and provider boundary tests](https://github.com/sakibshuvo/Entroping/issues/43) | Done | AST-based regression tests enforce domain/bridge import direction, run-core isolation, and LiteLLM-only provider access | Keep process guardrails executable |
| [CI duplicate workflow reduction](https://github.com/sakibshuvo/Entroping/issues/46) | Done | CI runs on pull requests and pushes to `main`, avoiding duplicate feature-branch runs | Keep marathon feedback fast |
| [Managed-block Hurl merge](https://github.com/sakibshuvo/Entroping/issues/48) | Done | Pure bridge merge replaces explicit Entroping-managed Hurl blocks while preserving manual content outside them | Reused by managed-block refactor |
| [Managed-block Architect refactor](https://github.com/sakibshuvo/Entroping/issues/50) | Done | `architect refactor` can update manual Hurl managed blocks while preserving surrounding content | Reused by prompt build merge |
| [Prompt build merge strategy](https://github.com/sakibshuvo/Entroping/issues/52) | Done | `architect build --strategy merge --prompt` updates existing Architect-owned files or managed manual blocks | Keep non-prompt merge deferred |
| [Deterministic repo hygiene and local hooks](https://github.com/sakibshuvo/Entroping/issues/54) | Done | `repo_hygiene.sh` blocks tracked local/generated state, `feature_gate.sh` runs it, and optional hook installation is scripted | Keep deterministic gates ahead of prompt-only process |
| [Alpha release readiness gate](https://github.com/sakibshuvo/Entroping/issues/56) | Done | Release checklist and deterministic `release_check.sh` gate | Tag only after required evidence passes |
| [Open-source license and package metadata](https://github.com/sakibshuvo/Entroping/issues/58) | Done | Apache-2.0 core license, explicit package metadata, README license status, and ADR-0009 | Keep commercial surfaces separate from the public core |
| [Open-core boundary audit](https://github.com/sakibshuvo/Entroping/issues/209) | Done | `docs/product/OPEN_CORE_BOUNDARIES.md` defines public-core commitments, commercial surfaces, and decision checks before monetized add-ons | Keep local runtime governance strong while monetizing aggregation, hosted, policy-pack, and service layers |
| [Eye redaction and traffic store foundation](https://github.com/sakibshuvo/Entroping/issues/61) | Done | Security-first capture models, redaction, and local SQLite state | Build before mitmproxy `watch` wiring |
| [Eye watch capture-only workflow](https://github.com/sakibshuvo/Entroping/issues/60) | Done | mitmproxy capture command after redaction/store foundation | Keep freeze/map out of scope |
| [Freeze/map implementation plan](https://github.com/sakibshuvo/Entroping/issues/59) | Done | Design traffic-to-Hurl and dependency export before implementation | Split into focused implementation issues |
| [Traffic filtering and session candidates](https://github.com/sakibshuvo/Entroping/issues/66) | Done | Pure bridge filtering/session inputs for freeze and map | Keep SQLite/proxy/CLI out of bridge |
| [Traffic-to-Hurl compiler](https://github.com/sakibshuvo/Entroping/issues/67) | Done | Compile redacted sessions into valid Hurl content | Depends on #66 |
| [Freeze CLI safe writes](https://github.com/sakibshuvo/Entroping/issues/68) | Done | Wire `freeze` to store reads, compiler output, staged writes, and parser validation | Depends on #66 and #67 |
| [Dependency graph export](https://github.com/sakibshuvo/Entroping/issues/69) | Done | Host-level graph compiler plus Mermaid/Markdown/DOT exports | Keep output escaping tested |
| [WireMock dependency mappings](https://github.com/sakibshuvo/Entroping/issues/75) | Done | `freeze --mock <service>` writes WireMock-compatible mappings from redacted dependency traffic | Keep mappings redacted |
| [PNG dependency map rendering](https://github.com/sakibshuvo/Entroping/issues/80) | Done | `map --export png` writes `reports/dependency-map.png` through local Graphviz `dot` when available | Keep renderer optional and subprocess-bounded |
| [Distribution and install polish](https://github.com/sakibshuvo/Entroping/issues/82) | Done | GitHub branch/tag install docs plus deterministic wheel/sdist metadata verification | Keep package publishing credentials out of the repo |
| [Cross-platform install smoke matrix](https://github.com/sakibshuvo/Entroping/issues/206) | Done | `install-smoke` proves uv tool install on Linux, macOS, and Windows with explicit Hurl modes and Windows doctor-only non-claim | Keep platform claims tied to CI/manual evidence |
| [Bounded parallel Hurl execution](https://github.com/sakibshuvo/Entroping/issues/83) | Done | `run --parallel` uses QAnstitution worker limits and preserves deterministic result ordering | Keep run path LLM-free |
| [Versioned report schemas](https://github.com/sakibshuvo/Entroping/issues/203) | Done | `entroping.run-report.v1`, `entroping.drift-report.v1`, and `entroping.traceability-report.v1` are documented and covered by contract tests | Add new schema versions for breaking report changes |
| [GitHub PR annotations](https://github.com/sakibshuvo/Entroping/issues/200) | Done | `report github-annotations` emits workflow-command annotations from JUnit, drift, and optional traceability findings without GitHub API calls | Keep annotations redacted and artifact-backed |
| [Deterministic drift report MVP](https://github.com/sakibshuvo/Entroping/issues/84) | Done | `run --drift-check --report drift` compares current run state with `.entroping/drift-baseline.json` | Keep baseline state value-free |
| [Reviewed drift baseline workflow](https://github.com/sakibshuvo/Entroping/issues/197) | Done | `--report drift` writes `reports/drift-baseline.candidate.json` after passing Hurl runs so users review and promote baselines deliberately | Never auto-write active drift baselines |
| [Structured response drift](https://github.com/sakibshuvo/Entroping/issues/110) | Done | Drift reports compare optional response status, selected stable headers, and JSON body shape fingerprints without storing response values | Add dependency drift only with stable traffic baseline data |
| [Latency regression drift findings](https://github.com/sakibshuvo/Entroping/issues/176) | Done | Drift reports warn when current per-test duration materially exceeds a reviewed baseline duration | Keep thresholds conservative so local timing noise does not churn reports |
| [Dependency-call drift](https://github.com/sakibshuvo/Entroping/issues/178) | Done | Drift reports compare `.entroping/dependency-baseline.json` route identities against current redacted traffic observations | Keep dependency drift route-only and value-free |
| [Read-only Studio status shell](https://github.com/sakibshuvo/Entroping/issues/85) | Done | `studio --env <name>` inspects QAnstitution, latest run, reports, and traffic-state availability when the optional Studio extra is installed | Superseded by interactive read-only Studio |
| [Interactive Studio TUI](https://github.com/sakibshuvo/Entroping/issues/180) | Done | `studio --env <name>` opens a Textual TUI with summary, suite, failures, reports, and traffic tabs | Keep Studio read-only until mutation workflows are designed |
| [Architect build mode guidance](https://github.com/sakibshuvo/Entroping/issues/95) | Done | `architect build` without a mode now prints supported-mode guidance instead of scaffold placeholder text | Keep shipped commands actionable |
| [Command compatibility audit](https://github.com/sakibshuvo/Entroping/issues/205) | Done | `docs/technical/CLI_COMPATIBILITY_AUDIT.md` records locked command signatures, exit-code policy, deprecated aliases, and report artifacts with regression tests against Typer help and docs | Require a compatibility issue before command, flag, alias, exit-code, or artifact changes |
| [Coverage artifact hygiene](https://github.com/sakibshuvo/Entroping/issues/97) | Done | `.coverage`, `coverage.xml`, and `htmlcov/` are ignored with a regression test | Add repeatable quality audit gate |
| [Context refresh](https://github.com/sakibshuvo/Entroping/issues/92) | Done | `.context/plan.md` and this dashboard now match the post-alpha implementation surface | Keep future agent sessions grounded |
| [Quality audit gate](https://github.com/sakibshuvo/Entroping/issues/93) | Done | `scripts/audit_quality.sh` runs coverage, complexity, maintainability, and dead-code gates | Prevent silent quality drift |
| [CI security and quality gates](https://github.com/sakibshuvo/Entroping/issues/148) | Done | GitHub Actions runs `scripts/regression.sh --security`, runs `scripts/audit_quality.sh`, and uploads quality reports | Keep CI/runtime cost visible as the suite grows |
| [Performance smoke evidence](https://github.com/sakibshuvo/Entroping/issues/208) | Done | `scripts/performance_smoke.py` generates bounded large-suite, parallel-run, report-size, and traffic-store evidence under `reports/performance-smoke.json` | Review before stable-core scalability claims |
| [Pinned live-demo Hurl checksum](https://github.com/sakibshuvo/Entroping/issues/150) | Done | `live-demo-smoke` verifies the downloaded Hurl archive against reviewed `HURL_SHA256` instead of a runtime sidecar download | Update version and checksum together when bumping Hurl |
| [Atomic artifact writes](https://github.com/sakibshuvo/Entroping/issues/149) | Done | Shared `core.safe_write` handles fsynced temp writes, symlink rejection, atomic replacement, and no-partial-replacement behavior for reports, freeze outputs, drift reports, and PNG maps | Keep future artifact writers on the shared helper |
| [Deterministic support-module coverage](https://github.com/sakibshuvo/Entroping/issues/146) | Done | `core.dependency_mapper`, `core.drift_report`, `models.traffic`, and `studio.status` have 100 percent focused coverage | Keep tests meaningful as behavior changes |
| [Eye proxy and freeze coverage](https://github.com/sakibshuvo/Entroping/issues/145) | Done | `core.traffic_proxy` and `core.freeze` have 100 percent focused coverage without live mitmproxy or network sessions | Keep proxy tests fake-only unless explicitly running integration tests |
| [Architect workflow coverage](https://github.com/sakibshuvo/Entroping/issues/144) | Done | `brain.architect_build`, `brain.architect_refactor`, and `brain.architect_writer` have 100 percent focused coverage for merge/refactor/write edge cases | Keep provider calls out of regression tests |
| [Brain provider and persona boundary coverage](https://github.com/sakibshuvo/Entroping/issues/157) | Done | `brain.persona_loader` and `brain.litellm_client` have 100 percent focused coverage without provider or network calls | Keep provider and network calls out of tests |
| [CLI adapter coverage](https://github.com/sakibshuvo/Entroping/issues/159) | Done | `cli.main` has 100 percent focused coverage across command display, helper, and error branches | Use the full quality audit as the release-level proof |
| [Architect validation UX](https://github.com/sakibshuvo/Entroping/issues/179) | Done | Architect parse and Hurl validation failures now print actionable no-write guidance without echoing raw provider/parser streams | Keep broader Architect UX changes issue-scoped |
| [Architect remediation guidance](https://github.com/sakibshuvo/Entroping/issues/199) | Done | Invalid provider JSON and parser-rejected Hurl now include safe retry guidance while preserving no-write behavior and raw-output redaction | Keep provider troubleshooting guidance aligned with CLI errors |
| [100 percent coverage release gate](https://github.com/sakibshuvo/Entroping/issues/112) | Done | `scripts/audit_quality.sh` defaults to `ENTROPING_COVERAGE_FAIL_UNDER=100` and the full suite currently reports 100.00 percent coverage | Keep future gaps explicit and tracked |
| [Finish-issue workflow](https://github.com/sakibshuvo/Entroping/issues/94) | Done | `scripts/finish_issue.sh` verifies merged PRs, CI, clean issue worktrees, and project hygiene before local cleanup | Make multi-session marathons safer |
| [Story traceability bridge](https://github.com/sakibshuvo/Entroping/issues/91) | Done | Pure bridge report maps Hurl metadata to stories, owners, docs, tests, tags, and traceability findings | Keep external business-system sync out of scope |
| [Traceability report CLI](https://github.com/sakibshuvo/Entroping/issues/106) | Done | `entroping report traceability --output md` renders local story/test metadata and fails on missing story IDs or conflicting doc links | Keep output Markdown-only until a downstream consumer needs JSON |
| [Launch demo assets](https://github.com/sakibshuvo/Entroping/issues/108) | Done | README links a two-minute launch asset hub with real terminal output, curated PNG screenshots, HTML report evidence, and a dependency-map example | Keep launch media small, reproducible, and tied to the checkout fixture |
| [README open-source front door](https://github.com/sakibshuvo/Entroping/issues/174) | Done | README now leads with the AI-regression hook, two-minute live demo proof, concise value props, launch assets, and alpha boundaries before deep docs | Keep the front page demo-first as the product surface grows |
| [Public clean-checkout onboarding smoke](https://github.com/sakibshuvo/Entroping/issues/185) | Done | Fresh public clone on macOS 26.5 arm64 completed `uv sync --dev`, verified Hurl 8.0.1 on PATH, ran `scripts/live_demo_smoke.sh`, and passed `scripts/release_check.sh --require-live-demo` | Capture issue evidence and keep README quickstart honest |
| [Zero-config demo entrypoint](https://github.com/sakibshuvo/Entroping/issues/230) | Done | `scripts/demo.sh` is the friendly checkout command, delegates to the live smoke release gate, and is documented by `docs/meta/ZERO_CONFIG_DEMO_ENTRYPOINT.md` | Revisit `entroping demo` only after packaging/demo fixture distribution is settled |
| [First-hour QAnstitution UX](https://github.com/sakibshuvo/Entroping/issues/232) | Done | `init --minimal`, the checkout demo policy, and `docs/user/QANSTITUTION_FIRST_HOUR.md` now share schema-validated status, latency, and request-ID header gates | Keep first-hour examples aligned with the starter policy |
| [Curated public launch previews](https://github.com/sakibshuvo/Entroping/issues/191) | Done | README and launch hub link terminal, HTML report, and dependency-map PNGs generated from live checkout fixture output and redacted traffic state | Replace media only from reproducible source commands |
| [Good-first-issue contributor walkthrough](https://github.com/sakibshuvo/Entroping/issues/184) | Done | New contributor guide explains labels, milestones, `scripts/start_issue.sh`, validation gates, and PR documentation expectations | Keep first-contribution path small as workflow grows |
| [Downstream GitHub Actions starter](https://github.com/sakibshuvo/Entroping/issues/189) | Done | Copyable workflow installs tagged Entroping, verifies pinned Hurl, runs `entroping run --ci --report junit --report html`, and uploads reports | Keep starter aligned with current report paths and release tag |
| [Brain provider setup guide](https://github.com/sakibshuvo/Entroping/issues/195) | Done | LiteLLM, local Qwen through Ollama/oMLX, cloud routing, `api_base`, `api_key_env`, secret rules, and no-provider CI are documented and schema-backed | Keep model/provider docs current without making `entroping run` depend on LLM access |
| [PyPI/TestPyPI release path](https://github.com/sakibshuvo/Entroping/issues/186) | Done | TestPyPI-first Trusted Publishing runbook covers token-free GitHub Actions environments, PEP 440 alpha naming, preflight checks, PyPI publish policy, and yank/new-version rollback | Do not add active publish automation until GitHub environments and trusted publishers are configured |
| [Public docs site decision](https://github.com/sakibshuvo/Entroping/issues/188) | Done | MkDocs Material decision, `mkdocs.yml`, and `docs/index.md` scaffold publish existing canonical Markdown without duplicating the docs tree | Add deployment only after Pages settings and curated nav are reviewed |
| [Distribution path recommendation](https://github.com/sakibshuvo/Entroping/issues/183) | Done | Recommendation keeps `uv tool install` first, PyPI/TestPyPI next, Homebrew tap after PyPI alpha, and standalone binaries later; follow-up issues #223 through #225 track implementation | Keep signing/notarization out until demand justifies it |
| [Run orchestration extraction](https://github.com/sakibshuvo/Entroping/issues/90) | Done | `core.run_workflow` now owns deterministic run orchestration and returns a typed workflow result | Keep future run flags out of the CLI adapter |
| [Post-alpha security review](https://github.com/sakibshuvo/Entroping/issues/96) | Done | PR #105 merged the local boundary hardening after fixing 14 validated candidates; scan artifacts live under `/tmp/codex-security-scans/Entroping/eb08827323c6_20260530T160200Z/` | Keep security scans tied to concrete remediation branches |
| [Stable-core threat model refresh](https://github.com/sakibshuvo/Entroping/issues/207) | Done | `docs/technical/THREAT_MODEL.md` now tracks current runtime surfaces, controls, prior validated findings, and residual-risk follow-up issues | Review before stable-core security claims |
| [Captured-traffic redaction review](https://github.com/sakibshuvo/Entroping/issues/198) | Done | `entroping report redaction --output md|html` writes counts-only reports for header, query, body-field, and body-summary redaction categories | Keep reports free of raw captured values |
| [Optional-extras runtime smoke](https://github.com/sakibshuvo/Entroping/issues/227) | Done | GitHub Actions installs all optional extras and runs `scripts/optional_extras_smoke.py` against LiteLLM, mitmproxy, and Textual boundaries without credentials or live capture | Keep default regression lightweight while proving optional adapters boot |
| [Studio scope decision](https://github.com/sakibshuvo/Entroping/issues/231) | Done | ADR-0010 keeps v0.3 CLI/report-first, allows only optional read-only report-backed Studio drilldowns, and keeps mutation work design-only | Update Studio issues before implementation |

## Later Roadmap

| Phase | Status | Notes |
| --- | --- | --- |
| OpenAPI Build | Done | Dedicated bridge compiler, local loader, and `architect build --new` |
| Runner Usability | Done | Local env-file loading for generated Hurl variables |
| Reporting Polish | Done | Dependency-free HTML run reports |
| Drift Reports | Done | MVP compares test path, Hurl status, exit code, injected rule IDs, material latency regressions, and optional value-free response fingerprints |
| CI Proof | Done | Live demo smoke with real Hurl in GitHub Actions |
| Runner Parallelism | Done | Bounded `run --parallel` with deterministic report ordering |
| OpenAPI Depth | Done | Path/query/header/cookie parameters plus schema examples/defaults |
| Architect Minimal | Done | Prompt generation, prompt-backed build merge, pre-write Hurl validation, Architect-owned refactor, and managed-block manual refactor are available |
| Delivery Automation | Done | Deterministic repo hygiene, issue worktrees, regression gates, optional local hooks, and release-readiness checks support multi-session development |
| Alpha Release | Done | `v0.1.0-alpha` prerelease published from `abd08c0`; `v0.1.1-alpha` sync is the current public-roadmap/release evidence target | Keep public release notes tied to current `main` evidence |
| Eye Capture Spike | Done | Capture-only `watch` records redacted, bounded traffic through mitmproxy; freeze/map remain separate |
| Freeze and Map | Done | Basic `freeze`, WireMock dependency mocks, and Mermaid/DOT/Markdown/PNG dependency maps are in place |
| Agent Workflow | Done | Deterministic context packs, configurable source-archive paths, portable cross-agent docs, source-promotion workflow, and community health docs are available | Use issue branches for follow-on automation |
| Coverage Hardening | Done | `scripts/audit_quality.sh` enforces 100 percent coverage by default; `cli.main`, `core.session_prompt`, `core.config_loader`, `core.config_writer`, `core.dependency_mapper`, `core.drift_report`, `core.env_loader`, `core.freeze`, `core.gate_injector`, `core.openapi_loader`, `core.hurl_discovery`, `core.hurl_runner`, `core.hurl_validator`, `core.report_writer`, `core.safe_write`, `core.traffic_proxy`, `core.traffic_redactor`, `core.traffic_store`, `studio.app`, `studio.status`, `brain.architect_build`, `brain.architect_refactor`, `brain.architect_writer`, `brain.litellm_client`, `brain.output_parser`, `brain.persona_loader`, `brain.prompt_builder`, `brain.safety`, `models.hurl`, `models.traffic`, `bridge.merge`, `bridge.openapi_audit`, `bridge.openapi_to_hurl`, `bridge.policy_to_hurl`, `bridge.story_traceability`, `bridge.traffic_sessions`, `bridge.traffic_to_graph`, `bridge.traffic_to_hurl`, and `bridge.traffic_to_wiremock` have 100 percent module coverage | Keep future gaps explicit and tracked |
| Public Trust Signals | Done | Community-profile audit script, README Scorecard badge, and scheduled/manual OpenSSF Scorecard workflow are in place | Manually dispatch Scorecard after public repo settings are ready |
| Launch Assets | Done | Launch kit links curated PNG previews for terminal smoke, HTML report, and dependency map plus portable rebuild/source commands from README and Obsidian index | Keep raw generated media out of Git |
| Studio | Done | Interactive read-only Textual TUI is available; v0.3 Studio work is optional, report-backed, and mutation-free by ADR-0010 |

## Update Rules

- Update this file after every meaningful feature, bug fix, or roadmap change.
- Keep this file phase-level; do not duplicate every GitHub issue.
- Link durable decisions to ADRs.
- Keep `.context/changelog.md` as the chronological handoff log.
- Keep `.context/lessons-learned.md` for durable pitfalls only.
