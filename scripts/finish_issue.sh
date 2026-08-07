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
  --keep-worktree   Verify merged issue, PR, and CI but leave local cleanup
                   state untouched for post-merge diagnostics.
  --worktree PATH   Override the issue worktree path.
  --expected-pr N   Strict controller contract: require this exact PR.
  --expected-head SHA
                   Strict controller contract: require this exact PR head.
  --expected-branch NAME
                   Strict controller contract: require this exact branch.
  --aggregate-evidence PATH
                   Use the tracked aggregate-PR evidence manifest at PATH.
  -h, --help        Show this help text.

Environment:
  ENTROPING_REPO             GitHub repo. Default: sakibshuvo/Entroping
  ENTROPING_PROJECT_OWNER    GitHub project owner. Default: sakibshuvo
  ENTROPING_PROJECT_NUMBER   GitHub project number. Default: 1
  ENTROPING_PROJECT_ITEM_LIST_LIMIT
                            Project item lookup window. Default: 1000
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

controller_mode="0"
if [[ -n "${ENTROPING_FINISH_SCRIPT_DIR:-}" \
  || -n "${ENTROPING_FINISH_PROJECT_LIB:-}" \
  || -n "${ENTROPING_FINISH_METRICS_HELPER:-}" \
  || -n "${ENTROPING_FINISH_REPLAY_HELPER:-}" ]]; then
  [[ -z "${ENTROPING_FINISH_SCRIPT_DIR:-}" \
    && "${ENTROPING_FINISH_PROJECT_LIB:-}" =~ ^/dev/fd/[1-9][0-9]*$ \
    && "${ENTROPING_FINISH_METRICS_HELPER:-}" =~ ^/dev/fd/[1-9][0-9]*$ \
    && "${ENTROPING_FINISH_REPLAY_HELPER:-}" =~ ^/dev/fd/[1-9][0-9]*$ \
    && "$ENTROPING_FINISH_PROJECT_LIB" != "$ENTROPING_FINISH_METRICS_HELPER" \
    && "$ENTROPING_FINISH_PROJECT_LIB" != "$ENTROPING_FINISH_REPLAY_HELPER" \
    && "$ENTROPING_FINISH_METRICS_HELPER" != "$ENTROPING_FINISH_REPLAY_HELPER" ]] \
    || die "internal finish helper capabilities are invalid"
  controller_mode="1"
else
  script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
fi

run_python_helper() {
  local helper_name="$1"
  shift
  if [[ "$controller_mode" == "1" ]]; then
    local helper_path
    case "$helper_name" in
      factory_metrics_archive.py)
        helper_path="$ENTROPING_FINISH_METRICS_HELPER"
        ;;
      finish_issue_replay_evidence.py)
        helper_path="$ENTROPING_FINISH_REPLAY_HELPER"
        ;;
      *)
        die "internal finish helper is unavailable"
        ;;
    esac
    python3 -c '
import os
import sys

descriptor = int(sys.argv[1])
os.lseek(descriptor, 0, os.SEEK_SET)
try:
    sys.argv = [sys.argv[2], *sys.argv[3:]]
    payload = bytearray()
    while chunk := os.read(descriptor, 65_536):
        payload.extend(chunk)
    capability = f"/dev/fd/{descriptor}"
    namespace = {
        "__name__": "__main__",
        "__file__": capability,
        "__package__": None,
        "__cached__": None,
    }
    exec(compile(bytes(payload), capability, "exec"), namespace)
finally:
    os.lseek(descriptor, 0, os.SEEK_SET)
' "${helper_path#/dev/fd/}" "$helper_name" "$@"
  else
    python3 "$script_dir/$helper_name" "$@"
  fi
}

# shellcheck source=scripts/_project_board_lib.sh
if [[ "$controller_mode" == "1" ]]; then
  source "$ENTROPING_FINISH_PROJECT_LIB"
else
  source "$script_dir/_project_board_lib.sh"
