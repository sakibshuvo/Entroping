#!/usr/bin/env bash
set -euo pipefail

script_dir="${BASH_SOURCE[0]%/*}"
repo_root="$(cd "$script_dir/.." && pwd)"

printf '[entroping-aha-failure] Running deterministic missing-header failure proof.\n'
printf '[entroping-aha-failure] expected output: entroping run blocks on request_id_header.\n'

"$repo_root/scripts/ai_regression_demo.sh"
