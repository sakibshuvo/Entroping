# Entroping Lessons Learned

## 2026-05-29

- The final v4.1 product is Hurl-native. Bruno is useful historical context and can still act as a client through the proxy, but it is not the source format for MVP tests.
- The most important product distinction is runtime governance, not generic AI test generation.
- The command namespace must stay small: `init`, `doctor`, `config`, `architect build/refactor/audit`, `watch`, `freeze`, `map`, `studio`, `run`, and `report bug`.
- `qanstitution.yaml` should contain deterministic law. Agent persona files should remain Markdown.
- The Eye lifecycle from v3 is still required in v4.1: traffic capture, freeze, golden masters, mocks, and dependency maps.
- Hurl is the enforcement boundary. Python orchestrates but must not replace Hurl as the API execution engine.
- Reports need both machine formats and human formats: JUnit for CI, JSON for tooling, HTML/Markdown for review and bug handoff.
- The creator intent is solo-first but not toy-grade: use `uv` and source debugging now, defer binary packaging and Cloud until the core governance loop is real.
- The Brain must be local-first and LiteLLM-routed; do not depend on external provider CLIs, and do not put API keys in plaintext config.
- `entroping run` must remain deterministic and should not call the LLM; AI-generated Breaker work must become committed Hurl tests before it can govern CI.
- Business truth may live in Jira, Notion, Linear, or monday.com. Entroping should link through metadata and optionally cache external requirements into local Markdown.
- Entroping metadata belongs in Hurl comments such as `# entroping: tags=...`; do not add custom `tags` or `meta` keys to Hurl `[Options]`.
- Do not document unsupported Hurl validation commands. Use parser-backed validation, with `hurlfmt --out json <file>` as the safe non-executing example.
- Prefer a small typed agent router for the MVP before adopting orchestration dependencies.
