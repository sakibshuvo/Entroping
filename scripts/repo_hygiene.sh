#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/repo_hygiene.sh

Fails when local machine state, runtime state, caches, reports, or generated
local output are tracked by Git.

Forbidden tracked paths include:
  .DS_Store
  .obsidian/
  .entroping/
  .entroping/factory-metrics/
  reports/
  llm-wiki-out/
  .understand-anything/
  understand-anything-out/
  agent-context-out/
  .venv/
  .mypy_cache/
  .pytest_cache/
  .ruff_cache/

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

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "repo_hygiene.sh must be run inside a Git repository." >&2
  exit 2
fi

is_forbidden_path() {
  local path="$1"

  case "$path" in
    .DS_Store|*/.DS_Store|\
    .obsidian/*|\
    .entroping/factory-metrics/*|\
    .entroping/*|\
    reports/*|\
    llm-wiki-out/*|\
    .understand-anything/*|\
    understand-anything-out/*|\
    agent-context-out/*|\
    .venv/*|\
    .mypy_cache/*|\
    .pytest_cache/*|\
    .ruff_cache/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

forbidden=()

while IFS= read -r -d '' tracked_path; do
  if is_forbidden_path "$tracked_path"; then
    forbidden+=("$tracked_path")
  fi
done < <(git -C "$repo_root" ls-files -z)

if ((${#forbidden[@]})); then
  echo "Forbidden tracked local/generated files detected:" >&2
  printf '  %s\n' "${forbidden[@]}" >&2
  echo >&2
  echo "Remove them from the index after confirming local copies should remain:" >&2
  echo "  git rm --cached <path> ..." >&2
  exit 1
fi

echo "Repo hygiene OK"
