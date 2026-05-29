#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start_issue.sh <issue-number> <branch-name> [options]

Create an isolated Entroping worktree for one GitHub issue and print a
ready-to-paste session prompt for Codex, OpenCode, or another agent.

Options:
  --mode write|review    Session mode for the generated prompt. Default: write.
  --dry-run              Print the planned worktree and prompt without creating anything.
  --allow-closed         Allow prompt generation for a closed issue.
  -h, --help             Show this help text.

Environment:
  ENTROPING_REPO             GitHub repo. Default: sakibshuvo/Entroping
  ENTROPING_PROJECT_OWNER    GitHub project owner. Default: sakibshuvo
  ENTROPING_PROJECT_NUMBER   GitHub project number. Default: 1
  ENTROPING_WORKTREE_PARENT  Parent directory for worktrees.
USAGE
}

die() {
  printf 'start_issue: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'start_issue warning: %s\n' "$*" >&2
}

json_key() {
  local payload="$1"
  local key="$2"
  printf '%s' "$payload" | uv run python -c \
    'import json, sys; value = json.load(sys.stdin)[sys.argv[1]]; print(value)' "$key"
}

json_project_status_ids() {
  local payload="$1"
  printf '%s' "$payload" | uv run python -c '
import json
import sys

data = json.load(sys.stdin)
for field in data.get("fields", []):
    if field.get("name") != "Status":
        continue
    for option in field.get("options", []):
        if option.get("name") == "In Progress":
            print(field.get("id", ""))
            print(option.get("id", ""))
            raise SystemExit(0)
raise SystemExit(1)
'
}

json_project_item_id() {
  local payload="$1"
  local issue_number="$2"
  printf '%s' "$payload" | uv run python -c '
import json
import sys

data = json.load(sys.stdin)
issue_number = int(sys.argv[1])
for item in data.get("items", []):
    content = item.get("content", {})
    if content.get("number") == issue_number:
        print(item.get("id", ""))
        raise SystemExit(0)
raise SystemExit(1)
' "$issue_number"
}

render_prompt() {
  (
    cd "$repo_root"
    uv run python -m entroping.core.session_prompt \
      --issue "$issue_number" \
      --title "$issue_title" \
      --url "$issue_url" \
      --worktree "$worktree_path" \
      --branch "$branch_name" \
      --repo "$repo" \
      --mode "$mode"
  )
}

update_issue_tracking() {
  gh issue edit "$issue_number" --repo "$repo" --add-label "status:in-progress" >/dev/null \
    2>&1 || warn "could not add status:in-progress label"
  gh issue edit "$issue_number" --repo "$repo" --remove-label "status:ready" >/dev/null \
    2>&1 || true

  local project_owner="${ENTROPING_PROJECT_OWNER:-sakibshuvo}"
  local project_number="${ENTROPING_PROJECT_NUMBER:-1}"
  local project_json
  local project_id
  local fields_json
  local ids
  local status_field_id
  local in_progress_option_id
  local items_json
  local item_id

  if ! project_json=$(gh project view "$project_number" --owner "$project_owner" --format json 2>/dev/null); then
    warn "could not read GitHub Project board; worktree was still created"
    return 0
  fi
  project_id=$(json_key "$project_json" "id")

  if ! fields_json=$(gh project field-list "$project_number" --owner "$project_owner" --format json 2>/dev/null); then
    warn "could not read GitHub Project fields"
    return 0
  fi
  if ! ids=$(json_project_status_ids "$fields_json"); then
    warn "could not find Project Status/In Progress field option"
    return 0
  fi
  status_field_id=$(printf '%s\n' "$ids" | sed -n '1p')
  in_progress_option_id=$(printf '%s\n' "$ids" | sed -n '2p')

  if ! items_json=$(gh project item-list "$project_number" --owner "$project_owner" --limit 200 --format json 2>/dev/null); then
    warn "could not read GitHub Project items"
    return 0
  fi
  if ! item_id=$(json_project_item_id "$items_json" "$issue_number"); then
    warn "issue #$issue_number is not on the GitHub Project board"
    return 0
  fi

  gh project item-edit \
    --id "$item_id" \
    --project-id "$project_id" \
    --field-id "$status_field_id" \
    --single-select-option-id "$in_progress_option_id" >/dev/null 2>&1 \
    || warn "could not move issue #$issue_number to In Progress"
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

issue_number="$1"
branch_name="$2"
shift 2

mode="write"
dry_run="0"
allow_closed="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || die "--mode requires write or review"
      mode="$2"
      shift 2
      ;;
    --dry-run)
      dry_run="1"
      shift
      ;;
    --allow-closed)
      allow_closed="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[[ "$issue_number" =~ ^[1-9][0-9]*$ ]] || die "issue-number must be a positive integer"
[[ "$mode" == "write" || "$mode" == "review" ]] || die "--mode must be write or review"
[[ "$branch_name" != *" "* ]] || die "branch-name must not contain spaces"
command -v git >/dev/null 2>&1 || die "git is required"
command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required"
command -v uv >/dev/null 2>&1 || die "uv is required"

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) \
  || die "run this from inside the Entroping git repository"
repo="${ENTROPING_REPO:-sakibshuvo/Entroping}"
worktree_parent="${ENTROPING_WORKTREE_PARENT:-$(dirname "$repo_root")}"
worktree_path="${worktree_parent}/Entroping-issue-${issue_number}"

issue_json=$(gh issue view "$issue_number" --repo "$repo" --json title,url,state) \
  || die "could not read GitHub issue #$issue_number from $repo"
issue_title=$(json_key "$issue_json" "title")
issue_url=$(json_key "$issue_json" "url")
issue_state=$(json_key "$issue_json" "state")

if [[ "$issue_state" != "OPEN" && "$allow_closed" != "1" ]]; then
  die "issue #$issue_number is $issue_state; use --allow-closed for review-only sessions"
fi

if [[ "$dry_run" == "1" ]]; then
  printf 'DRY RUN\n'
  printf 'Repo: %s\n' "$repo"
  printf 'Issue: #%s %s\n' "$issue_number" "$issue_title"
  printf 'Branch: %s\n' "$branch_name"
  printf 'Worktree: %s\n\n' "$worktree_path"
  render_prompt
  exit 0
fi

[[ ! -e "$worktree_path" ]] || die "worktree path already exists: $worktree_path"
if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
  die "local branch already exists: $branch_name"
fi

git -C "$repo_root" pull --ff-only origin main
mkdir -p "$worktree_parent"
git -C "$repo_root" worktree add "$worktree_path" -b "$branch_name" main
update_issue_tracking

prompt_dir="$worktree_path/.entroping/session-prompts"
prompt_path="$prompt_dir/issue-$issue_number.md"
mkdir -p "$prompt_dir"
render_prompt > "$prompt_path"

printf 'Created worktree: %s\n' "$worktree_path"
printf 'Created prompt: %s\n\n' "$prompt_path"
cat "$prompt_path"
