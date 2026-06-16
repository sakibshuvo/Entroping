#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/architecture_integrity.sh

Runs Entroping's deterministic architecture integrity gate.

This executes the AST import-boundary checks in
tests/test_architecture_boundaries.py. The gate is source-only and
provider-free: it does not call model providers, execute Hurl, access the
network, or read secrets.

Options:
  -h, --help  Show this help.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
  exit 0
fi

if (($#)); then
  echo "Unknown option: $1" >&2
  show_help >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${repo_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

echo "Architecture integrity: running AST import-boundary checks"
uv run pytest tests/test_architecture_boundaries.py -q
echo "Architecture integrity OK"
