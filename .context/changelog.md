# Entroping Changelog

## 2026-06-04

- Added issue #403's sanitized failure-bundle workflow so
  `entroping report failure-bundle` writes `reports/failure-bundle/manifest.json`
  with `entroping.failure-bundle.v1`, sanitized latest-run JSON, generated bug
  Markdown, failed-test Hurl metadata, optional reviewed report artifacts,
  artifact sizes/hashes, and guardrails against missing/passing runs, raw local
  state, env files, symlinked artifacts, and source Hurl contents.

## 2026-06-03

- Added issue #402's named suite manifests so `entroping run --suite <name>`
  loads committed `suites/<name>.yaml` files with schema
  `entroping.suite.v1`, root-bounded path globs, tags, env, reports, parallel,
  and drift settings while preserving the existing deterministic run workflow.
- Added issue #401's local policy-pack vendoring workflow so
  `entroping config vendor-policy-pack` copies reviewed local packs under
  `policy-packs/`, validates manifest and QAnstitution evidence, preserves
  final-gate behavior, and appends a local import without remote registry
  coupling.
- Added issue #400's OpenAPI operation-to-Hurl coverage matrix so
  `architect audit --focus logic --output md|json` now reports covered,
  uncovered, ambiguous, and stale operation mappings with
  `entroping.openapi-audit.v1` JSON output and project-relative Hurl paths.
- Added issue #399's reviewed drift-baseline promotion command so
  `entroping report promote-drift-baseline` validates
  `entroping.drift-baseline.v1` candidates, rejects unsafe paths and
  stale/future schemas, and atomically writes `.entroping/drift-baseline.json`
  only after human review.
- Added issue #398's SARIF report output so `entroping report sarif` writes
  `reports/entroping.sarif` from local JUnit, drift, and optional traceability
  findings with stable rule IDs, SARIF severities, best-effort locations,
  redacted text, and no provider calls or upload side effects.
- Added issue #397's changed-test run mode so
  `entroping run --changed-from <ref>` selects existing changed `.hurl` files
  from Git diff for fast local or agent feedback while preserving full-suite
  `run` as the default release gate.
- Added issue #395's machine-readable doctor output so
  `entroping doctor --output json` emits schema version
  `entroping.doctor.v1` with tool, traffic-state, QAnstitution, and
  agent-readiness health while preserving human doctor exit semantics.
- Added issue #394's doctor agent-readiness validation so configured
  Builder/Auditor/Breaker persona files are checked through the runtime persona
  loader, unsafe persona setup fails locally, and configured `api_key_env`
  names are reported without printing secret values or calling providers.
- Added issue #396's Hurl variable preflight so `entroping run` scans
  selected temporary execution copies before invoking Hurl, fails early with
  missing variable names only, accepts `envs/<name>.env`, shell
  `HURL_VARIABLE_<name>`, Hurl `[Options] variable`, captures, and safe Hurl
  built-ins, and keeps variable values out of CLI errors.
- Added issue #393's Auditor-backed Architect audit route so
  `architect audit --focus auditor` loads the configured Auditor persona/model,
  sends deterministic coverage and path-only Hurl inventory context, validates
  review JSON before display, and renders Markdown or JSON without writing files.
- Added issue #392's Breaker-backed Architect prompt build route so
  `architect build --agent breaker --prompt ...` loads the configured Breaker
  persona/model, adds Breaker-specific generation instructions, tags generated
  Hurl with `breaker`, and keeps Auditor out of prompt-build file generation.
- Added issue #385's transitive dependency security refresh so `uv.lock` moves
  optional `litellm`'s `aiohttp` dependency from vulnerable `3.13.5` to
  `3.14.0`, restoring the all-extras dependency audit gate without adding a
  direct runtime dependency.
- Added issue #381's README OWASP policy-pack wedge so the public launch story
  highlights the local starter pack as runtime security governance while
  preserving explicit non-endorsement, non-compliance, and non-certification
  boundaries.
- Added issue #382's README backstage-context cleanup so first-time users see
  the product, demo, install, and CI path before maintainer vault, release, and
  agent-handoff material.
- Added issue #383's README schema-autocomplete note so new users can find the
  checked-in QAnstitution JSON Schema while `entroping doctor` stays the
  authoritative runtime validation path.
- Added issue #384's launch-copy cleanup so the public first story stays
  focused on REST/OpenAPI, QAnstitution, Hurl, and CI reports while advanced
  surfaces remain documented as optional or deeper examples.
- Added issue #372's post-alpha CLI UX decision queue so env-file paths,
  generated output roots, deprecated command guidance, and QAnstitution policy
  migration rules are documented before any command-surface change.

## 2026-06-02

- Added issue #371's vault/context cleanup so completed one-off demo context is
  marked archival, evolution docs are labeled historical evidence rather than
  current product truth, and Obsidian/GitHub/source-promotion guides have
  explicit ownership boundaries.
- Added issue #370's report writer module split so the public
  `entroping.core.report_writer` facade remains stable while response
  fingerprinting, JSON serialization, JUnit/HTML/bug rendering, and report
  errors move into focused core modules.
- Added issue #368's CLI adapter test split so the former 3,374-line
  `tests/test_cli.py` is now organized by command area, with shared CLI test
  helpers and the existing 113 assertions preserved.
- Added issue #369's shell script quality gate so tracked `.sh` files are
  checked with `bash -n`, ShellCheck runs when available with an explicit skip
  message otherwise, and `scripts/feature_gate.sh` executes the shell gate
  before Python lint/type/test checks.
- Added issue #367's Python integration proof for `entroping run`, using a
  fake `hurl` executable on `PATH` to exercise CLI wiring, discovery, gate
  injection, variables-file passing, subprocess execution, source immutability,
  and JSON/JUnit report writing without network access.
- Added issue #366's PEP 561 package marker so `src/entroping/py.typed` ships
  with the wheel and sdist, while `scripts/package_check.sh` and its tests now
  fail if package artifacts omit `entroping/py.typed`.
