#!/usr/bin/env bash
set -euo pipefail

show_help() {
  cat <<'EOF'
Usage: scripts/context_pack.sh [--mode implementation|review|source|growth|handoff] [--record-factory-metrics]

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
  add_file "README.md"
  add_file "docs/meta/VAULT_INDEX.md"
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
    add_file "sources/SOURCE_MAP.md"
    add_file "docs/meta/KNOWLEDGE_BASE_WORKFLOW.md"
    add_file "docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE.md"
    add_file "docs/evolution/REQUIREMENTS_ANALYSIS.md"
    add_file "docs/evolution/EVOLUTION_TIMELINE.md"
    add_file "docs/evolution/CREATOR_INTENT_AUDIT.md"
    ;;
  growth)
    add_file "docs/product/PRODUCT_SPEC.md"
    add_file "docs/product/MARKETING_NOTE.md"
    add_file "docs/product/GROWTH_AND_MONETIZATION.md"
    add_file "docs/meta/RELEASE_CHECKLIST.md"
    add_file "CONTRIBUTING.md"
    add_file "SECURITY.md"
    ;;
  handoff)
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

  if [[ -n "$status" ]]; then
    printf "\`\`\`text\n%s\n\`\`\`\n\n" "$status"
  else
    printf "\`\`\`text\nworking tree clean\n\`\`\`\n\n"
  fi

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

record_context_pack_metrics() {
  local pack_file="$1"
  local context_bytes
  local estimated_tokens
  local metrics_output
  local metrics_args

  context_bytes="$(wc -c < "$pack_file" | tr -d '[:space:]')"
  if [[ -z "$context_bytes" ]]; then
    context_bytes=0
  fi
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

if [[ "$record_factory_metrics" == "true" ]]; then
  tmp_pack="$(mktemp "${TMPDIR:-/tmp}/entroping-context-pack.XXXXXX")"
  cleanup_context_pack_metrics() {
    rm -f "$tmp_pack"
  }
  trap cleanup_context_pack_metrics EXIT
  emit_context_pack > "$tmp_pack"
  cat "$tmp_pack"
  record_context_pack_metrics "$tmp_pack"
else
  emit_context_pack
fi
