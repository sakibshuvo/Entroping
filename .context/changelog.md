# Entroping Changelog

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
