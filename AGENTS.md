# Entroping Codex Instructions

These instructions extend the global Codex rules for this repository. If a rule conflicts with product docs, prefer the stricter safety or architecture rule and update the docs before implementation.

## Priorities

- Treat security, quality, maintainability, reliability, and architectural consistency as release gates.
- Keep the product thesis intact: AI may propose tests, but deterministic Hurl execution and QAnstitution governance decide pass or fail.
- Prefer a narrow working vertical slice over broad placeholder implementation.
- Preserve the Obsidian knowledge base as a durable product-evolution record.

## Architecture Rules

- Follow the hexagonal architecture documented in `docs/technical/TDS.md`.
- Domain code in `src/entroping/models/` and `src/entroping/bridge/` must not import adapters from `cli`, `core`, `brain`, or `studio`.
- Keep bridge compiler responsibilities separate:
  - `openapi_to_hurl/` for OpenAPI translation, with bounded schema,
    validation, parameter, model, and compiler modules.
  - `traffic_to_hurl.py` for redacted traffic translation.
  - `traffic_to_wiremock.py` for redacted dependency mock translation.
  - `traffic_to_graph.py` for redacted dependency map translation.
  - `policy_to_hurl.py` for QAnstitution gate translation.
  - `story_traceability.py` for external business-truth linkage.
  - `merge.py` for preserving manual Hurl edits.
- Add shared abstractions only when they reduce real complexity or match an established local boundary.

## Runtime Rules

- Do not execute API tests through Python HTTP clients as a substitute for Hurl.
- Hurl execution must go through subprocess APIs with argument arrays, timeouts, bounded output capture, cleanup, and secret redaction.
- `entroping run` must remain deterministic and LLM-free.
- Do not mutate source `.hurl` files during `run`; use temporary execution copies for injected gates.
- Validate attacker-controlled inputs at boundaries: CLI args, globs, paths, YAML policy, Hurl metadata comments, OpenAPI files, captured traffic, and LLM outputs.

## AI and Traffic Rules

- Use LiteLLM for model access; do not add direct OpenAI, Anthropic, Gemini, or provider-specific SDK calls unless the architecture docs are changed first.
- Repo-local development helpers may call direct provider APIs only as bounded,
  ignored artifact generators for external review or patch proposals; this does
  not replace Entroping's LiteLLM product boundary.
- Separate prompt construction, provider invocation, structured response validation, and business logic.
- Never send secrets, raw captured traffic, credentials, tokens, cookies, or unredacted request/response bodies to model providers.
- mitmproxy capture must redact sensitive headers, cookies, token-like fields, and body content before persistence or export.
- Captured traffic state belongs under `.entroping/` and must stay out of Git.

## Documentation and Context

- Follow `docs/meta/DOCS_GOVERNANCE.md` before changing roadmap, progress, product, technical, user, ADR, or context docs.
- Keep `README.md`, `docs/meta/VAULT_INDEX.md`, `.context/`, and `docs/product/MVP_PLAN.md` aligned with the current implementation milestone.
- Use `docs/meta/DECISION_REGISTRY.yaml` as the durable decision lookup layer before reading broad historical material; registry summaries point to sources and do not replace them.
- Keep `docs/meta/PROJECT_PROGRESS.md` current after meaningful feature, bug, or roadmap changes.
- Add or update an ADR when a product or architecture decision should survive context resets.
- Use `.context/plan.md` for the active implementation plan, `.context/changelog.md` for concise changes, and `.context/lessons-learned.md` for durable pitfalls and decisions.
- Keep Obsidian workspace state and generated local context output out of Git unless it is intentionally curated Markdown.
- Use GitHub Issues as the canonical tracker for individual bugs, feature slices, and regressions.
- Keep `.codex/` and installed skills/plugins user-local. Project behavior belongs in this file, tracked scripts, issue prompts, docs, and CI.

## Autonomous Development Workflow

