# Contributing To Entroping

Entroping is early alpha. Contributions are welcome, but they need to preserve the deterministic governance thesis: AI can propose, Hurl and QAnstitution decide.

## Start Here

1. Read `README.md`.
2. Read `AGENTS.md`.
3. Read `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`.
4. Pick or create one GitHub issue.
5. Keep the change narrow.

## Issue Labels

| Label | Meaning | Good for new contributors? |
|-------|---------|---------------------------|
| `good-first-issue` | Small, self-contained, clear acceptance criteria | ✅ Yes |
| `bug` | Reproducible defect with steps to reproduce | ✅ If deterministic |
| `feature` | New behavior or enhancement | ⚠️ Read FEATURE_DELIVERY_CHECKLIST first |
| `docs` | Documentation-only change | ✅ Yes |
| `regression` | Previously working behavior broke | ⚠️ Needs regression test |

## Step-by-Step: Your First Contribution

### 1. Pick an issue

Browse [open issues](https://github.com/sakibshuvo/Entroping/issues) and look for `good-first-issue` labels. Each issue has acceptance criteria — read them before starting.

### 2. Create a worktree

Use the provided script to create an isolated worktree:

```bash
scripts/start_issue.sh <issue-number> <branch-name>
```

This creates a git worktree (not a branch in your main checkout) and prints a session prompt you can paste into Codex, OpenCode, or another agent.

Options:
- `--mode write` — for implementing the change (default)
- `--mode review` — for reviewing existing code
- `--dry-run` — print the plan without creating anything

### 3. Implement the change

Work inside the worktree. Follow the development rules below.

### 4. Validate locally

Before committing, run both gates:

```bash
# Feature gate (lint, type-check, tests)
scripts/feature_gate.sh

# Full regression suite
scripts/regression.sh

# Check for trailing whitespace
git diff --check
```

### 5. Commit and push

```bash
git add -A
git commit -m "feat: brief description of change

Closes #<issue-number>"
git push origin <branch-name>
```

### 6. Open a pull request

Open a PR against `main`. The PR template will guide you through the checklist.

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
- Do not commit `.entroping/`, reports, local env files, Obsidian workspace state, Graphify output, caches, or secrets.

## Pull Requests

Before opening a PR:

```bash
scripts/feature_gate.sh
scripts/regression.sh
git diff --check
```

Update docs and `.context/` only when behavior, workflow, architecture, or durable lessons changed.

## What Happens After You Open a PR

1. **CI runs** — feature gate and regression suite run automatically.
2. **Review** — a maintainer reviews your change. They may request changes.
3. **Merge** — once approved and CI passes, your PR is merged.

## Architecture Overview

For a high-level understanding of the codebase, see:
- `docs/architecture/ARCHITECTURE.md` — implementation overview
- `docs/architecture/DEVELOPMENT.md` — local development commands
- `docs/technical/TDS.md` — technical design spec

## Getting Help

- Open a [discussion](https://github.com/sakibshuvo/Entroping/discussions) for questions
- Comment on an issue if you're stuck
- Read `docs/meta/KNOWLEDGE_BASE_WORKFLOW.md` for how the project manages context
