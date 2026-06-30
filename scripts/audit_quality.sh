#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

show_help() {
  cat <<'EOF'
Usage: scripts/audit_quality.sh [OPTIONS]

Runs the repeatable validation quality audit. This is heavier than
scripts/regression.sh and is meant for marathon validation, release hardening,
and maintenance-risk reviews.

Checks:
  - test taxonomy report under reports/
  - long-file hotspot report under reports/
  - pytest-cov coverage gate with a JSON artifact under reports/
  - script-focused coverage and typing visibility report under reports/
  - radon cyclomatic complexity and maintainability-index audit
  - vulture dead-code discovery with a curated confidence threshold
  - quality trend summary under reports/
  - bounded performance smoke evidence under reports/

Environment thresholds:
  ENTROPING_COVERAGE_FAIL_UNDER  Minimum total coverage. Default: 100.
  ENTROPING_MAX_COMPLEXITY_RANK  Highest allowed Radon CC rank. Default: D.
  ENTROPING_MIN_MI_RANK          Lowest allowed Radon MI rank. Default: C.
  ENTROPING_VULTURE_CONFIDENCE   Vulture minimum confidence. Default: 90.
  ENTROPING_QUALITY_TREND_PREVIOUS
                                  Optional previous reports/quality-trend.json
                                  to compute numeric deltas.
  ENTROPING_SCRIPT_QUALITY_BASELINE
                                  Script-quality ratchet baseline.
                                  Default: docs/meta/script-quality-ratchet-baseline.json.

Options:
  --dry-run   Show deterministic audit steps without running them.
  -h, --help  Show this help.
EOF
}

dry_run=0

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
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

coverage_fail_under="${ENTROPING_COVERAGE_FAIL_UNDER:-100}"
max_complexity_rank="${ENTROPING_MAX_COMPLEXITY_RANK:-D}"
min_mi_rank="${ENTROPING_MIN_MI_RANK:-C}"
vulture_confidence="${ENTROPING_VULTURE_CONFIDENCE:-90}"
script_quality_baseline="${ENTROPING_SCRIPT_QUALITY_BASELINE:-docs/meta/script-quality-ratchet-baseline.json}"

log() {
  printf '[quality-audit] %s\n' "$*"
}

cleanup() {
  rm -f .coverage
  uv sync --dev --reinstall-package entroping >/dev/null 2>&1 || true
}

if ((dry_run)); then
  log "coverage fail-under: ${coverage_fail_under}"
  log "max complexity rank: ${max_complexity_rank}"
  log "min maintainability rank: ${min_mi_rank}"
  log "vulture confidence: ${vulture_confidence}"
  if [[ -n "${script_quality_baseline}" ]]; then
    log "script quality baseline: ${script_quality_baseline}"
  else
    log "script quality baseline: not configured"
  fi
  log "Would write test taxonomy report"
  log "Would run long-file hotspot report"
  log "Would run coverage gate with pytest-cov"
  log "Would run script quality coverage and typing visibility report"
  log "Would run Radon complexity gate"
  log "Would run Vulture dead-code discovery"
  log "Would write quality trend summary"
  log "Would run bounded performance smoke"
  exit 0
fi

cd "$repo_root"
mkdir -p reports
trap cleanup EXIT
export PYTHONPATH="${repo_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

log "Syncing dev environment"
uv sync --dev --reinstall-package entroping

log "Writing test taxonomy report"
uv run python scripts/test_taxonomy.py --output reports/test-taxonomy.json --strict

log "Running long-file hotspot report"
uv run python scripts/quality_hotspot_report.py --output reports/long-file-hotspots.json

log "Running coverage gate with pytest-cov"
uv run pytest \
  --cov=entroping \
  --cov-report=term-missing \
  --cov-report=json:reports/coverage.json \
  --cov-fail-under="${coverage_fail_under}"

log "Running script quality report"
script_quality_args=(
  --repo-root "${repo_root}"
)
if [[ -n "${script_quality_baseline}" ]]; then
  script_quality_args+=(--baseline "${script_quality_baseline}")
fi
uv run python scripts/script_quality_report.py "${script_quality_args[@]}"

