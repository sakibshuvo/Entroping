---
title: Development
type: guide
status: active
tags:
  - development
  - uv
---

# Development

## Tooling

This repository is prepared for:

- Python 3.12
- uv for dependency and virtual environment management
- ruff, mypy, and pytest for local quality gates
- Codex as the primary implementation agent
- OpenCode as a future low-cost worker/reviewer loop
- Spec Kit as a future feature-spec pilot

## Setup

```bash
uv sync --dev
```

## Checks

```bash
scripts/feature_gate.sh
```

The feature gate runs:

1. `uv run ruff check .`
2. `uv run mypy src tests`
3. `uv run pytest`
4. `git diff --check`
5. `git diff --cached --check`

For the underlying fast scaffold gate, run:

```bash
scripts/check.sh
```

## Regression Suite

```bash
scripts/regression.sh
```

The regression suite runs the feature gate plus CLI smoke checks. CI uses this command as the default proof that existing behavior still works.

## Security Checks

For dependency or security-sensitive work, also run:

```bash
scripts/feature_gate.sh --security
scripts/regression.sh --security
```

The all-extras audit matters because future runtime surfaces such as `watch` use optional dependencies.

## CLI Smoke Test

```bash
uv run entroping --help
uv run entroping --version
uv run entroping doctor
```

The CLI currently exposes the planned v4.1 command surface. `init`, `doctor`, deterministic `run`, JSON/JUnit reports, and `report bug` are implemented; AI, proxy, HTML/drift reports, and Studio commands still intentionally return scaffold messages until their subsystems land.

## Agent Workflow

Use `docs/meta/AUTONOMOUS_DEVELOPMENT.md` for the Codex-first operating loop and the future OpenCode/oMLX plan.

Use `docs/meta/FEATURE_DELIVERY_CHECKLIST.md` before every meaningful feature branch or PR.
