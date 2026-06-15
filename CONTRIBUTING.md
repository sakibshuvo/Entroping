# Contributing To Entroping

Entroping is early alpha. Contributions are welcome, but they need to preserve the deterministic governance thesis: AI can propose, Hurl and QAnstitution decide.

## Start Here

1. Read `README.md`.
2. For a first contribution, follow
   [GOOD_FIRST_ISSUE_WALKTHROUGH.md](docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH.md).
3. Read `AGENTS.md`.
4. Read `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`.
5. Pick or create one GitHub issue.
6. Keep the change narrow.

## Local Setup

```bash
uv sync --dev
scripts/regression.sh
```

For dependency, subprocess, proxy, LLM, report, traffic-state, or filesystem-sensitive work:

```bash
scripts/regression.sh --security
```

## Development Rules

- Preserve the locked command surface in `docs/technical/COMMAND_CHEAT_SHEET.md`.
- Keep domain and bridge modules free of adapter imports.
- Keep `entroping run` deterministic and LLM-free.
- Use Hurl as the API execution boundary.
- Add regression tests for defects when reproduction is deterministic.
- Do not commit `.entroping/`, reports, local env files, Obsidian workspace state, generated local context output, caches, or secrets.

## Pull Requests

Before opening a PR:

```bash
scripts/feature_gate.sh
scripts/regression.sh
git diff --check
```

Update docs and `.context/` only when behavior, workflow, architecture, or durable lessons changed.
