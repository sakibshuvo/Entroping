#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/install_hooks.sh [--dry-run] [--force]

Installs Entroping's optional local Git hooks into the current repository.
The hooks are local developer convenience only; repository behavior lives in
tracked scripts and CI.

Options:
  --dry-run   Print what would be installed without writing files.
  --force     Overwrite an existing pre-commit hook.
  -h, --help  Show this help.
EOF
}

dry_run=0
force=0

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      ;;
    --force)
      force=1
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

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "install_hooks.sh must be run inside a Git repository." >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
template_path="$script_dir/hooks/pre-commit"

if [[ ! -f "$template_path" ]]; then
  echo "Missing hook template: $template_path" >&2
  exit 1
fi

hook_path="$(git -C "$repo_root" rev-parse --git-path hooks/pre-commit)"
case "$hook_path" in
  /*) ;;
  *) hook_path="$repo_root/$hook_path" ;;
esac

if ((dry_run)); then
  echo "Would install pre-commit hook: $hook_path"
  exit 0
fi

if [[ -e "$hook_path" && "$force" -ne 1 ]]; then
  echo "pre-commit hook already exists: $hook_path (use --force to overwrite)" >&2
  exit 1
fi

if [[ ! -x "$repo_root/scripts/repo_hygiene.sh" ]]; then
  echo "Cannot install hooks: $repo_root/scripts/repo_hygiene.sh is missing or not executable." >&2
  exit 1
fi

mkdir -p "$(dirname "$hook_path")"
cp "$template_path" "$hook_path"
chmod +x "$hook_path"

echo "Installed pre-commit hook: $hook_path"