- Added issue #365's captured-traffic redaction hardening so multipart request
  and response bodies are replaced with redacted media-type summaries before
  persistence, broad token prefix patterns avoid short documentation
  placeholders, and harmless Bearer prose is preserved while common credential
  coverage remains tested.
- Added issue #364's hardened XML report parsing so JUnit inputs consumed by
  GitHub annotations and review summaries use `defusedxml`, reject DTD/entity
  constructs as unsafe XML, keep valid JUnit behavior intact, and include
  `defusedxml` in the reviewed direct dependency license policy.

## 2026-06-01

- Added issue #347's shell-completion onboarding note for Typer's existing
  `--install-completion` and `--show-completion` global options without
  expanding Entroping's locked command namespace.
- Added issue #346's no-Hurl CLI smoke script so constrained agent or
  downstream sessions can prove CLI boot, version, minimal init, and doctor
  behavior without installing or executing Hurl.
- Added issue #345's traffic-store retention optimization so pruning now uses
  a SQL-level delete for stale event IDs while preserving newest-event
  retention semantics and insertion-order reads.
- Added issue #344's shared path-safety helper so common symlink component
  traversal lives in `entroping.core.path_safety`, config imports reject
  symlinked local imports, and existing adapters keep their domain-specific
  error messages.
- Added issue #351's OWASP API Security Top 10-inspired starter policy pack
  under `examples/policy-packs/owasp-api-top-10/`, with local QAnstitution
  imports, provenance metadata, smoke evidence, honest non-compliance claims,
  and open-core boundary notes for deeper maintained packs and support.
- Added issue #350's practical `watch` limits guidance so the user guide now
  warns about per-client mitmproxy CA setup, corporate VPN/proxy conflicts,
  certificate pinning, proxy bypass, session headers, and capture authorization
  before users try real traffic interception.
- Added issue #349's brand-integrity audit: ADR-0012 keeps
  `qanstitution.yaml` canonical, preserves "The QAnstitution is Law. Traffic
  is Truth. Hurl is the Enforcer.", rejects unplanned `entroping.yaml` aliases,
  and tightens public positioning away from autonomous-agent-swarm claims.
- Added issue #348's public-docs launch-path cleanup so README uses a concise
  `Project Context` handoff instead of a deep-docs inventory, MkDocs navigation
  is grouped by reader task, and documentation governance blocks casual
  first-level public-nav expansion.
- Added issue #343's HTML run-summary escaping so the local HTML report now
  escapes the summary header consistently with project, environment, generated
  timestamp, rule IDs, known-failure summaries, and captured output.
- Added issue #342's OpenAPI-generated Hurl validation so
  `architect build --new` validates every compiled Hurl file through the
  parser-backed Hurl validator before writing and leaves no partial generated
  files behind when validation fails.
- Added issue #352's progress and agent-control cleanup so
  `docs/meta/PROJECT_PROGRESS.md` is a short daily dashboard again,
  `ROADMAP.md` separates product direction from backlog tracking,
  `docs/meta/DOCS_GOVERNANCE.md` blocks new strategy-doc sprawl, and
  `docs/meta/AGENT_CONTROL_PLANE.md` defines the Codex-first software-factory
  model for OpenCode/free-model/local-Qwen workers.
- Added issue #340's public-docs discoverability cleanup so the README links
  the MkDocs site before deep context, the MkDocs landing page explains how it
  relates to GitHub Issues, ROADMAP, Obsidian, and docs governance, and the
  documentation control plane names each canonical surface.
- Added issue #337's GraphQL and SOAP Hurl-over-HTTP fixtures with local demo
  servers, QAnstitution gates, env examples, protocol-specific Hurl assertions,
  and README/Vault discoverability without adding new protocol engines.
- Added issue #336's runtime known-failure semantics so active
  `ignore_failures` entries skip only matching Entroping-injected QAnstitution
  gates by exact test path and rule ID, expired exceptions block before Hurl
  execution, and JSON/JUnit/HTML run reports expose the applied exception
  evidence.
- Added issue #329's reusable policy-pack verification artifact so
  `scripts/policy_pack_smoke.py --pack <local-pack> --format json --strict`
  validates arbitrary local pack directories, emits attachable
  `policy-pack-verification` evidence, and checks attribution, entrypoint
  imports, final gates, and consumer examples without registry or runtime
  manifest behavior.
- Added issue #307's repeated alpha release evidence so the committed ledger
  records `v0.1.2-alpha-rc.1` local release-candidate rehearsal proof with
  reviewed CI/Pages run IDs and a passing `scripts/release_check.sh
  --require-live-demo` gate, while stable-core remains blocked by package-index
  proof, compatibility discipline, and real downstream user feedback.
- Added issue #312's policy-pack distribution decision so packs have a
  local-first path for versioning, distribution, import verification,
  provenance, attribution, open-core/premium boundaries, minimum smoke evidence,
  and follow-up implementation issues before registries or hosted catalogs.
- Added issue #318's downstream feedback evidence kit so real external-user
  feedback can be collected with install path, OS, Python, Hurl, command,
  success/failure, friction, and sanitized logs while excluding secrets,
  private URLs, raw traffic, and proprietary payloads.
- Added issue #317's policy-pack provenance validation so the example
  API-baseline manifest declares local source, license, supported Entroping
  range, evidence command, gate files, gate IDs, and final flags, and
  `scripts/policy_pack_smoke.py --strict` verifies those claims against loaded
  QAnstitution gates without adding registry behavior.
- Added issue #316's artifact-backed review summary:
  `entroping report review-summary` writes provider-neutral Markdown from local
  JSON, JUnit, drift, and optional traceability evidence, and the downstream
  GitHub Actions starter now generates JSON before uploading `reports/`.
