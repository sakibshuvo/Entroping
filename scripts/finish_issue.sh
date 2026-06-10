#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/finish_issue.sh <issue-number> [options]

Finish a merged issue session by verifying the closing PR, CI checks, issue
state, and local worktree safety before removing local cleanup state.

Options:
  --dry-run         Print the verified cleanup plan without deleting anything.
  --worktree PATH   Override the issue worktree path.
  -h, --help        Show this help text.

Environment:
  ENTROPING_REPO             GitHub repo. Default: sakibshuvo/Entroping
  ENTROPING_PROJECT_OWNER    GitHub project owner. Default: sakibshuvo
  ENTROPING_PROJECT_NUMBER   GitHub project number. Default: 1
  ENTROPING_WORKTREE_PARENT  Parent directory for issue worktrees.
USAGE
}

die() {
  printf 'finish_issue: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'finish_issue warning: %s\n' "$*" >&2
}

json_key() {
  local payload="$1"
  local key="$2"
  printf '%s' "$payload" | python3 -c \
    'import json, sys; value = json.load(sys.stdin).get(sys.argv[1], ""); print("" if value is None else value)' "$key"
}

json_closing_pr_number() {
  local payload="$1"
  printf '%s' "$payload" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
refs = data.get("closedByPullRequestsReferences") or []
if not refs:
    raise SystemExit(1)
number = refs[0].get("number")
if not isinstance(number, int):
    raise SystemExit(1)
print(number)
'
}

json_check_rollup_passed() {
  local payload="$1"
  printf '%s' "$payload" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
checks = data.get("statusCheckRollup") or []
if not checks:
    print("no CI checks found on closing PR", file=sys.stderr)
    raise SystemExit(1)

allowed_check_run_conclusions = {"SUCCESS", "SKIPPED", "NEUTRAL"}
bad: list[str] = []
for check in checks:
    name = str(check.get("name") or check.get("context") or "<unnamed>")
    kind = check.get("__typename", "")
    if kind == "CheckRun":
        status = str(check.get("status", "")).upper()
        conclusion = str(check.get("conclusion", "")).upper()
        if status != "COMPLETED" or conclusion not in allowed_check_run_conclusions:
            status_display = status or "?"
            conclusion_display = conclusion or "?"
            bad.append(f"{name}: status={status_display} conclusion={conclusion_display}")
    elif kind == "StatusContext":
        state = str(check.get("state", "")).upper()
        if state != "SUCCESS":
            state_display = state or "?"
            bad.append(f"{name}: state={state_display}")
    else:
        state = str(check.get("state") or check.get("status") or "").upper()
        conclusion = str(check.get("conclusion") or "").upper()
        if state not in {"SUCCESS", "COMPLETED"} and conclusion not in allowed_check_run_conclusions:
            bad.append(f"{name}: unrecognized check state")

if bad:
    print("closing PR has non-passing checks:", file=sys.stderr)
    for item in bad:
        print(f"  {item}", file=sys.stderr)
    raise SystemExit(1)

print(len(checks))
'
}

json_project_status_ids() {
  local payload="$1"
  printf '%s' "$payload" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
for field in data.get("fields", []):
    if field.get("name") != "Status":
        continue
    for option in field.get("options", []):
        if option.get("name") == "Done":
            print(field.get("id", ""))
            print(option.get("id", ""))
            raise SystemExit(0)
raise SystemExit(1)
'
}

