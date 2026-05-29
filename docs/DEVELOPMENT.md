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

## Setup

```bash
uv sync --dev
```

## Checks

```bash
scripts/check.sh
```

The check script runs:

1. `uv run ruff check .`
2. `uv run mypy src tests`
3. `uv run pytest`

## CLI Smoke Test

```bash
uv run entroping --help
uv run entroping --version
uv run entroping doctor
```

The CLI currently exposes the planned v4.1 command surface. Most runtime commands intentionally return a scaffold message until their subsystem is implemented.
