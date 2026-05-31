#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/doc_governance_check.sh [--root <path>]

Validates the documentation control plane so humans and agents cannot silently
remove roadmap, progress, PR, or agent-governance guardrails.

Required anchors include:
  README.md links ROADMAP.md
  ROADMAP.md defines public roadmap boundaries
  docs/meta/DOCS_GOVERNANCE.md defines the update matrix
  .github/pull_request_template.md requires a Documentation Impact Declaration
  scripts/feature_gate.sh runs this check

Options:
  --root <path>  Validate another repository root, used by tests.
  -h, --help     Show this help.
EOF
}

repo_root=""

while (($#)); do
  case "$1" in
    --root)
      if [[ -z "${2:-}" ]]; then
        echo "--root requires a path." >&2
        exit 2
      fi
      repo_root="$2"
      shift
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

if [[ -z "$repo_root" ]]; then
  if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    echo "doc_governance_check.sh must be run inside a Git repository." >&2
    exit 2
  fi
fi

failures=()

require_file() {
  local relative_path="$1"
  if [[ ! -s "$repo_root/$relative_path" ]]; then
    failures+=("$relative_path: missing or empty")
  fi
}

require_marker() {
  local relative_path="$1"
  local marker="$2"

  require_file "$relative_path"
  if [[ -s "$repo_root/$relative_path" ]] && ! grep -Fq -- "$marker" "$repo_root/$relative_path"; then
    failures+=("$relative_path: missing marker: $marker")
  fi
}

require_marker "README.md" "[ROADMAP.md](ROADMAP.md)"
require_marker "README.md" "[DOCS_GOVERNANCE.md](docs/meta/DOCS_GOVERNANCE.md)"
require_marker "ROADMAP.md" "Canonical work tracking lives in:"
require_marker "ROADMAP.md" "Explicitly Not Near-Term"
require_marker "00_INDEX.md" "[[ROADMAP|ROADMAP]]"
require_marker "00_INDEX.md" "[[docs/meta/OBSIDIAN_VS_GITHUB|OBSIDIAN_VS_GITHUB]]"
require_marker "docs/meta/OBSIDIAN_VS_GITHUB.md" "## Fast Rule"
require_marker "docs/meta/OBSIDIAN_VS_GITHUB.md" "## Brainstorming Workflow"
require_marker "docs/meta/OBSIDIAN_VS_GITHUB.md" "## Bug Workflow"
require_marker "docs/meta/OBSIDIAN_VS_GITHUB.md" "## Roadmap Workflow"
require_marker "docs/meta/OBSIDIAN_VS_GITHUB.md" "## Weekly Review"
require_marker "docs/meta/DOCS_GOVERNANCE.md" "## Update Matrix"
require_marker "docs/meta/DOCS_GOVERNANCE.md" "## Roadmap Change Gate"
require_marker "docs/meta/DOCS_GOVERNANCE.md" "## Agent Rules"
require_marker "docs/meta/DOCS_GOVERNANCE.md" "Documentation Impact Declaration"
require_marker ".github/pull_request_template.md" "## Documentation Impact Declaration"
require_marker ".github/pull_request_template.md" "Roadmap/progress updated:"
require_marker "scripts/feature_gate.sh" "scripts/doc_governance_check.sh"
require_marker "docs/meta/FEATURE_DELIVERY_CHECKLIST.md" "scripts/doc_governance_check.sh"
require_marker "docs/meta/FEATURE_DELIVERY_CHECKLIST.md" "Documentation Impact Declaration"
require_marker "docs/meta/PROJECT_PROGRESS.md" "DOCS_GOVERNANCE"
require_marker "AGENTS.md" "docs/meta/DOCS_GOVERNANCE.md"

if ((${#failures[@]})); then
  echo "Documentation governance failed:" >&2
  printf '  %s\n' "${failures[@]}" >&2
  exit 1
fi

echo "Documentation governance OK"
