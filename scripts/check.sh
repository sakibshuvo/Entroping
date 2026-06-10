#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${repo_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

uv run ruff check .
uv run mypy src tests
uv run pytest
