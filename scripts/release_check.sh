#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

show_help() {
  cat <<'EOF'
Usage: scripts/release_check.sh [OPTIONS]

Runs the local alpha release-readiness gate.

By default this requires a clean Git worktree, rejects tracked local/generated
state, verifies package artifacts, runs the security regression suite, runs the
bounded performance smoke, checks alpha launch and stable-core evidence, and
runs downstream and live demo smokes when the Hurl binary is available.

Options:
  --dry-run            Show the planned release gate without running commands.
  --skip-security      Run regression without dependency/security audits.
  --aggregate          Run all independent release gates and print a summary of all
                       command failures before exiting.
  --skip-performance   Do not run the bounded performance smoke.
  --skip-downstream-smoke
                       Do not run the external downstream project smoke.
  --skip-release-evidence-freshness
                       Validate release evidence without the GitHub freshness
                       lookup. Use only for offline/local diagnostics.
  --skip-live-demo     Do not run the live Hurl demo smoke.
  --require-live-demo  Fail if Hurl is missing instead of skipping the demo.
  --allow-dirty        Allow uncommitted changes in the working tree.
  -h, --help           Show this help.
EOF
}

dry_run=0
skip_security=0
aggregate=0
skip_performance=0
skip_downstream_smoke=0
release_evidence_freshness=1
skip_live_demo=0
require_live_demo=0
allow_dirty=0
failed_gates=()
failed_codes=()

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      ;;
    --aggregate)
      aggregate=1
      ;;
    --skip-security)
      skip_security=1
      ;;
    --skip-performance)
      skip_performance=1
      ;;
    --skip-downstream-smoke)
      skip_downstream_smoke=1
      ;;
    --skip-release-evidence-freshness)
      release_evidence_freshness=0
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

run_or_record() {
  local gate_name="$1"
  shift

  if ((dry_run)); then
    log "Would run: $*"
    return 0
  fi

  if ((aggregate)); then
    log "Running: $*"
    local exit_code=0
    set +e
    "$@"
    exit_code=$?
    set -e
    if ((exit_code == 0)); then
      return 0
    fi
    failed_gates+=("$gate_name :: $*")
    failed_codes+=("$exit_code")
    return 0
  fi

  run_or_print "$@"
}

log "dry run: $(yes_no "$dry_run")"
log "skip security: $(yes_no "$skip_security")"
log "aggregate mode: $(yes_no "$aggregate")"
log "skip performance: $(yes_no "$skip_performance")"
log "skip downstream smoke: $(yes_no "$skip_downstream_smoke")"
log "release evidence freshness: $(yes_no "$release_evidence_freshness")"
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

release_evidence_command=(uv run python scripts/release_evidence.py)
if ((release_evidence_freshness)); then
  release_evidence_command+=(--check-freshness)
fi
release_evidence_command+=(--strict)

if ((aggregate)); then
  run_or_record "repo_hygiene" scripts/repo_hygiene.sh
  run_or_record "policy_pack_smoke" uv run python scripts/policy_pack_smoke.py --strict
  run_or_record "launch_readiness" uv run python scripts/launch_readiness.py --strict
  run_or_record "release_evidence" "${release_evidence_command[@]}"
  run_or_record "package_index_readiness" uv run python scripts/package_index_readiness.py --strict
  run_or_record "install_reference_sync" uv run python scripts/install_reference_sync.py --check
  run_or_record "stable_core_readiness" uv run python scripts/stable_core_readiness.py --strict
  run_or_record "package_check" scripts/package_check.sh
  run_or_record "local_wheel_install_smoke" uv run python scripts/local_wheel_install_smoke.py --skip-build
else
  run_or_print scripts/repo_hygiene.sh
  run_or_print uv run python scripts/policy_pack_smoke.py --strict
  run_or_print uv run python scripts/launch_readiness.py --strict
  run_or_print "${release_evidence_command[@]}"
  run_or_print uv run python scripts/package_index_readiness.py --strict
  run_or_print uv run python scripts/install_reference_sync.py --check
  run_or_print uv run python scripts/stable_core_readiness.py --strict
  run_or_print scripts/package_check.sh
  run_or_print uv run python scripts/local_wheel_install_smoke.py --skip-build
fi

if ((skip_security)); then
  if ((aggregate)); then
    run_or_record "regression" scripts/regression.sh
  else
    run_or_print scripts/regression.sh
  fi
else
  if ((aggregate)); then
    run_or_record "regression_security" scripts/regression.sh --security
  else
    run_or_print scripts/regression.sh --security
  fi
fi

if ((skip_performance)); then
  log "Skipping performance smoke by request."
else
  if ((aggregate)); then
    run_or_record "performance_smoke" uv run python scripts/performance_smoke.py
  else
    run_or_print uv run python scripts/performance_smoke.py
  fi
fi

if ((skip_downstream_smoke)); then
  log "Skipping downstream smoke by request."
elif ((dry_run)); then
  if ((aggregate)); then
    run_or_record "downstream_smoke" uv run python scripts/downstream_smoke.py
  else
    run_or_print uv run python scripts/downstream_smoke.py
  fi
elif command -v hurl >/dev/null 2>&1; then
  if ((aggregate)); then
    run_or_record "downstream_smoke" uv run python scripts/downstream_smoke.py
  else
    run_or_print uv run python scripts/downstream_smoke.py
  fi
elif ((require_live_demo)); then
  echo "Hurl binary not found; cannot run required downstream or live demo smoke." >&2
  exit 1
else
  log "Skipping downstream smoke because hurl is not installed."
  log "Use --require-live-demo for release-candidate proof."
fi

if ((skip_live_demo)); then
  log "Skipping live demo smoke by request."
elif ((dry_run)); then
  if ((aggregate)); then
    run_or_record "live_demo_smoke" scripts/live_demo_smoke.sh
  else
    run_or_print scripts/live_demo_smoke.sh
  fi
elif command -v hurl >/dev/null 2>&1; then
  if ((aggregate)); then
    run_or_record "live_demo_smoke" scripts/live_demo_smoke.sh
  else
    run_or_print scripts/live_demo_smoke.sh
  fi
elif ((require_live_demo)); then
  echo "Hurl binary not found; cannot run required live demo smoke." >&2
  exit 1
else
  log "Skipping live demo smoke because hurl is not installed. Use --require-live-demo for release-candidate proof."
fi

if ((aggregate)) && ((${#failed_gates[@]} > 0)); then
  log "Release check failed with ${#failed_gates[@]} failed gate(s)."
  for i in "${!failed_gates[@]}"; do
    log " - ${failed_gates[i]} (exit ${failed_codes[i]})"
  done
  log "Run in non-aggregated mode for first-failure-fast debugging."
  exit 1
fi

log "Release readiness gate finished."
