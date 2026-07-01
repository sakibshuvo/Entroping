# shellcheck shell=bash

project_item_list_limit() {
  local limit="${ENTROPING_PROJECT_ITEM_LIST_LIMIT:-1000}"
  if [[ ! "$limit" =~ ^[1-9][0-9]*$ ]]; then
    limit="1000"
  fi
  printf '%s\n' "$limit"
}

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

retry_project_item_id() {
  local project_number="$1"
  local project_owner="$2"
  local issue_number="$3"
  local attempts="${ENTROPING_PROJECT_ITEM_LOOKUP_RETRIES:-3}"
  local delay_seconds="${ENTROPING_PROJECT_ITEM_LOOKUP_RETRY_DELAY_SECONDS:-1}"
  local attempt
  local items_json
  local item_id
  local item_list_limit

  if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]]; then
    attempts="3"
  fi
  if [[ ! "$delay_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    delay_seconds="1"
  fi
  item_list_limit=$(project_item_list_limit)

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if ! items_json=$(gh project item-list "$project_number" --owner "$project_owner" --limit "$item_list_limit" --format json 2>/dev/null); then
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