fi

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
        if state not in {"SUCCESS", "COMPLETED"} or conclusion not in allowed_check_run_conclusions:
            bad.append(f"{name}: unrecognized check state")

if bad:
    print("closing PR has non-passing checks:", file=sys.stderr)
    for item in bad:
        print(f"  {item}", file=sys.stderr)
    raise SystemExit(1)

print(len(checks))
'
}

canonical_path() {
  (cd "$1" && pwd -P)
}

worktree_registration_probe() {
  local repo_root="$1"
  local worktree_path="$2"
  local listing
  local parser_status
  if ! listing=$(git -C "$repo_root" worktree list --porcelain 2>/dev/null); then
    return 2
  fi
  if printf '%s\n' "$listing" | python3 -c '
from __future__ import annotations

import os
import sys

target = os.path.realpath(sys.argv[1])
seen = False
for line in sys.stdin:
    if not line.startswith("worktree "):
        continue
    value = line.removeprefix("worktree ").strip()
    if not value:
        raise SystemExit(2)
    seen = True
    candidate = os.path.realpath(value)
    if candidate == target:
        raise SystemExit(0)
if not seen:
    raise SystemExit(2)
raise SystemExit(1)
' "$worktree_path"; then
    return 0
  else
    parser_status=$?
  fi
  [[ "$parser_status" == "1" ]] && return 1
  return 2
}

local_branch_probe() {
  local repo_root="$1"
  local branch="$2"
  local probe_status
  if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch" 2>/dev/null; then
    return 0
  else
    probe_status=$?
  fi
  [[ "$probe_status" == "1" ]] && return 1
  return 2
}

