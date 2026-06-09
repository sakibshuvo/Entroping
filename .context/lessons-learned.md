# Entroping Lessons Learned

## 2026-06-09

- Runtime tool compatibility belongs beside discovery, not inside execution.
  `doctor` can run bounded `--version` subprocesses to prove local tool support,
  while `run` stays focused on deterministic Hurl execution and API behavior.
- Multi-agent orchestration should start as deterministic evidence aggregation,
  not hidden agent autonomy. Summarize sanitized manifests, report conflicts as
  findings, and keep provider calls outside `entroping run`.
- Local AI evidence is still untrusted input when read back. Parse
  `.entroping/agent-runs/*.json` strictly, reject secret-like or malformed
  manifests before rendering, and keep output path conflicts explicit for human
  review.

## 2026-06-05

- AI refactor previews should prove reviewability, not runtime correctness.
  Validate and redact the proposed diff before display, avoid target writes, and
  keep deterministic Hurl execution as the proof step.
- Rerun selectors should accelerate debugging without becoming release proof.
  Select failed source files from sanitized latest-run reports, revalidate paths
  and symlink components before execution, and still require full-suite CI for
  release confidence.
- Gate coverage evidence and runtime results are different contracts. Coverage
  matrices should stay gate-first, local-only, value-free, and clear that they
  prove selection/matching, not Hurl assertion pass/fail.
- Installed CLI templates need package-artifact proof. If a command copies a
  reviewed example from an installed wheel, keep a packaged template under
  `src/entroping/`, assert it matches the reviewed `examples/` artifact, and
  make `scripts/package_check.sh` fail when the wheel or sdist drops it.
- Report artifact manifests should prove local integrity with paths, sizes, and
  checksums only. Do not turn them into signing, attestation, or content
  validation claims unless a separate provenance/signing design exists.
- Traffic artifact preview should reuse the same redacted session compilers and
  path-safety checks as the write path, then stop before Hurl validation,
  artifact writes, and approval manifests. Preview output should stay at
  method, path, status, proposed path, golden status, and redaction-category
  counts.
- Traffic capture safety should be fail-closed before redaction. `watch` scope
  checks need to normalize hosts and default ports, ignore malformed flow URLs
  without persisting request details, and report only counts; redaction remains
  the second layer for records that were explicitly in scope.
- Policy-pack consumer examples should be tested in a temporary consumer layout,
  not by loosening root-bounded import validation. Rewrite only the disposable
  temp import path so the production loader stays local-first and safe.
- Runtime progress logs should be useful without becoming another secret sink.
  Record selected paths, safe metadata, redacted failures, artifact paths, and
  completion status, but omit Hurl variables and raw passing stdout/stderr.

## 2026-06-04

- Context compression is safe only when it is lossless. A decision registry
  should index durable conclusions and point back to ADRs, docs, issues, source
  maps, and exports; it must not replace raw history or become a second backlog.
  Wire retrieval checks into `scripts/doc_governance_check.sh` so agents cannot
  silently orphan source-history anchors.

## 2026-06-02

- Obsidian cleanup should mark ownership and archival status before deleting
  context. Historical product evidence remains useful when the vault clearly
  says which notes explain history and which files define current truth.
- A report writer facade can preserve imports for CLI/tests while separating
  format-specific internals. Keep schema serialization, response
  fingerprinting, rendering, and safe-write error handling distinct so future
  report formats do not pile onto one module.
- Once CLI production modules are split by namespace, the adapter tests should
  follow the same map. A single mega-file makes command behavior harder to
  review even when coverage is strong.
- Optional local tools should fail loudly when required and skip explicitly
  when optional. `scripts/shell_quality.sh` always enforces `bash -n`, but
  ShellCheck remains opportunistic until the repo deliberately installs it in
  local setup or CI.
- Python integration tests can prove Hurl orchestration without a real API by
  placing a fake executable named `hurl` on `PATH`. This keeps the subprocess
  boundary real while avoiding broad monkeypatching of the run workflow.
- Multipart captured bodies are too risky to preserve as text, even after
  field-level redaction. Treat mixed file/form payloads as untrusted binary-ish
  material and persist only a redacted media-type summary with the original
  size metadata.