- Added issue #319's stable-core blocker issue map so
  `scripts/stable_core_readiness.py --format json` and Markdown output link
  each unresolved stable-core blocker to the GitHub issues that can satisfy it,
  without changing `stable_core_ready=false`.
- Added issue #315's optional release-evidence freshness check so maintainers
  can compare committed CI/Pages run IDs and commits with latest successful
  `main` runs through `gh`, or fixture input in tests, without mutating the
  ledger or making normal release validation network-dependent.
- Added issue #314's downstream smoke release-gate wiring so
  `scripts/release_check.sh` runs `scripts/downstream_smoke.py` when Hurl is
  available, supports `--skip-downstream-smoke` for diagnostics, and reports
  missing-Hurl versus Entroping-run failures distinctly.
- Added issue #313's local wheel install smoke so release checks can install
  the built wheel into a temporary venv, run only installed public CLI commands
  from a temporary project, and emit machine-readable evidence without
  PyPI/TestPyPI or network registry access.
- Aligned issue #301's release-evidence blocker list with stable-core
  readiness so package-index proof, real downstream feedback, and compatibility
  decision remain consistent across both gates.
- Expanded issue #299's release-evidence validator so Pages CI and local
  downstream smoke evidence are strict ledger fields, while the ledger still
  states that stable-core remains blocked by package-index proof,
  compatibility decision, and real downstream user feedback.
- Added issue #297's downstream smoke evidence harness so maintainers can prove
  Entroping runs through the public CLI from an external temporary project while
  keeping real downstream user feedback as a separate stable-core blocker.
- Clarified issue #295's release-evidence wording so committed CI evidence is
  treated as last reviewed release evidence, not a self-updating current-HEAD
  assertion.
- Added issue #293's release-evidence ledger so alpha releases, last reviewed
  `main` CI, package-index status, and stable-core blockers are committed and
  validated by `scripts/release_evidence.py --strict`,
  `scripts/stable_core_readiness.py`, and the release gate.
- Added issue #291's README launch-polish slice: concrete "Use Entroping
  When" scenarios now appear before the demo, and reviewed animated GIF
  previews show the checkout happy path plus AI-regression failure proof.
- Added issue #279's effective policy evidence command:
  `entroping report policy --output md|json` writes resolved QAnstitution
  gate provenance, including imports and local overrides.
- Added issue #280's public claims audit so documentation governance blocks
  unsupported production-readiness and security-guarantee language before it
  reaches public Markdown.
- Added issue #281's direct dependency license policy gate with reviewed
  runtime, optional, and dev dependency entries plus security-gate wiring.
- Added issue #282's downstream integration guardrails so only the proven
  GitHub Actions template is committed and other CI providers require real
  runner evidence before native examples land.
- Added issue #283's AI-regression failure proof fixture and script, showing
  Entroping blocking a body-correct API that drops `X-Request-Id`.
- Added issue #284's stable-core readiness evidence check and release-gate
  wiring so v1/stable claims stay tied to explicit evidence and blockers.
- Added issue #285's backlog health guard for checking GitHub issue labels and
  milestones before or after marathons.
- Added issue #287's policy-pack smoke evidence so the example API-baseline
  pack is validated through local QAnstitution imports before policy-pack
  claims.
- Added issue #288's alpha launch-readiness aggregator and wired it into the
  release check so public demo, release, policy-pack, backlog, and stability
  boundary evidence cannot silently drift.
- Added issue #289's demo proof matrix so maintainers can rehearse the checkout
  happy path, AI-regression failure proof, policy-pack smoke, launch readiness,
  and backlog health from one wrapper.
- Implemented issue #275's doctor traffic-state health check so
  `entroping doctor` reports missing, readable, and incompatible
  `.entroping/state.db` state through the read-only SQLModel traffic-store
  boundary without creating runtime state.
- Reconciled issue #277's public roadmap drift so completed v0.2 adoption and
  v0.3 CLI/report-first depth are no longer presented as future work, and
  v0.4 integration plus v1.0 stable-core evidence are the clear next frontier.

## 2026-05-31

- Implemented issue #260's CLI adapter split so `cli.main` is now a small
  entrypoint and project, config, architect, execution, and report commands live
  in focused modules with architecture regression coverage.
- Implemented issue #262's traffic-store schema policy with
  `schema_version=1`, future-version fail-closed behavior, and TDS migration
  guidance for `.entroping/state.db`.
- Implemented issue #263's typed dependency-drift run failures with
  `DependencyDriftObservationError` under `RunWorkflowError`.
- Implemented issue #264's Studio typing cleanup by removing `no_type_check`
  from the lazy Textual app boundary while keeping optional imports lazy.
- Implemented issue #265's live-demo guidance cleanup so the smoke script
  distinguishes the HTTP readiness probe from Hurl-backed API assertions and
  gives direct Hurl install guidance.
- Added `docs/meta/OBSIDIAN_VS_GITHUB.md` as the internal maintainer guide
  for choosing between Obsidian, GitHub Issues, GitHub Project, roadmap, ADRs,
  source archives, and context files.
- Added executable documentation governance through `docs/meta/DOCS_GOVERNANCE.md`,
  `scripts/doc_governance_check.sh`, CI PR-body validation, PR template
  documentation-impact declarations, and feature-gate wiring so roadmap and
  docs ownership rules are enforced for both humans and agents.
- Added a public `ROADMAP.md`, linked it from the README and Obsidian index,
  and reframed the progress dashboard around visible public backlog, project
  board, and `v0.1.1-alpha` release sync.
- Made the GitHub Project public as `Entroping Public Roadmap`, enabled
  Discussions, closed completed empty milestones, and seeded 26 open issues
  across five public roadmap milestones.
- Added Dependabot visibility for GitHub Actions and Python dependencies so
  dependency drift becomes issue/PR-backed instead of ad hoc.