preserve_factory_metrics() {
  local worktree_path="$1"
  local repo_root="$2"
  local issue_number="$3"
  local dry_run="$4"
  local pr_number="$5"
  local merged_at="$6"
  local -a archive_args=(
    --repo-root "$repo_root"
    --source-worktree "$worktree_path"
    --issue "$issue_number"
    --pull-request "$pr_number"
    --archived-at "$merged_at"
  )
  if [[ "$dry_run" == "1" ]]; then
    archive_args+=(--dry-run)
  fi
  run_python_helper "factory_metrics_archive.py" "${archive_args[@]}"
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
  local item_list_limit

  project_graphql_quota_allows_update || return 0

  if ! project_json=$(gh project view "$project_number" --owner "$project_owner" --format json 2>/dev/null); then
    warn "could not read GitHub Project board"
    return 0
  fi
  project_id=$(json_key "$project_json" "id")

  if ! fields_json=$(gh project field-list "$project_number" --owner "$project_owner" --format json 2>/dev/null); then
    warn "could not read GitHub Project fields"
    return 0
  fi
  if ! ids=$(json_project_status_ids "$fields_json" "Done"); then
    warn "could not find Project Status/Done field option"
    return 0
  fi
  status_field_id=$(printf '%s\n' "$ids" | sed -n '1p')
  done_option_id=$(printf '%s\n' "$ids" | sed -n '2p')

  item_list_limit=$(project_item_list_limit)
  if ! items_json=$(gh project item-list "$project_number" --owner "$project_owner" --limit "$item_list_limit" --format json 2>/dev/null); then
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
keep_worktree="0"
worktree_override=""
expected_pr=""
expected_head=""
expected_branch=""
aggregate_manifest=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run="1"
      shift
      ;;
    --keep-worktree)
      keep_worktree="1"
      shift
      ;;
    --worktree)
      [[ $# -ge 2 ]] || die "--worktree requires a path"
      worktree_override="$2"
      shift 2
      ;;
    --expected-pr)
      [[ $# -ge 2 ]] || die "--expected-pr requires a number"
      expected_pr="$2"
      shift 2
      ;;
    --expected-head)
      [[ $# -ge 2 ]] || die "--expected-head requires a commit"
      expected_head="$2"
      shift 2
      ;;
    --expected-branch)
      [[ $# -ge 2 ]] || die "--expected-branch requires a branch"
      expected_branch="$2"
      shift 2
      ;;
    --aggregate-evidence)
      [[ $# -ge 2 ]] || die "--aggregate-evidence requires a path"
      aggregate_manifest="$2"
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

if [[ "$dry_run" == "1" && "$keep_worktree" == "1" ]]; then
  die "--dry-run and --keep-worktree cannot be combined"
fi

strict_cleanup="0"
aggregate_mode="0"
if [[ -n "$aggregate_manifest" ]]; then
  [[ -z "$expected_pr" && -z "$expected_head" && -z "$expected_branch" ]] \
    || die "--aggregate-evidence cannot be combined with --expected-pr, --expected-head, or --expected-branch"
  [[ "$controller_mode" == "0" ]] \
    || die "aggregate evidence is unavailable through pinned controller capabilities"
  aggregate_mode="1"
  strict_cleanup="1"
elif [[ -n "$expected_pr" || -n "$expected_head" || -n "$expected_branch" ]]; then
  [[ -n "$expected_pr" && -n "$expected_head" && -n "$expected_branch" ]] \
    || die "--expected-pr, --expected-head, and --expected-branch must be supplied together"
  [[ "$expected_pr" =~ ^[1-9][0-9]*$ ]] || die "--expected-pr must be a positive integer"
  [[ "$expected_head" =~ ^[0-9a-f]{40}$ ]] || die "--expected-head must be a commit SHA"
  [[ "$expected_branch" != "main" && "$expected_branch" != "master" ]] \
    || die "--expected-branch must not be the base branch"
  [[ "$expected_branch" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{2,159}$ ]] \
    || die "--expected-branch has invalid syntax"
  strict_cleanup="1"
fi

[[ "$issue_number" =~ ^[1-9][0-9]*$ ]] || die "issue-number must be a positive integer"
command -v git >/dev/null 2>&1 || die "git is required"
command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required"
command -v uv >/dev/null 2>&1 || die "uv is required"
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
if [[ "$aggregate_mode" == "1" ]]; then
  aggregate_payload=$(run_python_helper "finish_issue_aggregate.py" \
    --repo-root "$repo_root" \
    --repo "$repo" \
    --worktree "$worktree_path" \
    --issue "$issue_number" \
    --manifest "$aggregate_manifest" 2>/dev/null) \
    || die "aggregate evidence is invalid or unsafe"
  issue_title=$(json_key "$aggregate_payload" "issue_title")
  issue_url=$(json_key "$aggregate_payload" "issue_url")
  issue_state="CLOSED"
  pr_number=$(json_key "$aggregate_payload" "aggregate_pr_number")
  pr_url=$(json_key "$aggregate_payload" "aggregate_pr_url")
  branch_name=$(json_key "$aggregate_payload" "source_branch")
  merged_at=$(json_key "$aggregate_payload" "merged_at")
  expected_pr="$pr_number"
  expected_head=$(json_key "$aggregate_payload" "source_commit")
  expected_branch="$branch_name"
  check_count=$(json_key "$aggregate_payload" "check_count")
else
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
    --json number,url,state,headRefName,headRefOid,mergedAt,statusCheckRollup) \
    || die "could not read closing PR #$pr_number"
  pr_state=$(json_key "$pr_json" "state")
  pr_url=$(json_key "$pr_json" "url")
  branch_name=$(json_key "$pr_json" "headRefName")
  merged_at=$(json_key "$pr_json" "mergedAt")
  [[ "$pr_state" == "MERGED" && -n "$merged_at" ]] || die "closing PR #$pr_number is not merged"
  [[ -n "$branch_name" ]] || die "closing PR #$pr_number has no head branch name"
  if [[ "$strict_cleanup" == "1" ]]; then
    [[ "$pr_number" == "$expected_pr" ]] || die "closing PR identity does not match expected PR"
    [[ "$branch_name" == "$expected_branch" ]] || die "closing PR branch does not match expected branch"
    [[ "$(json_key "$pr_json" "headRefOid")" == "$expected_head" ]] \
      || die "closing PR head does not match expected head"
    closing_count=$(printf '%s' "$issue_json" | python3 -c '
import json, sys
refs = json.load(sys.stdin).get("closedByPullRequestsReferences") or []
print(len(refs))
    ')
    [[ "$closing_count" == "1" ]] || die "issue must have exactly one closing pull request"
  fi
  if ! check_count=$(json_check_rollup_passed "$pr_json"); then
    die "closing PR #$pr_number checks have not all passed"
  fi
fi

if [[ "$strict_cleanup" == "1" ]]; then
  [[ ! -L "$worktree_path" ]] || die "strict cleanup worktree path must not be a symlink"
  worktree_path=$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$worktree_path")
fi

worktree_exists="0"
worktree_registered="0"
worktree_probe_status="0"
worktree_registration_probe "$repo_root" "$worktree_path" || worktree_probe_status=$?
case "$worktree_probe_status" in
  0)
    worktree_registered="1"
    ;;
  1)
    ;;
  *)
    if [[ "$strict_cleanup" == "1" ]]; then
      die "strict cleanup worktree registration probe failed"
    fi
    ;;
esac
if [[ -e "$worktree_path" ]]; then
  worktree_exists="1"
  worktree_real=$(canonical_path "$worktree_path")
  repo_real=$(canonical_path "$repo_root")
  if [[ "$worktree_real" == "$repo_real" && "$dry_run" != "1" && "$keep_worktree" != "1" ]]; then
    die "refusing to remove the current worktree; run from another checkout or use --dry-run"
  fi
  [[ "$worktree_registered" == "1" ]] \
    || die "worktree path is not registered for this repository: $worktree_path"
  worktree_branch=$(git -C "$worktree_path" branch --show-current)
  [[ "$worktree_branch" == "$branch_name" ]] \
    || die "worktree branch is $worktree_branch, expected $branch_name"
  if [[ "$strict_cleanup" == "1" ]]; then
    [[ "$(git -C "$worktree_path" rev-parse HEAD)" == "$expected_head" ]] \
      || die "worktree head does not match expected head"
  fi
  if [[ -n "$(git -C "$worktree_path" status --porcelain)" ]]; then
    die "worktree is not clean: $worktree_path"
  fi
fi

branch_exists="0"
branch_probe_status="0"
local_branch_probe "$repo_root" "$branch_name" || branch_probe_status=$?
case "$branch_probe_status" in
  0)
    branch_exists="1"
    if [[ "$strict_cleanup" == "1" ]]; then
    [[ "$(git -C "$repo_root" rev-parse "refs/heads/$expected_branch")" == "$expected_head" ]] \
      || die "local branch does not match expected head"
    fi
    ;;
  1)
    ;;
  *)
    if [[ "$strict_cleanup" == "1" ]]; then
      die "strict cleanup local branch probe failed"
    fi
    ;;