- Report artifacts are still untrusted inputs when read back into Entroping.
  Generated JUnit XML can be safe to write with stdlib `ElementTree`, but any
  JUnit XML accepted from disk for annotations, review summaries, or CI handoff
  should use a hardened parser and reject DTD/entity constructs before rendering
  findings.

## 2026-06-01

- Do not run environment-mutating gates in parallel. `scripts/audit_quality.sh`
  can resync optional extras in `.venv`, so run `scripts/regression.sh
  --security` after it rather than at the same time or file-walking docs checks
  can observe a half-mutated virtualenv.
- Policy-pack distribution should be a file provenance problem before it is a
  registry problem. Define versioning, attribution, local verification, and
  open-core/premium boundaries first; only then add pack commands, checksums,
  signatures, external repo smoke, or hosted catalog exports.
- Real downstream feedback needs a sanitized intake template before users show
  up. Ask for install path, environment, commands, outcome, friction, and
  short redacted logs; explicitly reject secrets, private URLs, raw traffic,
  proprietary payloads, and customer data.
- Policy-pack provenance should be validated against loaded local
  QAnstitution gates, not trusted as catalog copy. The manifest can prove
  source paths, license, compatibility range, evidence command, gate files, and
  final flags match local files; it still does not prove remote registry
  authenticity or commercial policy review.
- Provider-neutral CI summaries should be artifacts, not integrations. Let
  Entroping write redacted Markdown from local reports, and let downstream CI
  decide whether to upload, print, or post it.
- Stable-core blockers need direct issue links in machine-readable evidence.
  Otherwise future marathon sessions can invent duplicate work or overclaim
  readiness from green local tests instead of following the tracked blocker
  chain.
- Release evidence freshness should be an explicit maintainer check, not a
  default offline gate. Querying GitHub can prove that recorded CI/Page runs are
  stale, but missing `gh` or auth should not block normal ledger validation.
- Release gates should refresh local downstream proof, not only record that a
  harness exists. Keep maintainer-controlled downstream smoke enabled by
  default when Hurl is present, but continue separating it from real downstream
  user feedback in stable-core readiness.
- Local package proof should install the built wheel, not the source checkout.
  Use a temporary venv and temporary project outside the repository, install
  with `uv pip install --offline`, run only public console-script commands, and
  keep PyPI/TestPyPI proof as a separate package-index blocker.

## 2026-05-31

- Public launch language needs an executable claim audit. Unsupported phrases
  like production-ready or guaranteed secure should fail in a script, not depend
  on a tired reviewer noticing them in Markdown.
- Direct dependency license review should be tied to `pyproject.toml`, not a
  one-time memory of package choices. A static reviewed policy file gives agents
  a deterministic reason to stop when adding dependencies.
- Stable-core readiness is a separate artifact from alpha test success. Green
  tests can prove the current implementation, while a readiness report should
  keep repeated releases, package-index proof, compatibility discipline, and
  user feedback visible as blockers.
- Backlog hygiene needs a script because marathon sessions create many issues
  quickly. Labels and milestones are the minimum context that lets fresh agents
  continue without reopening old chat history.
- Launch-readiness checks should execute core proof scripts in the release gate,
  not only look for their files. Static markers catch documentation drift, but
  release checks should run the fast local evidence when it is deterministic.
- Policy-pack consumer examples are easiest to prove by vendoring the pack into
  a temporary consumer root and loading a normal `qanstitution.yaml`. That keeps
  root-bounded import semantics intact while still testing copyable examples.