- Implemented issue #174's README front-door rewrite so the public overview now leads with the sourced AI-regression problem, two-minute live demo proof, launch assets, and concise alpha boundaries before deep Obsidian/spec inventory.
- Added README guardrail tests that keep the public page demo-first and prevent the old "Available now" knowledge-dump structure from drifting back above the alpha/status sections.
- Implemented issue #176's latency drift slice so drift baselines preserve optional `duration_ms` values and reports warn on material per-test latency regressions without adding CLI flags or response-value snapshots.
- Implemented issue #179's Architect validation UX slice so invalid provider JSON and parser-rejected Hurl print actionable no-write guidance without echoing raw provider or parser streams.
- Ran issue #185's public clean-checkout onboarding smoke from a fresh GitHub clone on macOS 26.5 arm64, proving `uv sync --dev`, Hurl availability, `scripts/live_demo_smoke.sh`, and `scripts/release_check.sh --require-live-demo`.
- Implemented issue #191's public launch preview upgrade with curated terminal, HTML report, and dependency-map PNGs generated from live checkout fixture output and redacted traffic state.
- Added issue #184's good-first-issue walkthrough so new contributors can move from labeled issue selection through `scripts/start_issue.sh`, local validation gates, and PR documentation expectations without reading the whole vault first.
- Added issue #189's downstream GitHub Actions starter workflow with pinned Hurl installation, tagged Entroping install, JUnit/HTML report upload, user docs, and guard tests.
- Added issue #195's Brain provider setup path with optional `api_base` and `api_key_env` agent metadata, LiteLLM/local Qwen/oMLX setup docs, no-provider CI guidance, and docs/code guard tests.
- Added issue #186's package-index release runbook for TestPyPI-first Trusted Publishing, PEP 440 alpha naming, token-free GitHub Actions environments, PyPI publish policy, and yank/new-version rollback.
- Added issue #188's public docs site decision and minimal MkDocs Material scaffold with `mkdocs.yml`, `docs/index.md`, and guard tests, while keeping canonical docs in the existing Markdown tree.
- Added issue #183's distribution recommendation: keep `uv tool install` first, activate PyPI/TestPyPI next, prototype Homebrew after PyPI alpha, defer standalone binaries, and track follow-up implementation issues #223 through #225.
- Added issue #230's zero-config checkout demo entrypoint: `scripts/demo.sh` now provides friendly preflight guidance and delegates to the existing live smoke release gate without expanding the locked CLI surface.
- Added issue #232's first-hour QAnstitution UX: the starter policy, checkout demo policy, and new user guide now share schema-validated status, latency, and request-ID header gates without adding condition syntax.
- Added issue #205's CLI compatibility audit: locked command signatures, deprecated alias policy, exit-code semantics, report artifacts, and Typer/help/documentation guard tests now anchor stable-core command claims.
- Added issue #207's tracked threat model refresh: `docs/technical/THREAT_MODEL.md` now records current stable-core security boundaries, implemented controls, prior validated findings, and residual-risk issue mapping.
- Added issue #198's redaction review report: `entroping report redaction --output md|html` writes counts-only captured-traffic redaction reviews without raw header, query, or body values.
- Added issue #227's optional-extras runtime smoke lane: CI installs all extras and runs `scripts/optional_extras_smoke.py` against LiteLLM, mitmproxy, and Textual boundaries without credentials or live capture.
- Added ADR-0010 for issue #231: v0.3 stays CLI/report-first, Studio remains optional/read-only/report-backed, and mutation workflows remain design-only.
- Added issue #199's Architect remediation guidance: invalid provider JSON and parser-rejected Hurl now print safe retry constraints while preserving no-write behavior and raw-output redaction.
- Added issue #209's open-core boundary audit with a maintainer-facing `OPEN_CORE_BOUNDARIES.md`, entrypoint links, and guard tests that keep the Apache-2.0 local CLI strong while separating paid policy-pack, hosted, audit-history, and service surfaces.
- Added issue #208's bounded performance smoke evidence script for large Hurl suites, parallel runner behavior, report size, and SQLModel traffic-store retention, and wired it into the local release check.
- Added issue #206's cross-platform install smoke matrix with Linux pinned-Hurl, macOS Homebrew-Hurl, Windows doctor-only install proof, and docs that keep platform claims aligned with CI.
- Added issue #201's reusable policy-pack layout, including a runtime-neutral `POLICY_PACK_LAYOUT.md` design note and a loadable `examples/policy-packs/api-baseline/` pack shape.
- Added issue #196's Studio mutation workflow design note, keeping v0.3 Studio read-only while documenting future preview, two-step confirmation, no-raw-secret, rollback, and test gates.
- Added issue #192's read-only Studio applied-gate drilldowns by linking latest-run rule IDs to QAnstitution gate definitions without running Hurl or mutating tests/config.
- Added issue #190's read-only Studio traffic session browser, using read-only SQLModel-backed state access plus existing traffic session and graph compilers to show target/dependency route summaries and safe redaction category counts without starting capture or rendering raw traffic values.
- Added issue #229's Python compatibility policy: package metadata now claims Python 3.12 and 3.13 only, CI runs security regression and optional-extras smoke on both versions, and release docs no longer imply unproven Python 3.14 support.
- Added issue #228's strict public docs automation: pull requests run `mkdocs build --strict`, `main` publishes through GitHub Pages, and public-site docs now describe the active deployment instead of the old deferred scaffold.
- Added issue #259's centralized secret-safety boundary so Brain prompt packaging, Hurl runner output, traffic redaction, and traffic-to-Hurl compilation share one redaction model before provider or report boundaries.
- Added issue #261's `hurlfmt` doctor check so the Hurl executor and Architect parser dependency are reported separately.
- Added issue #267's QAnstitution authoring schema: `docs/technical/qanstitution.schema.json`, VS Code/YAML-language-server mapping, schema drift tests, and docs that keep runtime validation authoritative.
- Added issue #266's public repo surface hygiene by moving the Obsidian vault index to `docs/meta/VAULT_INDEX.md`, removing tracked `.obsidian/` machine state, and documenting why `.context/` remains tracked as maintainer/agent handoff material.
- Added ADR-0011 for issue #202: organization QAnstitution imports must preserve provenance, final-gate behavior, local-first validation, and effective-policy evidence before remote/registry features are implemented.
- Added issue #204's non-GitHub CI provider recipes with GitLab CI, Buildkite, CircleCI, and generic shell guidance while deferring untested native templates from `examples/`.
- Added issue #225's standalone binary distribution decision: defer Nuitka/PyInstaller automation until PyPI alpha, Homebrew tap demand, platform signing/notarization runbooks, and support evidence justify it.
- Added issue #223's manual PyPI/TestPyPI Trusted Publishing workflow with unprivileged artifact build, protected `testpypi`/`pypi` environments, and token-free OIDC publish jobs.
- Added issue #224's Homebrew tap prototype with a PyPI-sdist formula template, required Hurl dependency, local audit/install/test smoke commands, and guardrails that keep optional extras out of the default formula.
- Added issue #194's support-ticket API fixture with a local demo server, OpenAPI spec, Hurl smoke test, QAnstitution gates, README runbook, and real-run report path distinct from checkout.

