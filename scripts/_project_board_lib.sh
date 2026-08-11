# shellcheck shell=bash

json_project_status_ids() {
  local payload="$1"
  local option_name="$2"
  printf '%s' "$payload" | uv run python -c '
import json
import sys

data = json.load(sys.stdin)
option_name = sys.argv[1]
for field in data.get("fields", []):
    if field.get("name") != "Status":
        continue
    for option in field.get("options", []):
        if option.get("name") == option_name:
            print(field.get("id", ""))
            print(option.get("id", ""))
            raise SystemExit(0)
raise SystemExit(1)
' "$option_name"
}

json_current_issue_project_item_id() {
  local payload="$1"
  local project_id="$2"
  printf '%s' "$payload" | uv run python -c '
import json
import sys

try:
    data = json.load(sys.stdin)
    nodes = data["data"]["repository"]["issue"]["projectItems"]["nodes"]
except (KeyError, TypeError, json.JSONDecodeError):
    raise SystemExit(2)
if not isinstance(nodes, list):
    raise SystemExit(2)
project_id = sys.argv[1]
for item in nodes:
    if not isinstance(item, dict):
        continue
    project = item.get("project")
    if not isinstance(project, dict) or project.get("id") != project_id:
        continue
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise SystemExit(2)
    print(item_id)
    raise SystemExit(0)
raise SystemExit(1)
' "$project_id"
}

project_item_id_for_issue() {
  local repo_full_name="$1"
  local project_id="$2"
  local issue_number="$3"
  local repo_owner
  local repo_name
  local items_json

  if [[ ! "$repo_full_name" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    return 2
  fi
  repo_owner="${repo_full_name%%/*}"
  repo_name="${repo_full_name#*/}"
  # GraphQL variable names in the query must remain literal.
  # shellcheck disable=SC2016
  if ! items_json=$(gh api graphql \
    -F owner="$repo_owner" \
    -F name="$repo_name" \
    -F number="$issue_number" \
    -f query='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){issue(number:$number){projectItems(first:10){nodes{id project{id}}}}}}' \
    2>/dev/null); then
    return 2
  fi
  json_current_issue_project_item_id "$items_json" "$project_id"
}

retry_project_item_id() {
  local repo_full_name="$1"
  local project_id="$2"
  local issue_number="$3"
  local attempts="${ENTROPING_PROJECT_ITEM_LOOKUP_RETRIES:-3}"
  local delay_seconds="${ENTROPING_PROJECT_ITEM_LOOKUP_RETRY_DELAY_SECONDS:-1}"
  local attempt
  local item_id

  if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]]; then
    attempts="3"
  fi
  if [[ ! "$delay_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    delay_seconds="1"
  fi
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    local item_lookup_status=0
    item_id=$(project_item_id_for_issue "$repo_full_name" "$project_id" "$issue_number") \
      || item_lookup_status=$?
    if [[ "$item_lookup_status" == "0" ]]; then
      printf '%s\n' "$item_id"
      return 0
    fi
    if [[ "$item_lookup_status" == "2" ]]; then
      return 2
    fi
    if ((attempt < attempts)); then
      sleep "$delay_seconds"
    fi
  done
  return 1
}

project_graphql_quota_allows_update() {
  local minimum_remaining="${ENTROPING_PROJECT_GRAPHQL_MIN_REMAINING:-50}"
  local remaining

  if [[ ! "$minimum_remaining" =~ ^[0-9]+$ ]]; then
    minimum_remaining="50"
  fi

  if ! remaining=$(gh api rate_limit --jq '.resources.graphql.remaining' 2>/dev/null); then
    return 0
  fi
  if [[ ! "$remaining" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  if ((remaining < minimum_remaining)); then
    warn "GitHub Project GraphQL quota is low ($remaining remaining; need at least $minimum_remaining); skipping Project board update"
    return 1
  fi
  return 0
}