- The root README is a public product front door, not the full Obsidian vault index. Lead with the problem, promise, and executable demo proof; keep phase inventories, source maps, and agent context lower in the document or in linked docs.
- Run mypy through the repo target, not isolated test-file imports. `uv run mypy tests/<file>.py` can analyze the installed package and report missing `py.typed`, while `uv run mypy src tests/<file>.py` or the normal feature gate checks the local source tree correctly.
- CLI help-output tests should normalize Rich/Typer rendering. Pin `COLUMNS` and strip ANSI escape sequences before asserting command or flag names, otherwise CI terminal rendering can truncate or style option names while local tests still pass.
- Latency drift should be conservative and baseline-backed. Compare only sanitized `duration_ms` values from reviewed run reports, require both absolute and percentage regression thresholds, and report warnings rather than treating tiny local timing noise as product truth.
- Architect error UX should be actionable without becoming a data leak. Print short validation categories and no-write guidance, but continue hiding raw provider output and parser streams.
- Redaction review reports should be category/count artifacts, not sampled traffic dumps. Even already-redacted state can contain sensitive business structure, so the default review should prove coverage without rendering URLs, header values, body values, or `[REDACTED]` placeholders.
- Optional dependency audits and optional runtime smokes are different gates. Keep the all-extras dependency audit in the security gate, and keep adapter boot checks in a separate CI job so default regression remains lightweight.
- TUI polish should trail durable artifacts. Studio can make local inspection nicer, but the product truth needs to land first in CLI commands, sanitized reports, and CI-friendly files that agents and users can review without a custom UI.
- Architect remediation hints should be constraints, not copied provider text. Tell users how to retry safely, but keep raw model output and parser streams out of the terminal.
- Open-core monetization should distinguish local proof from team aggregation. Keep local runtime gates, reports, and PR annotations core; monetize hosted history, organization reporting, curated policy depth, and services.
- Performance smokes should produce reviewable release evidence, not noisy microbenchmarks. Use bounded synthetic workloads, generous thresholds, fake Hurl for network-free runner proof, and ignored JSON artifacts that a release owner can inspect.
- Cross-platform install claims need explicit non-claims. It is better to prove Windows CLI installation and `doctor` guidance than imply Hurl-backed Windows execution before the Windows Hurl path is reviewed.
- Policy packs should start as ordinary QAnstitution imports plus metadata, not a second policy system. Prove the directory shape and examples first; add registry, remote-fetch, or manifest validation only after a focused follow-up issue.
- Studio mutation must be preview-first, confirmation-gated, and reversible before code. Keep Textual as an adapter over existing CLI/core use cases, not a direct writer or runner.
- Studio drilldowns should explain existing artifacts, not create new truth. Applied-gate views should derive from latest-run report rule IDs plus loaded QAnstitution definitions while leaving Hurl execution and report generation in the CLI path.
- Studio traffic inspection should use a read-only database path. Reusing a write-capable store initializer for UI browsing can create or migrate `.entroping/state.db`; add a separate read-only SQLModel query path and keep raw URLs, headers, bodies, cookies, tokens, and secrets out of TUI rows.
- Runtime compatibility claims should be CI-proven and capped when unproven. If package metadata says Python 3.12 and 3.13, run regression and optional-extras smoke on both versions, keep 3.12 as the syntax/type-checking floor, and avoid implying Python 3.14 until a future lane proves it.

## 2026-05-30