## 2026-05-30

- Promoted the 2026-05-29 NotebookLM Markdown export as the final current source snapshot for reconciliation, while keeping older Gemini and dated NotebookLM files archival.
- Migrated the Eye traffic state adapter from raw `sqlite3` calls to SQLModel-backed SQLite, preserving the local `.entroping/state.db` runtime state boundary and redaction-first persistence behavior.
- Added a deterministic `scripts/context_pack.sh` agent context launcher, cross-agent control-plane docs, Obsidian/NotebookLM/Gemini knowledge workflow, open-source growth and monetization strategy, and community health files.
- Implemented issue #107's session-prompt context-pack wiring so write sessions point to `scripts/context_pack.sh --mode implementation`, review sessions point to `--mode review`, and `core.session_prompt` has meaningful 100% module coverage.
- Started issue #112's 100% meaningful coverage hardening by adding OpenAPI loader error-path tests, raising `core.openapi_loader` to 100% module coverage without weakening loader behavior.
- Continued issue #112 by covering Hurl validator subprocess startup failures and raising `core.hurl_validator` to 100% module coverage.
- Covered root-level Architect output validation errors, removed an unreachable managed-block marker branch, and raised `brain.output_parser` plus `bridge.merge` to 100% module coverage.
- Covered traffic dependency graph path-normalization edge cases and raised `bridge.traffic_to_graph` to 100% module coverage.
- Covered report writer mismatch, out-of-root path display, no-failure bug guidance, and bug-report write paths, raising `core.report_writer` to 100% module coverage.
- Created focused follow-up coverage issues #119 through #122 and implemented #119's security-focused traffic redactor tests, raising `core.traffic_redactor` to 100% module coverage.
- Implemented #120's Architect prompt builder coverage slice, covering missing-source-context rendering and malformed context paths while raising `brain.prompt_builder` to 100% module coverage.
- Implemented #121's story traceability coverage slice, covering empty-story Markdown and findings-table rendering while raising `bridge.story_traceability` to 100% module coverage.
- Implemented #122's SQLModel traffic store coverage slice, covering retention/list validation and missing inserted-id handling while raising `core.traffic_store` to 100% module coverage.
- Created focused follow-up coverage issues #127 through #130 and implemented #127's Brain safety tests, raising `brain.safety` to 100% module coverage.
- Implemented #128's Hurl metadata model coverage slice, covering malformed metadata keys, duplicate/empty metadata, direct tags access, and path extraction edge cases while raising `models.hurl` to 100% module coverage.
- Implemented #129's Hurl discovery adapter coverage slice, covering direct file roots, duplicate roots, missing/non-Hurl roots, invalid UTF-8, symlink skips, deterministic ordering, and tag-filter normalization while raising `core.hurl_discovery` to 100% module coverage.
- Implemented #130's policy-to-Hurl compiler coverage slice, covering invalid rule/assertion rejection, public gate matching, unsupported fields, and future-condition fallback while raising `bridge.policy_to_hurl` to 100% module coverage.
- Created focused follow-up coverage issues #135 through #138 and implemented #135's gate injector coverage slice, covering source read failures, execution-root validation, no-response handling, no-op matching, missing sources, and response-header insertion while raising `core.gate_injector` to 100% module coverage.
- Implemented #136's Hurl runner coverage slice, covering option validation, binary discovery, subprocess `OSError` mapping, path rejection, worker-count validation, missing worker results, and variable validation while raising `core.hurl_runner` to 100% module coverage.
- Implemented #137's traffic compiler coverage slice, covering session validation, unknown/binary body handling, unsafe Hurl line values, response-less records, unstable golden assertions, WireMock safe stems, redacted headers, and textual/unknown body payloads while raising `bridge.traffic_sessions`, `bridge.traffic_to_hurl`, and `bridge.traffic_to_wiremock` to 100% module coverage.
- Implemented #138's config/env coverage slice, covering QAnstitution load failures, import cycles, writer validation/rollback/race branches, persona path safety, env file decoding/read errors, and duplicate variables while raising `core.config_loader`, `core.config_writer`, and `core.env_loader` to 100% module coverage.
- Implemented #143's OpenAPI compiler/audit coverage slice, covering duplicate generated paths, malformed OpenAPI shapes, parameter fallback rendering, schema examples/defaults, response selection, audit spoofing gaps, and fallback operation IDs while raising `bridge.openapi_to_hurl` and `bridge.openapi_audit` to 100% module coverage.
- Implemented #148's CI gate hardening so GitHub Actions runs `scripts/regression.sh --security`, runs `scripts/audit_quality.sh` as a separate quality-audit job, uploads quality reports, and documents CI-enforced versus local release-owner gates.
- Implemented #150's live-demo Hurl supply-chain hardening by pinning the Linux archive SHA-256 in GitHub Actions and documenting the reviewed checksum bump process.
- Implemented #149's durable artifact-write hardening with a shared `core.safe_write` helper, fsynced temp-file writes, symlink rejection, atomic replacement, no-partial-replacement tests, and adoption by freeze outputs, dependency-map PNGs, drift reports, JSON/JUnit/HTML run reports, and bug reports.
- Implemented #146's deterministic support-module coverage slice, raising `core.dependency_mapper`, `core.drift_report`, `models.traffic`, and `studio.status` to 100% focused coverage with meaningful edge/error tests.
- Implemented #145's Eye proxy/freeze coverage slice, raising `core.traffic_proxy` and `core.freeze` to 100% focused coverage without live mitmproxy sessions or network traffic.
- Implemented #144's Architect workflow coverage slice, raising `brain.architect_build`, `brain.architect_refactor`, and `brain.architect_writer` to 100% focused coverage across merge safety, selected-target enforcement, path validation, and atomic-write failure handling.
- Implemented #157's Brain provider/persona boundary coverage slice, raising `brain.persona_loader` and `brain.litellm_client` to 100% focused coverage without provider or network calls.
- Implemented #159's CLI adapter coverage slice, raising `entroping.cli.main` to 100% focused coverage across doctor/config/architect/watch/run/report helper and error branches.
- Implemented #112's coverage release gate by changing `scripts/audit_quality.sh` to default to `ENTROPING_COVERAGE_FAIL_UNDER=100` and documenting 100% meaningful coverage as the enforced audit default.
- Implemented #106's traceability report CLI so `entroping report traceability --output md` renders local story/test metadata and returns failing exit codes for missing story IDs or conflicting doc links.
- Implemented #109's public trust hardening with a local community-profile audit script, README OpenSSF Scorecard badge, and scheduled/manual Scorecard workflow that avoids PR gating.
- Implemented #110's structured response drift MVP with value-free response fingerprints for status code, selected stable headers, and JSON body shape paths.
- Implemented #108's launch demo asset kit with README links, real checkout smoke terminal frames, a text/SVG HTML report preview, a dependency-map example from redacted traffic, and a concrete growth-plan publish order.
- Fixed #166's launch-doc portability gap by replacing maintainer-local temp paths with an `ENTROPING_DEMO_TMP_BASE` override and adding a guardrail test.
- Implemented #168's configurable source archive path for `scripts/context_pack.sh --mode source`, replacing the hardcoded maintainer-local path with `ENTROPING_SOURCE_ROOT` plus a sibling-folder default.
- Fixed #170's agent workflow docs so Obsidian, Graphify, and prompt examples use portable `<repo-root>` and `<source-archive>` placeholders instead of maintainer-local paths.
- Refreshed #172's README current-status wording so the public overview says active alpha implementation instead of initial scaffold.
- Ran issue #96's formal post-alpha security review and fixed 14 validated candidates across Brain prompt redaction, Hurl subprocess env isolation, symlinked path components, traffic redaction/body limits, OpenAPI generation/audit safety, policy gate compilation, Markdown escaping, Architect generated-file writes, and live demo workdir handling.
- Wrote the consolidated Codex Security scan artifacts under `/tmp/codex-security-scans/Entroping/eb08827323c6_20260530T160200Z`, including discovery, coverage, reconciliation, validation, attack-path, Markdown, and HTML reports.
- Refactored issue #90's `entroping run` orchestration into `core.run_workflow`, preserving reports, drift behavior, exit codes, and LLM-free execution while lowering CLI adapter complexity.
- Implemented issue #91's bridge-level story traceability compiler with missing-story and conflicting-doc-link findings, Markdown rendering, tests, and docs that avoid implying external API sync.
- Hardened local validation scripts to use the repo `src/` path explicitly so audit and regression gates do not depend on editable-install `.pth` state.
- Implemented issue #94's finish-issue workflow with merged-PR and CI verification, clean worktree safety checks, squash-merged branch cleanup, project Done updates, docs, and script tests.
- Implemented issue #93's repeatable local quality audit gate with coverage, Radon complexity/maintainability, Vulture dead-code discovery, ignored report artifacts, and script smoke tests.
- Refreshed issue #92's post-alpha context handoff so `.context/plan.md` and `PROJECT_PROGRESS.md` describe the implemented compiler/runtime surface and current validation queue instead of stale placeholder-era status.
- Fixed issue #95's remaining `architect build` placeholder path so invoking the command without `--new` or `--prompt` now returns actionable supported-mode guidance.
- Fixed issue #97's coverage-artifact hygiene gap by ignoring `.coverage`, `coverage.xml`, and `htmlcov/`, with a regression test proving Git ignores validation coverage output.
- Implemented issue #85's read-only Studio status shell with optional Textual dependency guidance, local latest-run/report/traffic-state inspection, and no-mutation coverage.
- Implemented issue #84's deterministic drift report MVP with `.entroping/drift-baseline.json`, `run --drift-check`, `--report drift`, missing-baseline artifacts, and result/rule-ID comparison.
- Implemented issue #83's bounded parallel Hurl execution so `entroping run --parallel` uses QAnstitution worker limits while preserving per-file safety behavior and deterministic report ordering.
- Implemented issue #82's distribution and install polish with a deterministic package artifact check, source/tag install guidance, and release documentation that keeps package publishing credentials out of the repo.
- Implemented issue #80's optional PNG dependency map export through local Graphviz `dot`, with subprocess-bounded rendering, atomic `reports/dependency-map.png` writes, missing-renderer errors, and secret-safe renderer failure handling.
- Implemented issue #58's license and package metadata blocker with Apache-2.0 core licensing, SPDX package metadata, alpha-safe classifiers, README license status, and ADR-0009 for the open-core boundary.
- Updated the progress dashboard and active implementation context so the remaining public-alpha action is release-gate evidence and tagging, not license selection.

