#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

show_help() {
  cat <<'EOF'
Usage: scripts/demo_matrix.sh [OPTIONS]

Run or dry-run the maintainer launch proof matrix.

Proof commands:
  scripts/demo.sh
  scripts/ai_regression_demo.sh
  uv run python scripts/policy_pack_smoke.py --strict
  uv run python scripts/launch_readiness.py --strict
  uv run python scripts/backlog_health.py

Options:
  --dry-run           Show the proof commands without running them.
  --skip-live-demos   Skip Hurl-backed checkout and AI-regression demos.
  -h, --help          Show this help.
EOF
}

dry_run=0
skip_live_demos=0

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      ;;
    --skip-live-demos)
      skip_live_demos=1
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

yes_no() {
  if (($1)); then
    echo "yes"
  else
    echo "no"
  fi
}

log() {
  printf '[demo-matrix] %s\n' "$*"
}

run_or_print() {
  local display="$1"
  shift
  if ((dry_run)); then
    log "Would run: $display"
  else
    log "Running: $display"
    "$@"
  fi
}

log "dry run: $(yes_no "$dry_run")"
log "skip live demos: $(yes_no "$skip_live_demos")"

cd "$repo_root"

if ((!dry_run)) && ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for the launch proof matrix." >&2
  exit 1
fi

if ((!skip_live_demos)); then
  run_or_print "scripts/demo.sh" "$repo_root/scripts/demo.sh"
  run_or_print "scripts/ai_regression_demo.sh" "$repo_root/scripts/ai_regression_demo.sh"
else
  log "Skipping Hurl-backed live demos by request."
fi

run_or_print \
  "uv run python scripts/policy_pack_smoke.py --strict" \
  uv run python scripts/policy_pack_smoke.py --strict
run_or_print \
  "uv run python scripts/launch_readiness.py --strict" \
  uv run python scripts/launch_readiness.py --strict
run_or_print \
  "uv run python scripts/backlog_health.py" \
  uv run python scripts/backlog_health.py

log "Demo proof matrix finished."