esac

if [[ "$strict_cleanup" == "1" ]]; then
  replay_helper() {
    local action="$1"
    local requested_stage="${2:-}"
    local output
    local helper_args=(
      "$action"
      --repo-root "$repo_root"
      --issue "$issue_number"
      --pull-request "$pr_number"
      --expected-head "$expected_head"
      --expected-branch "$expected_branch"
      --merged-at "$merged_at"
      --worktree-path "$worktree_path"
    )
    if [[ -n "$requested_stage" ]]; then
      helper_args+=(--stage "$requested_stage")
    fi
    if ! output=$(run_python_helper "finish_issue_replay_evidence.py" "${helper_args[@]}" 2>/dev/null); then
      die "strict cleanup replay evidence is invalid or unsafe"
    fi
    printf '%s' "$output"
  }

  replay_stage=$(replay_helper read)
  case "$replay_stage" in
    none)
      [[ "$worktree_exists" == "1" && "$worktree_registered" == "1" ]] \
        || die "strict cleanup requires the exact worktree on its first attempt"
      [[ "$branch_exists" == "1" ]] \
        || die "strict cleanup requires the exact local branch on its first attempt"
      ;;
    worktree-removal-attempted)
      [[ "$branch_exists" == "1" ]] \
        || die "strict cleanup replay lacks branch deletion evidence"
      if [[ "$worktree_exists" == "0" && "$worktree_registered" != "0" ]]; then
        die "strict cleanup replay has a stale worktree registration"
      fi
      ;;
    branch-deletion-attempted)
      [[ "$worktree_exists" == "0" && "$worktree_registered" == "0" ]] \
        || die "strict cleanup replay has a worktree after branch deletion intent"
      ;;
    remote-branch-deletion-attempted)
      [[ "$worktree_exists" == "0" && "$worktree_registered" == "0" ]] \
        || die "strict cleanup replay has a worktree after remote deletion intent"
      [[ "$branch_exists" == "0" ]] \
        || die "strict cleanup replay has a local branch after remote deletion intent"
      ;;
    *)
      die "strict cleanup replay evidence is invalid or unsafe"
      ;;
  esac

  remote_branch_helper() {
    local action="$1"
    local output
    if ! output=$(run_python_helper "finish_issue_remote_branch.py" \
      "$action" \
      --worktree "$repo_root" \
      --branch "$expected_branch" \
      --expected-head "$expected_head" 2>/dev/null); then
      die "remote source branch evidence is invalid or uncertain"
    fi
    printf '%s' "$output"
  }

  remote_initial=""
  if [[ "$aggregate_mode" == "1" ]]; then
    remote_initial=$(remote_branch_helper observe)
    if [[ "$remote_initial" == "present:"* ]]; then
      remote_initial_head="${remote_initial#present:}"
      [[ "$remote_initial_head" =~ ^[0-9a-f]{40}$ ]] \
        || die "remote source branch observation is invalid"
      [[ "$remote_initial_head" == "$expected_head" ]] \
        || die "remote source branch head does not match expected source commit"
    elif [[ "$remote_initial" != "absent" ]]; then
      die "remote source branch observation is invalid"
    fi
  fi
