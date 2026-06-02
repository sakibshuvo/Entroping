#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

show_help() {
  cat <<'EOF'
Usage: scripts/shell_quality.sh [OPTIONS]

Runs shell script quality checks over tracked .sh files.

Checks:
  - bash -n syntax validation over tracked shell scripts.
  - ShellCheck lint when shellcheck is available; absence is reported as an explicit optional skip.

Options:
  --dry-run   Show deterministic shell quality steps without running them.
  -h, --help  Show this help.
EOF
}

dry_run=0

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      ;;
    -h | --help)
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

log() {
  printf '[shell-quality] %s\n' "$*"
}

cd "$repo_root"

shell_scripts=()
while IFS= read -r script; do
  shell_scripts+=("$script")
done < <(git ls-files '*.sh' | sort)

if ((${#shell_scripts[@]} == 0)); then
  log "No tracked shell scripts found."
  exit 0
fi

if ((dry_run)); then
  log "Would run bash -n over tracked shell scripts (${#shell_scripts[@]} files)."
  log "Would run ShellCheck when shellcheck is available."
  exit 0
fi

log "Running bash -n over tracked shell scripts (${#shell_scripts[@]} files)."
for script in "${shell_scripts[@]}"; do
  bash -n "$script"
done
log "bash -n passed."

if command -v shellcheck >/dev/null 2>&1; then
  log "Running ShellCheck over tracked shell scripts."
  shellcheck "${shell_scripts[@]}"
  log "ShellCheck passed."
else
  log "ShellCheck not found; skipped optional ShellCheck lint."
fi