- Security-sensitive path checks need component-level symlink rejection, not only final-path checks. Env loading, report writes, drift reports, state files, and generated Hurl writes all need to reject symlinked ancestors before resolving.
- Drift baseline workflows should emit a sanitized candidate artifact and require deliberate promotion. Copying raw latest-run state into an active baseline blurs review evidence with approval and can retain output fields that drift comparison does not need.
- Hurl subprocess isolation needs an explicit environment allowlist. Passing variables through Hurl's variables file is not enough if the child process inherits unrelated parent secrets from CI or the local shell.
- Treat OpenAPI as active Hurl input, not passive documentation. Parameter names and JSON object keys can become Hurl interpolation syntax unless fallbacks and keys are validated before rendering.
- Markdown output is still a report boundary. Escape HTML metacharacters in addition to table pipes/newlines before metadata or spec values can be viewed in Obsidian, CI artifacts, or local renderers.
- Demo scripts should never clean user-selected directories. If a script accepts a workdir from the environment, require a symlink-free, empty directory and fail closed instead of trying to be helpful with deletion.
- Use Apache-2.0 for the public Entroping Core to maximize adoption and enterprise comfort while keeping paid hosted Brain, enterprise workflows, model weights, policy packs, support, and cloud services as separate commercial surfaces.
- Licensing is release metadata, not a vibe. Keep `LICENSE`, `pyproject.toml`, README status, progress docs, and release checks aligned so a public alpha is not accidentally shipped as an unlicensed repository.
- Distribution claims need executable evidence. Build and inspect wheel/sdist artifacts locally, keep `dist/` ignored, and keep PyPI/TestPyPI credentials out of the repo until publishing automation is explicitly designed.
- Homebrew should trail the package-index path. Keep the tap formula as a template until a PyPI alpha exists, generate explicit Python resource stanzas from the published sdist, depend on Hurl, and keep optional feature trees out of the default formula.
- Demo fixtures should vary endpoint shapes and governance rules. A second fixture needs different methods, headers, query/path parameters, and gates so smoke evidence does not accidentally prove only the checkout happy path.
- Parallel Hurl execution should change scheduling only, not report semantics. Bound worker count from QAnstitution, keep per-file subprocess isolation, and reorder completed futures back to input order before reports are built.
- Drift reports should compare structured Entroping-owned state first. Response drift belongs in sanitized run-report fingerprints, not raw full-body snapshots; store status, selected stable headers, and body shape instead of values.
- Studio should begin as a read-only local-state adapter. Require optional UI dependencies explicitly, render useful terminal status first, and prove the command does not mutate `.entroping`, reports, tests, or config.
- Optional renderer integrations should stay adapter-local and subprocess-bounded. Feed them already-redacted compiler output, write ignored artifacts atomically, and do not echo renderer stderr because external tools may replay source graph content.
- Coverage runs that invoke nested local tools should not rely only on editable-install `.pth` metadata. Set an explicit repo-local `PYTHONPATH` for deterministic audit scripts so subprocesses can import `src/entroping` even when local virtualenv metadata is flaky.
- Squash merges break normal `git branch -d` ancestry checks even when a PR is genuinely merged. Cleanup should verify the GitHub PR and CI state first, then use a scripted local branch deletion path instead of relying on chat memory.
- Traceability should start as a local compiler over committed metadata. Do not add Jira, Notion, Linear, or monday.com clients until the local story/test report and conflict rules are stable.
- High-risk CLI commands should delegate orchestration to core use cases before adding more flags. Keep Typer functions focused on option normalization, user-facing output, and exit-code mapping.

## 2026-05-29

