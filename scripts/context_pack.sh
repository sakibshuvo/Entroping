#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/context_pack.sh [--mode implementation|review|source|growth|handoff] [--manifest] [--strict-budget] [--record-factory-metrics]

Print a curated Entroping context pack for Codex, Claude Code, OpenCode,
Gemini, NotebookLM, local Qwen, or another coding/review agent.

Default to the repo-native context budget baseline: start with a named issue
question; use rg, this context pack, the decision registry, GitHub issue
evidence, source files, focused tests, CI, and factory metrics. Do not add
generated context because it is interesting, visual, popular, or already
installed.

Modes:
  implementation  Default. Rules, current plan, MVP, TDS, command surface, tests.
  review          Diff/review-oriented rules, progress, changelog, lessons, tests.
  source          Decision registry, source reconciliation, and product evolution.
  growth          Public open-source positioning, launch, and monetization context.
  handoff         Compact continuity pack for starting a new agent/chat session.

The pack is written to stdout. Redirect it to a temp file when needed:

  scripts/context_pack.sh --mode implementation > /tmp/entroping-context.md

Print only a JSON manifest with file inventory, byte counts, estimated tokens,
budget status, and next-action guidance when an agent needs retrieval planning
without loading the full context body:

  scripts/context_pack.sh --mode implementation --manifest

Use --strict-budget to fail when the generated pack exceeds its mode budget.
Budget overrides are available for local experiments and tests with
ENTROPING_CONTEXT_PACK_BUDGET_<MODE>, for example:

  ENTROPING_CONTEXT_PACK_BUDGET_IMPLEMENTATION=330000 scripts/context_pack.sh --mode implementation --strict-budget

Opt into ignored local software-factory metrics when measuring context cost:

  scripts/context_pack.sh --mode implementation --record-factory-metrics

Use --factory-role to override the default metrics role (`integrator`) and
--factory-metrics-ledger to choose a ledger under `.entroping/factory-metrics/`.
The ledger records byte and file counts only, not the generated context pack.

For source reconciliation, set ENTROPING_SOURCE_ROOT when the source archive is
not a sibling directory named entroping-specs:

  ENTROPING_SOURCE_ROOT=/path/to/entroping-specs scripts/context_pack.sh --mode source

Do not commit generated context packs. Promote durable changes into curated
Markdown, ADRs, GitHub issues, tests, or scripts instead.
EOF
}

die() {
  printf 'context_pack: %s\n' "$*" >&2
  exit 2
}

mode="implementation"
manifest=false
strict_budget=false
record_factory_metrics=false
factory_role="integrator"
factory_metrics_ledger=""

