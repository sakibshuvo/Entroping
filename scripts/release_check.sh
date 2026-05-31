#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

show_help() {
  cat <<'EOF'
Usage: scripts/release_check.sh [OPTIONS]

Runs the local alpha release-readiness gate.

By default this requires a clean Git worktree, rejects tracked local/generated
state, verifies package artifacts, runs the security regression suite, runs the
bounded performance smoke, and runs the live demo smoke when the Hurl binary is
available.

Options:
  --dry-run            Show the planned release gate without running commands.
  --skip-security      Run regression without dependency/security audits.
  --skip-performance   Do not run the bounded performance smoke.
  --skip-live-demo     Do not run the live Hurl demo smoke.
  --require-live-demo  Fail if Hurl is missing instead of skipping the demo.
  --allow-dirty        Allow uncommitted changes in the working tree.
  -h, --help           Show this help.
EOF
}

dry_run=0
skip_security=0
skip_performance=0
skip_live_demo=0
require_live_demo=0
allow_dirty=0

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      ;;
    --skip-security)
      skip_security=1
      ;;
    --skip-performance)
      skip_performance=1
      ;;
    --skip-live-demo)
      skip_live_demo=1
      ;;
    --require-live-demo)
      require_live_demo=1
      ;;
    --allow-dirty)
      allow_dirty=1
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

if ((skip_live_demo && require_live_demo)); then
  echo "--skip-live-demo and --require-live-demo cannot be used together." >&2
  exit 2
fi

yes_no() {
  if (($1)); then
    echo "yes"
  else
    echo "no"
  fi
}

log() {
  printf '[release-check] %s\n' "$*"
}

run_or_print() {
  if ((dry_run)); then
    log "Would run: $*"
  else
    log "Running: $*"
    "$@"
  fi
}

log "dry run: $(yes_no "$dry_run")"
log "skip security: $(yes_no "$skip_security")"
log "skip performance: $(yes_no "$skip_performance")"
log "skip live demo: $(yes_no "$skip_live_demo")"
log "require live demo: $(yes_no "$require_live_demo")"
log "allow dirty worktree: $(yes_no "$allow_dirty")"

if ((dry_run)); then
  if ((allow_dirty)); then
    log "Would allow a dirty Git worktree."
  else
    log "Would require a clean Git worktree."
  fi
else
  if ((!allow_dirty)); then
    status="$(git -C "$repo_root" status --short)"
    if [[ -n "$status" ]]; then
      echo "Release check requires a clean Git worktree. Current status:" >&2
      echo "$status" >&2
      echo "Commit, stash, or rerun with --allow-dirty for local diagnostics." >&2
      exit 1
    fi
  fi
fi

cd "$repo_root"

run_or_print scripts/repo_hygiene.sh
run_or_print scripts/package_check.sh

if ((skip_security)); then
  run_or_print scripts/regression.sh
else
  run_or_print scripts/regression.sh --security
fi

if ((skip_performance)); then
  log "Skipping performance smoke by request."
else
  run_or_print uv run python scripts/performance_smoke.py
fi

if ((skip_live_demo)); then
  log "Skipping live demo smoke by request."
elif ((dry_run)); then
  run_or_print scripts/live_demo_smoke.sh
elif command -v hurl >/dev/null 2>&1; then
  run_or_print scripts/live_demo_smoke.sh
elif ((require_live_demo)); then
  echo "Hurl binary not found; cannot run required live demo smoke." >&2
  exit 1
else
  log "Skipping live demo smoke because hurl is not installed. Use --require-live-demo for release-candidate proof."
fi

log "Release readiness gate finished."