- The final v4.1 product is Hurl-native. Bruno is useful historical context and can still act as a client through the proxy, but it is not the source format for MVP tests.
- The most important product distinction is runtime governance, not generic AI test generation.
- The command namespace must stay small: `init`, `doctor`, `config`, `architect build/refactor/audit`, `watch`, `freeze`, `map`, `studio`, `run`, and `report bug`.
- `qanstitution.yaml` should contain deterministic law. Agent persona files should remain Markdown.
- The Eye lifecycle from v3 is still required in v4.1: traffic capture, freeze, golden masters, mocks, and dependency maps.
- Hurl is the enforcement boundary. Python orchestrates but must not replace Hurl as the API execution engine.
- Reports need both machine formats and human formats: JUnit for CI, JSON for tooling, HTML/Markdown for review and bug handoff.
- Machine-readable reports need explicit schema versions before external dashboards or PR annotation tools depend on them. Additive optional fields can remain in v1, but required-field, rename, removal, or type changes need a new schema version and migration note.
- GitHub PR annotations should be emitted as local workflow commands, not GitHub API mutations. This keeps downstream CI token-light, preserves local-first behavior, and lets existing report artifacts remain the durable source of truth.
- The creator intent is solo-first but not toy-grade: use `uv` and source debugging now, defer binary packaging and Cloud until the core governance loop is real.
- The Brain must be local-first and LiteLLM-routed; do not depend on external provider CLIs, and do not put API keys in plaintext config.
- `entroping run` must remain deterministic and should not call the LLM; AI-generated Breaker work must become committed Hurl tests before it can govern CI.
- Business truth may live in Jira, Notion, Linear, or monday.com. Entroping should link through metadata and optionally cache external requirements into local Markdown.
- Entroping metadata belongs in Hurl comments such as `# entroping: tags=...`; do not add custom `tags` or `meta` keys to Hurl `[Options]`.
- Do not document unsupported Hurl validation commands. Use parser-backed validation, with `hurlfmt --out json <file>` as the safe non-executing example.
- Prefer a small typed agent router for the MVP before adopting orchestration dependencies.
- Project-local `AGENTS.md` is the fastest way to carry repo-specific Codex behavior across new threads. It should stay concise, stricter than generic docs, and focused on boundaries that are easy for an agent to violate.
- A dependency audit must include optional extras before release. The default install can be clean while `uv run --all-extras --with pip-audit pip-audit --progress-spinner off` still catches future runtime surfaces such as mitmproxy.
- Graphify should remain optional generated context. Keep `graphify-out/` ignored, and treat curated Markdown, ADRs, and `.context/` as the durable source of truth.
- The autonomous workflow should stay Codex-first until OpenCode and local Qwen/oMLX have proven reliable on bounded read-only or review tasks. Cheap agents can draft and critique, but verified commits remain the product boundary.
- A multi-agent workflow needs executable gates, not only principles. Keep one parent integrator, require local file evidence for claims, run deterministic checks before commit, and update context files so future threads inherit the decision trail.
- GitHub Issues should track individual bugs, feature slices, and regressions; Obsidian should track phase-level progress, roadmap movement, ADRs, and durable lessons. Duplicating every issue into Markdown creates stale context.
- Obsidian improves context preservation only when notes are tiered and curated. Keep `PROJECT_PROGRESS` as the daily dashboard, use `00_INDEX` as the map, and leave product-history files as reference material instead of default agent input.
- Quote QAnstitution condition strings in YAML, especially `condition: "true"`. Unquoted `true` is parsed as a boolean before Pydantic validation and should not be treated as the DSL expression.
- Phase 1A local QAnstitution imports are intentionally root-bounded to avoid arbitrary file reads from attacker-controlled YAML. Broader local trust roots need an explicit design before implementation.
- Hurl discovery should skip generated and local state such as `.entroping/`, reports, caches, virtualenvs, dependency folders, and hidden directories by default so future `run` work does not accidentally govern stale artifacts.
- Multi-session development should start from GitHub Issues and isolated worktrees, not from a shared checkout. Use `scripts/start_issue.sh --dry-run` to validate the branch, worktree path, and prompt before launching several agents.
- Gate matching for method, path, and URL conditions needs shallow Hurl request parsing, not Python HTTP execution and not custom Hurl options. Runtime injection should annotate temporary copies with rule IDs and enforcement levels so runner/report layers can keep block and warn gates distinct.
- Path hardening checks must inspect symlink status before resolving a path. Calling `Path.resolve()` first can hide that the original user-controlled path was a symlink.
- Hurl runner tests should stub the subprocess boundary, not the product behavior. The core proof is the argument array, `shell=False`, timeout conversion, bounded/redacted captured output, and deterministic suite exit code.
- Reports need two destinations: user-facing artifacts under `reports/` and sanitized latest-run state under `.entroping/` so `report bug` can work without rerunning Hurl.
- Fail-fast reports should map executed Hurl results back to temporary execution copies by resolved path, not by selected-list length. A shorter result list is valid only for fail-fast; normal mismatches should remain hard errors.
- Gate-injection explanations should consume effective QAnstitution evidence and selected Hurl metadata directly. They must not call Hurl, write execution copies, or infer source policy paths from the flattened runtime policy.
- A first-run demo must not depend on future env-file loading. Use literal localhost URLs plus a tiny local server until `--env` grows real variable injection.
- OpenAPI is an attacker-controlled boundary. Reject control characters in generated metadata/request lines and reject unsupported JSONPath field names instead of emitting malformed or injectable Hurl.
- Env loading should be intentionally narrow: read only `envs/<name>.env`, allow process overrides only for keys declared in that file, pass values to Hurl through a variables file, and redact loaded values from outputs.
- Avoid putting env-derived Hurl values directly in subprocess argv. Use Hurl's variables-file path instead, delete the temp file promptly, and keep redaction as a separate defense.
- Human-facing reports still need output escaping. Treat Hurl stdout/stderr, paths, environment names, and rule IDs as untrusted when rendering HTML.
- Live demo proof belongs in a separate CI job after fast checks. Pin external CLIs, verify checksums, keep generated artifacts out of Git, and upload reports as CI artifacts instead.
- OpenAPI parameters should compile through explicit rendering rules, not string concatenation. Use Hurl variables as the fallback, URL-encode literal path/query/cookie values, validate header/cookie names as HTTP tokens, and keep examples/defaults source-grounded.
- OpenAPI examples and defaults can become active Hurl syntax if emitted blindly. Reject Hurl template delimiters in literal source values and reject non-finite numbers before rendering generated `.hurl` files.
- Rich console rendering can hard-wrap JSON and corrupt machine-readable output. Use raw stdout for `--output json` style CLI payloads, and reserve Rich rendering for human Markdown/status text.
- Agent model IDs are routing metadata, not credentials. Validate them at the QAnstitution schema boundary, reject key-shaped values, and never add provider API keys to `qanstitution.yaml`.
- Config writers should validate the existing document before mutation and the updated document before write, so a convenience command cannot silently repair or worsen unrelated invalid policy.
- Config writers need effective-policy validation, not only root-schema validation. If imports, final-gate merge rules, or cycles make `doctor` fail, `config set` must fail before writing too.
- Avoid predictable temp paths for config writes. Use exclusive random same-directory temp files and validate the temp file before replacing the real config so attacker-controlled symlinks cannot receive config content.
- Brain implementation can advance safely before user-facing AI commands by making persona loading, prompt packaging, provider invocation, and structured output validation separate modules with tests.
- Treat persona Markdown and prompt context as untrusted inputs: keep paths root-bounded, reject symlinks, cap file size, and scan for token-shaped secrets before any provider call.
- Convenience commands that write config pointers should also create safe local target templates or fail before config mutation; otherwise the next command can still fail even though setup appeared successful.
- LiteLLM belongs behind a lazy adapter with injectable completion functions so normal development and regression tests do not need provider credentials or network access.
- Raw model output should enter the system through a parser boundary, not a writer. Parse JSON, validate with Pydantic, then let the filesystem adapter enforce ownership and path safety.
- Architect writes should mark generated files with `# entroping: source=architect` and refuse to overwrite manual or non-Architect Hurl files until a merge/refactor mode explicitly owns that behavior.
- Refactor commands should treat target globs as untrusted input: reject traversal, absolute paths, control characters, symlinks, non-Hurl files, and provider edits outside the selected target set before any write.
- Architecture rules should be executable tests, not only prose. Use AST import-boundary checks to catch domain-to-adapter drift, run-core Brain imports, and direct provider SDK imports before review.
- PR CI should run on `pull_request` plus `push` to `main`; broad branch push triggers double the feedback noise during multi-session work without increasing coverage.
- Manual-file-preserving AI maintenance needs explicit ownership markers. Whole-file overwrite is safe only for Architect-owned files; manual files should opt into block-level replacement with deterministic merge errors.
- Refactor writes need a separate prepared-write path from generation writes: generated files may create Architect-owned outputs, while refactors should require selected existing targets and preserve manual ownership mode.
- Prompt-backed build merge should not create missing targets; use plain prompt build for new files and merge strategy only when an existing Hurl file owns the destination.
- Treat model summaries, warnings, and provider errors as untrusted CLI output. Redact token-shaped values and print without Rich markup interpretation before showing them to users.
- Parser-backed validation errors for model-generated Hurl should identify the generated file path but not echo raw parser stderr/stdout, because those streams can include provider-supplied snippets.
- Prompt rules are not enough for multi-session development. Any repeatable decision about tracked machine state, generated output, cache files, or local hook setup should become a script, test, or CI gate.
- Release claims need a higher bar than feature completion. Keep a dedicated release checklist that names required evidence and known-not-built boundaries so public alpha messaging stays accurate.
- Eye capture must be security-first: model captured traffic as untrusted input, redact before persistence, refuse unredacted state writes, and prove traffic modules cannot import Brain or provider code.
- Optional proxy dependencies should be lazy-loaded at the command boundary. A default install must explain `uv sync --extra proxy` instead of failing at import time, and adapter tests should use fake flow objects instead of requiring a live mitmproxy process.
- Freeze/map work needs a compiler boundary before code. Keep filtering/sessioning, traffic-to-Hurl, graph export, and CLI/file writes separate so the Eye does not collapse into one adapter-heavy module.
- Session candidates should be built from redacted traffic only. Strip binary body text and label target/dependency roles in a pure bridge module before any freeze/map compiler writes artifacts.
- Traffic-to-Hurl generation should avoid raw response-body replay. Use observed request data plus stable response assertions, and skip token-like, ID-like, timestamp-like, redacted, binary, or templated values.
- Freeze writes must validate Hurl before touching the target path and use random same-directory temp files plus symlink checks before replacement. Missing traffic state should fail without creating `.entroping/state.db`.
- Dependency maps are export artifacts, not raw traffic dumps. Ignore query strings, template volatile path segments, aggregate only redacted records, and escape every host/method/path label independently for Mermaid, Markdown, and DOT.
- WireMock generation should match dependencies by a narrow safe service selector and avoid request-header/body matching in the MVP. Method plus URL path and redacted response payloads give useful mocks without replaying captured secrets.
- Release smoke jobs that download pinned external binaries still need bounded retries. Keep checksum verification strict, but do not let a single transient 5xx from a release host fail an otherwise valid PR.
- SQLModel is the typed persistence layer, not a replacement for SQLite. Keep `.entroping/state.db` as local-first runtime state, and use SQLModel where relational state needs clearer schema, tests, and future migration paths.
- Local SQLite state needs its own schema contract, not only SQLModel classes.
  Store a schema version in the database, fail closed on future versions, and
  require a reviewed migration before accepting explicit older versions.