log "Running Radon complexity audit"
uv run radon cc src tests -s -a --json > reports/radon-cc.json

uv run python - "${max_complexity_rank}" reports/radon-cc.json <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

rank_order = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
max_rank = sys.argv[1].strip().upper()
path = Path(sys.argv[2])
if max_rank not in rank_order:
    raise SystemExit(f"Invalid ENTROPING_MAX_COMPLEXITY_RANK: {max_rank}")

data = json.loads(path.read_text(encoding="utf-8"))
violations: list[str] = []
worst_rank = "A"
block_count = 0
for file_path, entries in data.items():
    for entry in entries:
        block_count += 1
        rank = str(entry.get("rank", "")).upper()
        if rank and rank_order.get(rank, 0) > rank_order[worst_rank]:
            worst_rank = rank
        if rank and rank_order.get(rank, 0) > rank_order[max_rank]:
            name = entry.get("name", "<unknown>")
            line = entry.get("lineno", "?")
            complexity = entry.get("complexity", "?")
            violations.append(f"{file_path}:{line} {name} rank {rank} ({complexity})")

if violations:
    print("Radon complexity threshold failed:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    raise SystemExit(1)

print(
    f"Radon complexity check passed: {block_count} blocks, "
    f"worst rank {worst_rank}, threshold {max_rank}."
)
PY

log "Running Radon maintainability audit"
uv run radon mi src -s --json > reports/radon-mi.json

uv run python - "${min_mi_rank}" reports/radon-mi.json <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

rank_order = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
min_rank = sys.argv[1].strip().upper()
path = Path(sys.argv[2])
if min_rank not in rank_order:
    raise SystemExit(f"Invalid ENTROPING_MIN_MI_RANK: {min_rank}")

data = json.loads(path.read_text(encoding="utf-8"))
violations: list[str] = []
worst_rank = "A"
file_count = 0
for file_path, entry in data.items():
    candidates = []
    if isinstance(entry, dict):
        candidates = [entry]
    elif isinstance(entry, list):
        candidates = [candidate for candidate in entry if isinstance(candidate, dict)]
    if candidates:
        file_count += 1
    for candidate in candidates:
        rank = str(candidate.get("rank", "")).upper()
        mi = candidate.get("mi", candidate.get("maintainability_index", "?"))
        if rank and rank_order.get(rank, 0) > rank_order[worst_rank]:
            worst_rank = rank
        if rank and rank_order.get(rank, 0) > rank_order[min_rank]:
            violations.append(f"{file_path} rank {rank} ({mi})")

if violations:
    print("Radon maintainability threshold failed:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    raise SystemExit(1)

print(
    f"Radon maintainability check passed: {file_count} files, "
    f"worst rank {worst_rank}, threshold {min_rank}."
)
PY

log "Running Vulture dead-code discovery"
set +e
vulture_output="$(uv run vulture src tests --min-confidence "${vulture_confidence}" 2>&1)"
vulture_status=$?
set -e
printf '%s\n' "$vulture_output" > reports/vulture.txt
if [[ -n "$vulture_output" ]]; then
  printf '%s\n' "$vulture_output"
fi

log "Writing quality trend summary"
quality_trend_args=(
  --taxonomy reports/test-taxonomy.json
  --coverage reports/coverage.json
  --radon-cc reports/radon-cc.json
  --radon-mi reports/radon-mi.json
  --vulture reports/vulture.txt
  --output reports/quality-trend.json
  --coverage-fail-under "${coverage_fail_under}"
  --max-complexity-rank "${max_complexity_rank}"
  --min-mi-rank "${min_mi_rank}"
  --vulture-confidence "${vulture_confidence}"
)
if [[ -n "${ENTROPING_QUALITY_TREND_PREVIOUS:-}" ]]; then
  quality_trend_args+=(--previous "${ENTROPING_QUALITY_TREND_PREVIOUS}")
fi
uv run python scripts/quality_trend_summary.py "${quality_trend_args[@]}"
if ((vulture_status != 0)); then
  exit "$vulture_status"
fi

log "Running bounded performance smoke"
uv run python scripts/performance_smoke.py --output reports/performance-smoke.json

log "Quality audit finished."