json_project_item_id() {
  local payload="$1"
  local issue_number="$2"
  printf '%s' "$payload" | python3 -c '
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

retry_project_item_id() {
  local project_number="$1"
  local project_owner="$2"
  local issue_number="$3"
  local attempts="${ENTROPING_PROJECT_ITEM_LOOKUP_RETRIES:-3}"
  local delay_seconds="${ENTROPING_PROJECT_ITEM_LOOKUP_RETRY_DELAY_SECONDS:-1}"
  local attempt
  local items_json
  local item_id

  if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]]; then
    attempts="3"
  fi
  if [[ ! "$delay_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    delay_seconds="1"
  fi

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if ! items_json=$(gh project item-list "$project_number" --owner "$project_owner" --limit 200 --format json 2>/dev/null); then
      return 2
    fi
    if item_id=$(json_project_item_id "$items_json" "$issue_number"); then
      printf '%s\n' "$item_id"
      return 0
    fi
    if ((attempt < attempts)); then
      sleep "$delay_seconds"
    fi
  done
  return 1
}

canonical_path() {
  (cd "$1" && pwd -P)
}

worktree_is_registered() {
  local repo_root="$1"
  local worktree_path="$2"
  git -C "$repo_root" worktree list --porcelain | python3 -c '
from __future__ import annotations

import os
import sys

target = os.path.realpath(sys.argv[1])
for line in sys.stdin:
    if not line.startswith("worktree "):
        continue
    candidate = os.path.realpath(line.removeprefix("worktree ").strip())
    if candidate == target:
        raise SystemExit(0)
raise SystemExit(1)
' "$worktree_path"
}

remove_status_labels() {
  gh issue edit "$issue_number" --repo "$repo" --remove-label "status:in-progress" >/dev/null \
    2>&1 || warn "could not remove status:in-progress label"
  gh issue edit "$issue_number" --repo "$repo" --remove-label "status:ready" >/dev/null \
    2>&1 || true
}

move_project_done() {
  local project_owner="${ENTROPING_PROJECT_OWNER:-sakibshuvo}"
  local project_number="${ENTROPING_PROJECT_NUMBER:-1}"
  local project_json
  local project_id
  local fields_json
  local ids
  local status_field_id
  local done_option_id
  local items_json
  local item_id
  local item_lookup_status

  if ! project_json=$(gh project view "$project_number" --owner "$project_owner" --format json 2>/dev/null); then
    warn "could not read GitHub Project board"
    return 0
  fi
  project_id=$(json_key "$project_json" "id")

  if ! fields_json=$(gh project field-list "$project_number" --owner "$project_owner" --format json 2>/dev/null); then
    warn "could not read GitHub Project fields"
    return 0
  fi
  if ! ids=$(json_project_status_ids "$fields_json"); then
    warn "could not find Project Status/Done field option"
    return 0
  fi
  status_field_id=$(printf '%s\n' "$ids" | sed -n '1p')
  done_option_id=$(printf '%s\n' "$ids" | sed -n '2p')

  if ! items_json=$(gh project item-list "$project_number" --owner "$project_owner" --limit 200 --format json 2>/dev/null); then
    warn "could not read GitHub Project items"
    return 0
  fi
  if ! item_id=$(json_project_item_id "$items_json" "$issue_number"); then
    if ! gh project item-add "$project_number" --owner "$project_owner" --url "$issue_url" >/dev/null 2>&1; then
      warn "issue #$issue_number is not on the GitHub Project board and could not be added"
      return 0
    fi
    item_lookup_status=0
    item_id=$(retry_project_item_id "$project_number" "$project_owner" "$issue_number") \
      || item_lookup_status=$?
    if [[ "$item_lookup_status" == "2" ]]; then
      warn "added issue #$issue_number to the GitHub Project board but could not reread items"
      return 0
    fi
    if [[ "$item_lookup_status" != "0" ]]; then
      warn "added issue #$issue_number to the GitHub Project board but could not find the item"
      return 0
    fi
  fi

  gh project item-edit \
    --id "$item_id" \
    --project-id "$project_id" \
    --field-id "$status_field_id" \
    --single-select-option-id "$done_option_id" >/dev/null 2>&1 \
    || warn "could not move issue #$issue_number to Done"
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

issue_number="$1"
shift

dry_run="0"
worktree_override=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run="1"
      shift
      ;;
    --worktree)
      [[ $# -ge 2 ]] || die "--worktree requires a path"
      worktree_override="$2"
      shift 2
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
command -v git >/dev/null 2>&1 || die "git is required"
command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) \
  || die "run this from inside an Entroping git repository"
repo="${ENTROPING_REPO:-sakibshuvo/Entroping}"
worktree_parent="${ENTROPING_WORKTREE_PARENT:-$(dirname "$repo_root")}"
if [[ -n "$worktree_override" ]]; then
  worktree_path="$worktree_override"
else
  worktree_path="${worktree_parent}/Entroping-issue-${issue_number}"
fi

issue_json=$(gh issue view "$issue_number" --repo "$repo" \
  --json title,url,state,closedByPullRequestsReferences) \
  || die "could not read GitHub issue #$issue_number from $repo"
issue_title=$(json_key "$issue_json" "title")
issue_url=$(json_key "$issue_json" "url")
issue_state=$(json_key "$issue_json" "state")
[[ "$issue_state" == "CLOSED" ]] || die "issue #$issue_number is $issue_state; wait for merge/close before cleanup"

if ! pr_number=$(json_closing_pr_number "$issue_json"); then
  die "issue #$issue_number has no closing pull request reference"
fi
pr_json=$(gh pr view "$pr_number" --repo "$repo" \
  --json number,url,state,headRefName,mergedAt,statusCheckRollup) \
  || die "could not read closing PR #$pr_number"
pr_state=$(json_key "$pr_json" "state")
pr_url=$(json_key "$pr_json" "url")
branch_name=$(json_key "$pr_json" "headRefName")
merged_at=$(json_key "$pr_json" "mergedAt")
[[ "$pr_state" == "MERGED" && -n "$merged_at" ]] || die "closing PR #$pr_number is not merged"
[[ -n "$branch_name" ]] || die "closing PR #$pr_number has no head branch name"
if ! check_count=$(json_check_rollup_passed "$pr_json"); then
  die "closing PR #$pr_number checks have not all passed"
fi

worktree_exists="0"
if [[ -e "$worktree_path" ]]; then
  worktree_exists="1"
  worktree_real=$(canonical_path "$worktree_path")
  repo_real=$(canonical_path "$repo_root")
  if [[ "$worktree_real" == "$repo_real" && "$dry_run" != "1" ]]; then
    die "refusing to remove the current worktree; run from another checkout or use --dry-run"
  fi
  worktree_is_registered "$repo_root" "$worktree_path" \
    || die "worktree path is not registered for this repository: $worktree_path"
  worktree_branch=$(git -C "$worktree_path" branch --show-current)
  [[ "$worktree_branch" == "$branch_name" ]] \
    || die "worktree branch is $worktree_branch, expected $branch_name"
  if [[ -n "$(git -C "$worktree_path" status --porcelain)" ]]; then
    die "worktree is not clean: $worktree_path"
  fi
fi

if [[ "$dry_run" != "1" && -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  die "current repository is not clean; commit or discard local changes before cleanup"
fi

printf '%s\n' "Issue: #$issue_number $issue_title"
printf '%s\n' "Issue URL: $issue_url"
printf '%s\n' "PR: #$pr_number $pr_url"
printf '%s\n' "Branch: $branch_name"
printf '%s\n' "CI checks verified: $check_count"
printf '%s\n' "Worktree: $worktree_path"

if [[ "$dry_run" == "1" ]]; then
  printf '%s\n' "DRY RUN"
  if [[ "$worktree_exists" == "1" ]]; then
    printf '%s\n' "Would remove worktree: $worktree_path"
  else
    printf '%s\n' "No local worktree found; would skip worktree removal."
  fi
  if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
    printf '%s\n' "Would delete local branch: $branch_name"
  else
    printf '%s\n' "No local branch found; would skip branch deletion."
  fi
  printf '%s\n' "Would remove active status labels and move project item to Done."
  exit 0
fi

if [[ "$worktree_exists" == "1" ]]; then
  git -C "$repo_root" worktree remove "$worktree_path"
  printf '%s\n' "Removed worktree: $worktree_path"
else
  warn "worktree path does not exist; skipping worktree removal: $worktree_path"
fi

if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
  git -C "$repo_root" branch -D "$branch_name" >/dev/null
  printf '%s\n' "Deleted local branch: $branch_name"
else
  warn "local branch does not exist; skipping branch deletion: $branch_name"
fi

remove_status_labels
move_project_done

printf '%s\n' "Finish workflow complete."