- Large Typer apps should not stay in one module after the command surface
  stabilizes. Split command adapters by namespace while keeping `cli.main` as
  the small registration entrypoint and preserving compatibility tests.
- Optional UI adapters can stay lazy without disabling type checks. Use a narrow
  runtime protocol and focused mypy coverage at the optional dependency
  boundary.
- Demo scripts may use Python HTTP calls for fixture readiness, but API
  correctness claims must remain tied to Entroping plus Hurl execution.
- Multi-agent scale needs deterministic context packs and one parent integrator. Use helper agents for bounded evidence and review, but promote durable decisions into issues, ADRs, docs, tests, or scripts before implementation follows them.
- Pydantic and mypy are complementary gates: Pydantic validates runtime data at boundaries, while mypy enforces static type consistency before runtime.
- Launch assets should be generated from real product paths but committed as small, reviewable text/SVG artifacts. Keep bulky terminal recordings, screenshots, generated reports, and traffic state out of Git unless each asset is deliberately curated.
- Public launch commands must not bake in maintainer-local paths. Use portable defaults with environment overrides, then test the public docs for path leaks.
- Agent handoff scripts should prefer repository-relative defaults plus environment overrides over hardcoded workstation paths.
- Agent workflow docs should be portable even when the maintainer has a known local checkout. Use placeholders in committed docs and keep machine-specific paths in local prompts or environment variables.
- Public README status language needs the same regression protection as code: stale "scaffold" wording can quietly undercut a real alpha.
- Public docs deployment needs two gates: PR CI should build the MkDocs site strictly, while the Pages workflow should publish only from `main` after the same strict build.
- Organization governance should compile into one effective local QAnstitution. Preserve provenance and final-gate behavior before adding remote policy registries, caches, or approval workflows.
- Do not ship native CI-provider templates just because the shell recipe is portable. Mark GitLab, Buildkite, and CircleCI templates as deferred until their actual runners prove install, Hurl checksum, Entroping run, and artifact behavior.
- Standalone binaries are a support and security commitment, not just a convenience feature. Require proven package-manager demand, signing/notarization ownership, and native dependency update plans before adding Nuitka or PyInstaller automation.
- Package-index publishing should split build and publish privileges. Build artifacts with read-only contents permission, then expose OIDC only in protected environment publish jobs after reviewer approval.
- Policy-pack verification must not bake in the example pack name or folder
  shape. Vendor arbitrary packs into a temporary local project under their own
  directory name, rewrite only the disposable consumer import path, and validate
  manifest attribution plus local consumer gates before advertising the pack.
- Do not run environment-mutating gates such as `scripts/audit_quality.sh` in
  parallel with `scripts/regression.sh --security`; both can touch `.venv`, so
  run them sequentially before treating a failure as product evidence.
- Report-only filesystem discovery can surface malformed local inputs as
  findings instead of crashing, but unsafe symlinked paths should still be
  skipped and reported before file reads.