fi

if [[ "$dry_run" != "1" && "$keep_worktree" != "1" && -n "$(git -C "$repo_root" status --porcelain)" ]]; then
  die "current repository is not clean; commit or discard local changes before cleanup"
fi

printf '%s\n' "Issue: #$issue_number $issue_title"
printf '%s\n' "Issue URL: $issue_url"
printf '%s\n' "PR: #$pr_number $pr_url"
printf '%s\n' "Branch: $branch_name"
printf '%s\n' "CI checks verified: $check_count"
printf '%s\n' "Worktree: $worktree_path"
if [[ "$aggregate_mode" == "1" ]]; then
  printf '%s\n' "Aggregate PR: #$pr_number"
  printf '%s\n' "Aggregate evidence: $aggregate_manifest"
  printf '%s\n' "Aggregate merge commit: $(json_key "$aggregate_payload" "aggregate_merge_commit")"
  printf '%s\n' "Integrated commit: $(json_key "$aggregate_payload" "integrated_commit")"
  printf '%s\n' "Stable patch ID: $(json_key "$aggregate_payload" "patch_id")"
fi

if [[ "$dry_run" == "1" ]]; then
  printf '%s\n' "DRY RUN"
  if [[ "$worktree_exists" == "1" ]]; then
    printf '%s\n' "Would remove worktree: $worktree_path"
    preserve_factory_metrics \
      "$worktree_path" "$repo_root" "$issue_number" "1" "$pr_number" "$merged_at"
  else
    printf '%s\n' "No local worktree found; would skip worktree removal."
  fi
  if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
    printf '%s\n' "Would delete local branch: $branch_name"
  else
    printf '%s\n' "No local branch found; would skip branch deletion."
  fi
  if [[ "$aggregate_mode" == "1" ]]; then
    if [[ "$remote_initial" == "present:"* ]]; then
      printf '%s\n' "Would delete remote source branch: $expected_branch"
    else
      printf '%s\n' "Remote source branch already absent: $expected_branch"
    fi
  fi
  printf '%s\n' "Would remove active status labels and move project item to Done."
  exit 0
