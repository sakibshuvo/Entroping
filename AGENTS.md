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
  - `openapi_to_hurl.py` for OpenAPI translation.
  - `traffic_to_hurl.py` for redacted traffic translation.
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
- Separate prompt construction, provider invocation, structured response validation, and business logic.
- Never send secrets, raw captured traffic, credentials, tokens, cookies, or unredacted request/response bodies to model providers.
- mitmproxy capture must redact sensitive headers, cookies, token-like fields, and body content before persistence or export.
- Captured traffic state belongs under `.entroping/` and must stay out of Git.

## Documentation and Context

- Keep `README.md`, `00_INDEX.md`, `.context/`, and `docs/product/MVP_PLAN.md` aligned with the current implementation milestone.
- Keep `docs/meta/PROJECT_PROGRESS.md` current after meaningful feature, bug, or roadmap changes.
- Add or update an ADR when a product or architecture decision should survive context resets.
- Use `.context/plan.md` for the active implementation plan, `.context/changelog.md` for concise changes, and `.context/lessons-learned.md` for durable pitfalls and decisions.
- Keep Obsidian/Graphify generated state out of Git unless it is intentionally curated Markdown.
- Use GitHub Issues as the canonical tracker for individual bugs, feature slices, and regressions.
- Keep `.codex/` and installed skills/plugins user-local. Project behavior belongs in this file, tracked scripts, issue prompts, docs, and CI.

## Autonomous Development Workflow

- Follow `docs/meta/AUTONOMOUS_DEVELOPMENT.md` for Codex-first implementation, Spec Kit pilots, and future OpenCode/oMLX loops.
- Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` for every non-trivial feature, defect fix, or architecture change.
- Codex is the final implementer and gatekeeper for now.
- Use OpenCode or local Qwen only as bounded workers or reviewers until their outputs have been validated against local files, tests, and CI.
- Do not let any unattended agent push to `main` or accept generated code without deterministic verification.
- Spec Kit may be piloted for one feature at a time on a clean branch; do not let generated templates replace existing curated docs without review.

## Verification

- For normal work, run `scripts/feature_gate.sh`.
- For regression proof, run `scripts/regression.sh`.
- For security-sensitive or dependency work, run `scripts/feature_gate.sh --security`.
- For docs-only changes, `scripts/check.sh` is acceptable when no source, dependency, subprocess, or runtime boundary changed.
- `scripts/feature_gate.sh` runs `scripts/repo_hygiene.sh`; do not bypass it when local state or generated files are involved.
- Optional local hooks can be installed with `scripts/install_hooks.sh`, but hooks are convenience only and do not replace CI or the feature gate.
- Review `git diff` before staging or committing.
- Do not commit `.DS_Store`, `.venv/`, `.entroping/`, generated reports, local env files, Graphify output, or Obsidian workspace/cache/plugin state.