## 2026-05-29

- Replaced the initial thin v4.1 notes with a comprehensive product specification.
- Expanded the technical design around hexagonal architecture, QAnstitution validation, Hurl execution, mitmproxy observation, LiteLLM routing, and reports.
- Added a detailed user guide for new APIs, legacy rescue, existing Hurl adoption, CI, smoke tests, and Studio.
- Added requirements analysis comparing the Gemini evolution, older specs, the slide deck, and the latest v4.1 direction.
- Added QAnstitution reference, command cheat sheet, user flows, use cases, diagrams, and MVP plan.
- Captured the final command namespace and marked older command ideas as deprecated, aliases, or future work.
- Re-ran a multi-pass audit over the old docs and Gemini transcript to recover creator intent around solo-first development, local-first model UX, source-grounded AI, traffic filtering/session stitching, state retention, external business systems, and command-surface conflicts.
- Added `CREATOR_INTENT_AUDIT.md` and `BRAIN_PROVIDER_STRATEGY.md`.
- Completed an additional hard-review pass against Hurl behavior and command contracts.
- Replaced invalid Hurl metadata examples with `# entroping:` comments and removed the invented Hurl validation command in favor of parser-backed validation through `hurlfmt --out json <file>` or an equivalent parser.
- Clarified that `--report` is repeatable for multiple run artifacts and that `report bug` is the only primary reporting subcommand.
- Tightened the MVP agent-routing choice to a small typed in-process router, leaving LangGraph-style orchestration as a later dependency only if complexity justifies it.
- Added PlantUML aliases in the deployment diagram to avoid renderer ambiguity.
- Added the initial Python package scaffold, Typer CLI boundary, Pydantic QAnstitution models, Hurl discovery adapter, tests, uv tooling, and GitHub Actions CI.
- Reworked `README.md` as a GitHub-facing project overview with product pitch, status, quick start, architecture diagrams, repo map, and security rules.
- Organized Markdown docs under `docs/product`, `docs/technical`, `docs/user`, `docs/evolution`, `docs/architecture`, and `docs/meta` while preserving root `README.md` and `00_INDEX.md`.
- Added a glossary, checkout API demo fixture, explicit bridge compiler boundaries, and initial typed condition DSL validation in response to external architecture review.
- Ran a repository-wide Codex Security scan. Current executable scaffold had no high or critical findings; the only reportable issue was a low-severity vulnerable optional proxy dependency tree.
- Raised the optional proxy dependency floor to `mitmproxy>=12.2.3`, refreshed vulnerable transitive packages, and verified the all-extras dependency audit is clean.
- Added project-local `AGENTS.md` so future Codex threads can rehydrate Entroping-specific architecture, runtime, AI, traffic, documentation, and verification rules quickly.
- Refreshed `.context/plan.md` from historical documentation synthesis into the active deterministic-core implementation plan.
- Added `docs/meta/CONTEXT_MANAGEMENT.md` to explain how Codex, Obsidian, `.context`, and optional Graphify output fit together.
- Added `docs/meta/AUTONOMOUS_DEVELOPMENT.md` for the Codex-first development loop, Spec Kit pilot rules, and future OpenCode plus local Qwen/oMLX worker strategy.
- Added `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`, `.github/pull_request_template.md`, and `scripts/feature_gate.sh` to make the feature workflow executable across TDD, regression, architecture, security, multi-agent review, documentation, and commit-readiness gates.
- Added GitHub issue forms, `docs/meta/ISSUE_TRACKING.md`, `docs/meta/TEST_STRATEGY.md`, `docs/meta/PROJECT_PROGRESS.md`, and `scripts/regression.sh` to make bug tracking, regression coverage, test-pyramid expectations, and progress tracking systematic.
- Created the `Alpha: deterministic core` GitHub milestone with six initial feature/docs issues and linked them from `docs/meta/PROJECT_PROGRESS.md`.
- Tightened Obsidian navigation by making `docs/meta/PROJECT_PROGRESS.md` the daily dashboard, reorganizing `00_INDEX.md` into reading tiers, and clarifying context tiers so agents do not treat every Markdown file as equally relevant.
- Created the GitHub Project board `Entroping Alpha`, linked it to the repo, added issues #1-#6, and marked issue #1 as in progress.
- Implemented the issue #1 Phase 1A slice: `entroping init --minimal` now creates a minimal `qanstitution.yaml` and runtime skeleton without overwriting existing policy, `entroping doctor` validates local config health without network calls, and `core.config_loader` loads root-bounded local QAnstitution imports with duplicate/final-gate validation.
- Implemented issue #2's Hurl discovery and metadata slice with pure `# entroping:` comment parsing, recursive `.hurl` discovery, generated-state ignores, tag-filter validation, and focused unit plus adapter tests.
- Added `scripts/start_issue.sh` and a tested prompt renderer for issue-scoped worktrees, dry-run previews, review/write session prompts, and best-effort GitHub issue/project status updates.
- Implemented issue #3's gate matching and temporary Hurl injection slice with shallow request metadata parsing, QAnstitution condition matching, gate-to-Hurl assertion compilation, deterministic execution-copy names, and source-immutability regression coverage.
- Implemented issue #4's deterministic Hurl subprocess runner with argument-array execution, timeout handling, bounded and redacted output, missing-binary handling, non-zero result aggregation, `entroping run` integration, temporary execution-copy cleanup, and focused subprocess/CLI tests.
- Implemented issue #5's report slice with redacted JSON run summaries, CI-consumable JUnit XML, latest-run state under `.entroping/`, `entroping report bug` Markdown generation, and report writer/CLI regression tests.
- Implemented issue #6's alpha quickstart with a tiny local checkout demo server, literal localhost Hurl fixture, README quickstart commands, updated fixture documentation, and demo-server tests.
- Implemented issue #11's first Architect build slice with a pure OpenAPI-to-Hurl compiler, local OpenAPI loader, deterministic `architect build --new` generation under `tests/generated/`, and docs/progress updates.
- Implemented issue #13's environment runner slice with local `envs/<name>.env` loading, process-env overrides for matching keys, Hurl variable passing, env-value output redaction, and fixture docs for generated tests.
- Hardened issue #13's Hurl variable passing in issue #15 by switching to short-lived `--variables-file` temp files so env values do not appear in subprocess argv.
- Implemented issue #17's HTML report slice with escaped dependency-free `reports/run-latest.html` output and repeatable `--report html` support.
- Closed the completed alpha, Architect, runner-usability, and reporting milestones; queued issue #19 as the next live CI proof slice.
- Implemented issue #19's live demo smoke script and GitHub Actions job with pinned Hurl, checksum verification, demo server startup, OpenAPI generation, env loading, real Hurl execution, and report artifact upload.
- Implemented issue #23's OpenAPI depth slice with deterministic path/query/header/cookie parameter rendering, schema example/default/const/enum request-body generation, parameter validation, review-driven Hurl template/non-finite/collision hardening, and a parameterized checkout demo endpoint.
- Implemented issue #25's Architect minimal slice with deterministic OpenAPI coverage audit, Markdown/JSON output, CLI pass/fail behavior, and review-driven hardening for executable Hurl coverage and Markdown validity.
- Implemented issue #29's non-secret config slice with `config list`, `config set`, schema-level unsafe model identifier rejection, effective-policy validation before writes, symlink-safe temporary YAML updates, and focused CLI/domain tests.
- Implemented issue #31's Brain foundation with validated Architect edit models, root-bounded persona loading, secret-checked prompt packaging, lazy LiteLLM adapter, and no provider/network calls in tests.
- Implemented issue #33's Architect output boundary with JSON-to-`ArchitectEditSet` parsing, Architect-owned Hurl staged writes, non-generated overwrite protection, and symlink-safe temporary writes.
- Implemented issue #35's Architect prompt build happy path with Builder persona loading, LiteLLM invocation, structured output parsing, staged Architect-owned Hurl writes, redacted CLI output, and `entroping run` regression isolation.
- Implemented issue #37's parser-backed prompt Hurl validation with a `hurlfmt` subprocess adapter, all-or-nothing pre-write validation, non-echoing validation errors, and Architect path control-character hardening.
- Implemented issue #39's config persona-template creation so `config set` safely creates missing local agent Markdown templates without overwriting existing files or accepting traversal, symlink, URL, non-Markdown, or control-character paths.
- Implemented issue #41's Architect-owned refactor path with safe target glob loading, Builder prompt context packaging, provider JSON parsing, selected-target enforcement, parser-backed Hurl validation, redacted CLI output, and staged writes.
- Implemented issue #43's executable architecture/provider boundary guard with AST-based regression tests for domain/bridge adapter imports, run-core Brain/LiteLLM imports, and direct provider SDK imports.
- Implemented issue #46's CI trigger dedupe so pull requests run once through `pull_request` and branch pushes do not start duplicate workflows unless the push is to `main`.
- Implemented issue #48's pure bridge managed-block Hurl merge primitive for replacing explicit Entroping-managed blocks while preserving manual content outside those blocks.
- Implemented issue #50's managed-block `architect refactor` integration so manual Hurl files can opt into block-level AI maintenance without whole-file overwrite.
- Implemented issue #52's prompt-backed `architect build --strategy merge` path for existing Architect-owned Hurl files and manual managed blocks.
- Implemented issue #54's deterministic repo hygiene slice with tracked local/generated-state rejection, feature-gate integration, optional local hook installation, Obsidian UI state removal from Git, and script tests.
- Added issue #56's alpha release-readiness gate and checklist so public release claims have deterministic local evidence.
- Refreshed the progress dashboard after the release-readiness merge, adding the license/package release blocker and the next Eye capture queue.
- Implemented issue #61's Eye foundation with typed traffic models, pre-persistence redaction, bounded SQLite traffic state, and tests proving secrets are not stored.
- Implemented issue #60's capture-only `watch` workflow with lazy mitmproxy loading, target-scope filtering, redacted flow persistence, CLI wiring, and proxy adapter tests that avoid live network dependence.
- Added issue #59's freeze/map implementation plan and ADR-0008 so filtering, sessioning, traffic-to-Hurl compilation, and graph export are split into implementation issues #66 through #69 before coding begins.
- Implemented issue #66's pure traffic session bridge with static-asset filtering, redacted-record enforcement, binary body text stripping, target/dependency/observed roles, ordering, and unit coverage.
- Implemented issue #67's redacted traffic-to-Hurl compiler with traffic metadata, request rendering, binary body omission, stable golden assertions, and bridge-only tests.
- Implemented issue #68's basic `freeze` CLI workflow with missing-state and unsafe-name errors, parser validation before writes, atomic generated Hurl writes, symlink protection, and redaction regression coverage.
- Implemented issue #69's dependency map export with a pure traffic-to-graph compiler, Mermaid/Markdown/DOT renderers, CLI map wiring, PNG missing-renderer messaging, and redaction/escaping coverage.
- Implemented issue #75's `freeze --mock` path with a pure traffic-to-WireMock compiler, safe mock service selection, staged mapping writes, symlink protection, and no-raw-secret coverage.
- Hardened the live demo CI Hurl install step with bounded retries after a transient GitHub release download 502 caused a flaky PR check.
- Implemented issue #197's reviewed drift baseline workflow with sanitized candidate baseline artifacts, no automatic active-baseline writes, path-safety and redaction regression tests, and user/technical docs for review, diff, and promotion.
- Implemented issue #203's report schema contracts with v1 schema versions for run, drift, and traceability report payloads; checked-in JSON Schema files; compatibility policy docs; and schema contract regression tests.
- Implemented issue #200's GitHub PR annotation integration with `report github-annotations`, JUnit/drift/optional-traceability annotation mapping, workflow-command escaping, redaction, downstream starter workflow updates, and regression tests.
