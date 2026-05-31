#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "README.md"
  "LICENSE"
  "CONTRIBUTING.md"
  "SECURITY.md"
  "CODE_OF_CONDUCT.md"
  ".github/pull_request_template.md"
  ".github/ISSUE_TEMPLATE/bug_report.yml"
  ".github/ISSUE_TEMPLATE/feature_slice.yml"
  ".github/ISSUE_TEMPLATE/regression_report.yml"
  ".github/workflows/ci.yml"
  ".github/workflows/scorecard.yml"
)

missing=0
for required_file in "${required_files[@]}"; do
  if [[ -s "$required_file" ]]; then
    printf 'ok: %s\n' "$required_file"
  else
    printf 'missing: %s\n' "$required_file" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  printf 'Community profile incomplete.\n' >&2
  exit 1
fi

printf 'Community profile OK.\n'
printf 'OpenSSF Scorecard workflow: .github/workflows/scorecard.yml\n'
