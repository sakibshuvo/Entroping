#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/feature_gate.sh [--security]

Runs the local feature delivery gate.

Options:
  --security  Also run Bandit and default/all-extras dependency audits.
  -h, --help  Show this help.
EOF
}

run_security=0

while (($#)); do
  case "$1" in
    --security)
      run_security=1
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help >&2
      exit 2
      ;;
  esac
  shift
done

scripts/repo_hygiene.sh
scripts/check.sh
git diff --check
git diff --cached --check

if ((run_security)); then
  uvx bandit -q -r src
  uv run --with pip-audit pip-audit --local --progress-spinner off
  uv run --all-extras --with pip-audit pip-audit --progress-spinner off
fi