fi

if [[ "$keep_worktree" == "1" ]]; then
  printf '%s\n' "KEEP WORKTREE"
  if [[ "$worktree_exists" == "1" ]]; then
    printf '%s\n' "Kept worktree: $worktree_path"
  else
    printf '%s\n' "No local worktree found; skipped worktree cleanup."
  fi
  if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch_name"; then
    printf '%s\n' "Kept local branch: $branch_name"
  else
    printf '%s\n' "No local branch found; skipped branch cleanup."
  fi
  printf '%s\n' "Verified merged issue and CI; kept local cleanup state."
  exit 0
fi

if [[ "$strict_cleanup" == "1" ]]; then
  if [[ "$aggregate_mode" == "1" && "$replay_stage" == "remote-branch-deletion-attempted" ]]; then
    printf '%s\n' "Replaying after verified local cleanup: $worktree_path"
  else
    if [[ "$worktree_exists" == "1" ]]; then
      preserve_factory_metrics \
        "$worktree_path" "$repo_root" "$issue_number" "0" "$pr_number" "$merged_at"
      [[ "$(replay_helper advance worktree-removal-attempted)" == "worktree-removal-attempted" ]] \
        || die "strict cleanup replay evidence is invalid or unsafe"
      git -C "$repo_root" worktree remove "$worktree_path"
      printf '%s\n' "Removed worktree: $worktree_path"
    fi
    [[ ! -e "$worktree_path" && ! -L "$worktree_path" ]] \
      || die "strict cleanup did not remove the exact worktree path"
    post_worktree_probe="0"
    worktree_registration_probe "$repo_root" "$worktree_path" || post_worktree_probe=$?
    case "$post_worktree_probe" in
      0)
        die "strict cleanup did not unregister the exact worktree"
        ;;
      1)
        ;;
      *)
        die "strict cleanup worktree absence verification failed"
        ;;
    esac

    [[ "$(replay_helper advance branch-deletion-attempted)" == "branch-deletion-attempted" ]] \
      || die "strict cleanup replay evidence is invalid or unsafe"
    if [[ "$branch_exists" == "1" ]]; then
      git -C "$repo_root" update-ref -d "refs/heads/$expected_branch" "$expected_head" \
        || die "strict cleanup local branch changed before deletion"
      printf '%s\n' "Deleted local branch: $expected_branch"
    fi
    post_branch_probe="0"
    local_branch_probe "$repo_root" "$expected_branch" || post_branch_probe=$?
    case "$post_branch_probe" in
      0)
        die "strict cleanup did not delete the exact local branch"
        ;;
      1)
        ;;
      *)
        die "strict cleanup local branch absence verification failed"
        ;;
    esac
  fi

  if [[ "$aggregate_mode" == "1" ]]; then
    if [[ "$remote_initial" == "present:"* ]]; then
      [[ "$(replay_helper advance remote-branch-deletion-attempted)" == \
        "remote-branch-deletion-attempted" ]] \
        || die "strict cleanup replay evidence is invalid or unsafe"
      remote_delete_result=$(remote_branch_helper delete)
      [[ "$remote_delete_result" == "deleted" || "$remote_delete_result" == "absent" ]] \
        || die "remote source branch deletion was not proven"
    fi
    remote_final=$(remote_branch_helper observe)
    [[ "$remote_final" == "absent" ]] \
      || die "remote source branch absence was not proven"
    printf '%s\n' "Verified remote source branch absent: $expected_branch"
  fi
else
  if [[ "$worktree_exists" == "1" ]]; then
    preserve_factory_metrics \
      "$worktree_path" "$repo_root" "$issue_number" "0" "$pr_number" "$merged_at"
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
fi

remove_status_labels
move_project_done

printf '%s\n' "Finish workflow complete."
