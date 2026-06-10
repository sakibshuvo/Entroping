#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${repo_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

show_help() {
  cat <<'EOF'
Usage: scripts/regression.sh [--security]

Runs the project regression suite. This is the default local and CI proof that
the scaffold, CLI surface, tests, typing, linting, and whitespace checks still
work together.

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

if ((run_security)); then
  scripts/feature_gate.sh --security
else
  scripts/feature_gate.sh
fi

uv run entroping --help >/dev/null
uv run entroping --version >/dev/null
uv run entroping doctor >/dev/null