while (($#)); do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || die "--mode requires a value"
      mode="$2"
      shift 2
      ;;
    --manifest)
      manifest=true
      shift
      ;;
    --strict-budget)
      strict_budget=true
      shift
      ;;
    --record-factory-metrics)
      record_factory_metrics=true
      shift
      ;;
    --factory-role)
      [[ $# -ge 2 ]] || die "--factory-role requires a value"
      factory_role="$2"
      shift 2
      ;;
    --factory-metrics-ledger)
      [[ $# -ge 2 ]] || die "--factory-metrics-ledger requires a value"
      factory_metrics_ledger="$2"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

case "$mode" in
  implementation|review|source|growth|handoff)
    ;;
  *)
    die "unknown mode: $mode"
    ;;
esac

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || die "run this from inside the Entroping git repository"
cd "$repo_root"

default_source_root="$(cd "$repo_root/.." && pwd)/entroping-specs"
source_root="${ENTROPING_SOURCE_ROOT:-$default_source_root}"
if [[ "$source_root" != /* ]]; then
  source_root="$repo_root/$source_root"
fi
if [[ -d "$source_root" ]]; then
  source_root="$(cd "$source_root" && pwd)"
fi
files=()

add_file() {
  local path="$1"
  local existing
  if ((${#files[@]})); then
    for existing in "${files[@]}"; do
      [[ "$existing" == "$path" ]] && return 0
    done
  fi
  files+=("$path")
}

add_base_files() {
  add_file "AGENTS.md"
  add_file "docs/meta/DECISION_REGISTRY.yaml"
  add_file ".context/plan.md"
  add_file "docs/meta/PROJECT_PROGRESS.md"
}

add_base_files

case "$mode" in
  implementation)
    add_file "docs/meta/FEATURE_DELIVERY_CHECKLIST.md"
    add_file "docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md"
    add_file "docs/product/MVP_PLAN.md"
    add_file "docs/technical/TDS.md"
    add_file "docs/technical/COMMAND_CHEAT_SHEET.md"
    add_file "docs/meta/TEST_STRATEGY.md"
    ;;
  review)
    add_file ".context/changelog.md"
    add_file ".context/lessons-learned.md"
    add_file "docs/meta/FEATURE_DELIVERY_CHECKLIST.md"
    add_file "docs/meta/TEST_STRATEGY.md"
    add_file "docs/meta/AGENT_CONTROL_PLANE.md"
    add_file ".github/pull_request_template.md"
    ;;
  source)
    add_file "docs/meta/VAULT_INDEX.md"
    add_file "sources/SOURCE_MAP.md"
    add_file "docs/meta/KNOWLEDGE_BASE_WORKFLOW.md"
    add_file "docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE.md"
    add_file "docs/evolution/REQUIREMENTS_ANALYSIS.md"
    add_file "docs/evolution/EVOLUTION_TIMELINE.md"
    add_file "docs/evolution/CREATOR_INTENT_AUDIT.md"
    ;;
  growth)
    add_file "README.md"
    add_file "docs/product/PRODUCT_SPEC.md"
    add_file "docs/product/MARKETING_NOTE.md"
    add_file "docs/product/GROWTH_AND_MONETIZATION.md"
    add_file "docs/meta/RELEASE_CHECKLIST.md"
    add_file "CONTRIBUTING.md"
    add_file "SECURITY.md"
    ;;
  handoff)
    add_file "docs/meta/VAULT_INDEX.md"
    add_file "docs/meta/FEATURE_DELIVERY_CHECKLIST.md"
    add_file ".context/changelog.md"
    add_file ".context/lessons-learned.md"
    add_file "docs/meta/CONTEXT_MANAGEMENT.md"
    add_file "docs/meta/AGENT_CONTROL_PLANE.md"
    add_file "docs/meta/KNOWLEDGE_BASE_WORKFLOW.md"
    add_file "docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE.md"
    ;;
esac

branch="$(git branch --show-current 2>/dev/null || true)"
status="$(git status --short 2>/dev/null || true)"
status_line_limit=10

mode_budget_bytes() {
  local default_budget
  local upper_mode
  local env_name
  local override

  case "$mode" in
    implementation)
      default_budget=330000
      ;;
    review)
      default_budget=405000
      ;;
    source)
      default_budget=225000
      ;;
    growth)
      default_budget=250000
      ;;
    handoff)
      default_budget=425000
      ;;
    *)
      die "unknown mode: $mode"
      ;;
  esac

  upper_mode="$(printf '%s' "$mode" | tr '[:lower:]' '[:upper:]')"
  env_name="ENTROPING_CONTEXT_PACK_BUDGET_${upper_mode}"
  override="${!env_name:-}"
  if [[ -n "$override" ]]; then
    [[ "$override" =~ ^[0-9]+$ ]] \
      || die "$env_name must be a non-negative integer byte budget"
    printf '%s\n' "$override"
    return 0
  fi

  printf '%s\n' "$default_budget"
}

context_pack_bytes() {
  local pack_file="$1"
  local context_bytes

  context_bytes="$(wc -c < "$pack_file" | tr -d '[:space:]')"
  if [[ -z "$context_bytes" ]]; then
    context_bytes=0
  fi
  printf '%s\n' "$context_bytes"
}

emit_git_status_block() {
  local line_count
  local omitted_count

  if [[ -z "$status" ]]; then
    printf "\`\`\`text\nworking tree clean\n\`\`\`\n\n"
    return 0
  fi

  line_count="$(printf '%s\n' "$status" | wc -l | tr -d '[:space:]')"
  printf "\`\`\`text\n"
  if ((line_count > status_line_limit)); then
    printf '%s\n' "$status" | sed -n "1,${status_line_limit}p"
    omitted_count=$((line_count - status_line_limit))
    printf '... %s additional status line(s) omitted; run git status --short for the full list.\n' "$omitted_count"
  else
    printf '%s\n' "$status"
  fi
  printf "\`\`\`\n\n"
}

file_reason() {
  local path="$1"

  case "$path" in
    AGENTS.md)
      printf 'agent-rules\n'
      ;;
    docs/meta/DECISION_REGISTRY.yaml)
      printf 'decision-registry\n'
      ;;
    .context/plan.md)
      printf 'active-plan\n'
      ;;
    docs/meta/PROJECT_PROGRESS.md)
      printf 'project-progress\n'
      ;;
    docs/meta/FEATURE_DELIVERY_CHECKLIST.md)
      printf 'delivery-checklist\n'
      ;;
    docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md)
      printf 'autonomous-workflow\n'
      ;;
    docs/product/MVP_PLAN.md)
      printf 'mvp-scope\n'
      ;;
    docs/technical/TDS.md)
      printf 'architecture\n'
      ;;
    docs/technical/COMMAND_CHEAT_SHEET.md)
      printf 'command-surface\n'
      ;;
    docs/meta/TEST_STRATEGY.md)
      printf 'test-strategy\n'
      ;;
    .context/changelog.md)
      printf 'context-changelog\n'
      ;;
    .context/lessons-learned.md)
      printf 'lessons-learned\n'
      ;;
    .github/pull_request_template.md)
      printf 'pr-evidence-template\n'
      ;;
    docs/meta/AGENT_CONTROL_PLANE.md)
      printf 'agent-control-plane\n'
      ;;
    docs/meta/VAULT_INDEX.md)
      printf 'vault-index\n'
      ;;
    sources/SOURCE_MAP.md)
      printf 'source-map\n'
      ;;
    docs/meta/KNOWLEDGE_BASE_WORKFLOW.md)
      printf 'knowledge-base-workflow\n'
      ;;
    docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE.md)
      printf 'obsidian-context-guide\n'
      ;;
    docs/evolution/REQUIREMENTS_ANALYSIS.md)
      printf 'requirements-evidence\n'
      ;;
    docs/evolution/EVOLUTION_TIMELINE.md)
      printf 'evolution-timeline\n'
      ;;
    docs/evolution/CREATOR_INTENT_AUDIT.md)
      printf 'creator-intent-audit\n'
      ;;
    README.md)
      printf 'public-positioning\n'
      ;;
    docs/product/PRODUCT_SPEC.md)
      printf 'product-spec\n'
      ;;
    docs/product/MARKETING_NOTE.md)
      printf 'marketing-note\n'
      ;;
    docs/product/GROWTH_AND_MONETIZATION.md)
      printf 'growth-monetization\n'
      ;;
    docs/meta/RELEASE_CHECKLIST.md)
      printf 'release-checklist\n'
      ;;
    CONTRIBUTING.md)
      printf 'contribution-rules\n'
      ;;
    SECURITY.md)
      printf 'security-policy\n'
      ;;
    docs/meta/CONTEXT_MANAGEMENT.md)
      printf 'context-management\n'
      ;;
    *)
      die "missing context manifest reason for: $path"
      ;;
  esac
}

emit_context_pack() {
  printf '# Entroping Agent Context Pack\n\n'
  printf '%s\n' "- Mode: $mode"
  printf '%s\n' "- Repo: $repo_root"
  printf '%s\n' "- Branch: ${branch:-detached}"
  printf '%s\n' "- Source archive: $source_root"
  printf '%s\n\n' "- Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  cat <<'EOF'
## Required Agent Rules

- Codex is the primary integrator unless a human explicitly assigns another parent integrator.
- No helper agent is a source of truth. Local files, tests, GitHub issues, ADRs, and CI decide.
- Use `docs/meta/DECISION_REGISTRY.yaml` as the fast durable-decision index; follow its links back to source material before treating summaries as truth.
- Preserve the locked v4.1 command surface unless the product docs and ADRs are updated first.
- Keep `entroping run` deterministic and LLM-free.
- Treat captured traffic, model output, YAML, paths, globs, and subprocess output as untrusted inputs.
- Historical source material is evidence, not automatic current truth.
- The NotebookLM Markdown export is the primary current source snapshot.

## Current Git Status

EOF

  emit_git_status_block

  if [[ "$mode" == "source" ]]; then
    cat <<EOF
## Source Archive Rule

The final source snapshot currently lives at:

\`\`\`text
$source_root/notebookLM/2026-05-29 NotebookLM Specs.md
\`\`\`

Older Gemini and NotebookLM exports remain archival references. Promote source
evidence through a GitHub issue, ADR, canonical product/technical doc, or
context note before implementation.

EOF
  fi

  printf '## Curated Files\n\n'

  for path in "${files[@]}"; do
    if [[ ! -f "$path" ]]; then
      die "required context file is missing: $path"
    fi
    printf '### %s\n\n' "$path"
    sed 's/[[:space:]]*$//' "$path"
    printf '\n\n'
  done
}

emit_context_pack_manifest() {
  local pack_file="$1"
  local budget_bytes="$2"
  local manifest_args
  local path
  local reason

  manifest_args=(
    "$mode"
    "$repo_root"
    "${branch:-detached}"
    "$source_root"
    "$budget_bytes"
    "$pack_file"
  )
  for path in "${files[@]}"; do
    reason="$(file_reason "$path")"
    manifest_args+=("$path" "$reason")
  done

  python3 - "${manifest_args[@]}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

mode, repo, branch, source_root, budget_raw, pack_file, *raw_files = sys.argv[1:]
budget_bytes = int(budget_raw)
context_bytes = os.path.getsize(pack_file)
estimated_tokens = max(1, (context_bytes + 3) // 4)
budget_status = "pass" if context_bytes <= budget_bytes else "fail"

files = []
for index in range(0, len(raw_files), 2):
    path = raw_files[index]
    reason = raw_files[index + 1]
    file_path = Path(path)
    files.append(
        {
            "path": path,
            "bytes": file_path.stat().st_size,
            "reason": reason,
        }
    )

if budget_status == "pass":
    recommended_next_action = {
        "action": "targeted_file_reads",
        "full_pack_allowed": True,
        "reason": "Manifest is within the mode budget; read only files relevant to the issue before loading the full pack.",
        "steps": [
            "Start from the named issue or review question.",
            "Use files[].path and files[].reason to choose the smallest useful read set.",
            "Use rg and the decision registry before opening broad historical docs.",
            "Load the full context pack only when targeted reads are insufficient.",
        ],
    }
else:
    recommended_next_action = {
        "action": "reduce_scope",
        "full_pack_allowed": False,
        "reason": "Manifest exceeds the mode budget; do not load the full context pack.",
        "steps": [
            "Switch to a narrower mode or a smaller issue question.",
            "Read only files[].path entries that match the issue scope.",
            "Use rg for exact symbol or phrase lookup before broad file reads.",
            "Record the budget failure in factory metrics or the worker handoff.",
        ],
    }

manifest = {
    "schema": "entroping.context-pack-manifest.v1",
    "mode": mode,
    "repo": repo,
    "branch": branch,
    "source_archive": source_root,
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "file_count": len(files),
    "files": files,
    "context_bytes": context_bytes,
    "estimated_tokens": estimated_tokens,
    "budget_bytes": budget_bytes,
    "budget_status": budget_status,
    "recommended_next_action": recommended_next_action,
}

print(json.dumps(manifest, indent=2, sort_keys=True))
PY
}

enforce_context_pack_budget() {
  local pack_file="$1"
  local budget_bytes="$2"
  local context_bytes

  context_bytes="$(context_pack_bytes "$pack_file")"
  if ((context_bytes > budget_bytes)); then
    printf 'context_pack: %s context pack exceeds budget: %s bytes > %s byte budget\n' \
      "$mode" "$context_bytes" "$budget_bytes" >&2
    return 1
  fi
}

record_context_pack_metrics() {
  local pack_file="$1"
  local context_bytes
  local estimated_tokens
  local metrics_output
  local metrics_args

  context_bytes="$(context_pack_bytes "$pack_file")"
  estimated_tokens=$(((context_bytes + 3) / 4))
  if ((estimated_tokens < 1)); then
    estimated_tokens=1
  fi

  metrics_args=(
    python3 scripts/factory_metrics.py
    --repo-root "$repo_root"
    append
    --event-type context_pack
    --role "$factory_role"
    --agent Codex
    --tool scripts/context_pack.sh
    --worktree "$repo_root"
    --context-bytes "$context_bytes"
    --estimated-tokens "$estimated_tokens"
    --candidate-files "${#files[@]}"
    --files-read "${#files[@]}"
    --outcome success
    --decision not_applicable
    --note "mode=$mode"
    --json
  )
  if [[ -n "$factory_metrics_ledger" ]]; then
    metrics_args+=(--ledger "$factory_metrics_ledger")
  fi

  if ! metrics_output="$("${metrics_args[@]}" 2>&1)"; then
    printf 'context_pack: factory metrics warning: %s\n' "$metrics_output" >&2
  fi
}

if [[ "$record_factory_metrics" == "true" || "$manifest" == "true" || "$strict_budget" == "true" ]]; then
  tmp_pack="$(mktemp "${TMPDIR:-/tmp}/entroping-context-pack.XXXXXX")"
  cleanup_context_pack_metrics() {
    rm -f "$tmp_pack"
  }
  trap cleanup_context_pack_metrics EXIT
  emit_context_pack > "$tmp_pack"

  budget_bytes="$(mode_budget_bytes)"

  if [[ "$manifest" == "true" ]]; then
    emit_context_pack_manifest "$tmp_pack" "$budget_bytes"
  fi

  if [[ "$strict_budget" == "true" ]]; then
    enforce_context_pack_budget "$tmp_pack" "$budget_bytes" || exit 2
  fi

  if [[ "$manifest" != "true" ]]; then
    cat "$tmp_pack"
  fi

  if [[ "$record_factory_metrics" == "true" ]]; then
    record_context_pack_metrics "$tmp_pack"
  fi
else
  emit_context_pack
fi