- Follow `docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md` for risk-tiered autonomous implementation, Spec Kit pilots, and future OpenCode/oMLX loops.
- Follow `docs/meta/AGENT_CONTROL_PLANE.md` for cross-agent coordination across Codex, Claude Code, OpenCode, Gemini, NotebookLM, and local Qwen.
- Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` for every non-trivial feature, defect fix, or architecture change.
- Use `scripts/context_pack.sh --mode implementation` to create deterministic context for a new coding session instead of relying on chat memory.
- Use `uv run python scripts/agent_toolchain.py --mode implementation --format json`
  to inspect local CLI availability and safe-use policy before claiming a tool
  is available. The preflight uses the `entroping.agent-toolchain.v1` schema,
  performs PATH lookup only, and must not run scanners, read provider config,
  inspect local secret stores, or make network calls.
- Codex owns factory design and final integration for Tier B/Tier C work.
- OpenCode/DeepSeek may independently implement and merge only Tier A autonomous lanes documented in `docs/meta/AGENT_CONTROL_PLANE.md` after issue-scoped worktrees, deterministic gates, GitHub CI, and finish cleanup prove scope.
- Tier B and Tier C remain human/Codex-reviewed.
- Use OpenCode or local Qwen only as bounded workers, reviewers, or documented Tier A autonomous workers until their outputs have been validated against local files, tests, and CI.
- Do not let any unattended agent push to `main` outside a documented Tier A autonomous lane, and never accept generated code without deterministic verification.
- Spec Kit may be piloted for one feature at a time on a clean branch; do not let generated templates replace existing curated docs without review.

## Local CLI Toolchain Rules

- `safe_default` tools may be used during normal agent work for targeted local
  discovery, structured inspection, diff review, and measurement. Prefer these
  before loading broad context: `fd`, `sg`/ast-grep, `delta`, `difft`, `jq`,
  `yq`, `tokei`, `scc`, `dust`, `git-sizer`, `hyperfine`, `watchexec`,
  `jless`, `fx`, and `jc`.
- `guarded_local_only` tools must run through a repo gate or explicit focused
  command and must not scan home directories, provider config, raw traffic,
  `.entroping` artifacts, local secret stores, or unrelated checkouts. This
  includes `actionlint`, `zizmor`, `gitleaks`, `detect-secrets`,
  `osv-scanner`, `pip-audit`, `lychee`, `markdownlint-cli2`, `shfmt`,
  `shellcheck`, `hadolint`, and Graphviz `dot`.
- `manual_explicit` tools must not run automatically. Use `act`,
  `trufflehog`, `semgrep`, `trivy`, `syft`, and `grype` only with explicit
  human/Codex approval, narrow repo scope, and a documented reason because they
  can execute workflow code, contact services, download databases, or traverse
  broad sensitive surfaces.
- Cheap workers may report that a manual or guarded tool looks useful, but they
  must not run it unless the issue packet or parent integrator explicitly
  authorizes that exact command and scope.

## Verification

- Choose the proportional verification lane from `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`
  before final review, and declare it in the PR body as `Verification lane: <lane>`.
- For `tiny-docs`, run `scripts/doc_governance_check.sh`.
- For `docs-guardrail`, run focused docs/workflow tests such as
  `uv run pytest tests/test_agent_workflow_docs.py -q` plus
  `scripts/doc_governance_check.sh`.
- For `tests-only`, run the focused pytest slice for the touched tests.
- For `normal-code`, run `scripts/feature_gate.sh` or `scripts/regression.sh`.
- For security-sensitive, dependency, subprocess, path, YAML, report, traffic,
  proxy, redaction, provider, secret, or runtime safety work, use
  `security-runtime` and run `scripts/feature_gate.sh --security` or
  `scripts/regression.sh --security`.
- For release, CI, architecture, quality, or delivery guardrail work, use
  `release-ci-architecture` and run `scripts/regression.sh --security` plus
  `scripts/audit_quality.sh`.
- PR CI runs the broader regression matrix; local gates should match the lane
  without using maximum-assurance checks for every tiny prompt/doc edit.
- `scripts/feature_gate.sh` runs `scripts/repo_hygiene.sh`; do not bypass it when local state or generated files are involved.
- Optional local hooks can be installed with `scripts/install_hooks.sh`, but hooks are convenience only and do not replace CI or the feature gate.
- Review `git diff` before staging or committing.
- Do not commit `.DS_Store`, `.venv/`, `.entroping/`, generated reports, local env files, generated local context output, or Obsidian workspace/cache/plugin state.
