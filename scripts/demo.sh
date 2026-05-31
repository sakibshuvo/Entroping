#!/usr/bin/env bash
set -euo pipefail

script_dir="${BASH_SOURCE[0]%/*}"
repo_root="$(cd "$script_dir/.." && pwd)"

fail() {
  printf 'demo: %s\n' "$*" >&2
  exit 1
}

if ! command -v uv >/dev/null 2>&1; then
  fail "uv is required. Install uv: https://docs.astral.sh/uv/"
fi

if ! command -v hurl >/dev/null 2>&1; then
  fail "Hurl is required for the deterministic checkout demo. Install hurl: https://hurl.dev/docs/installation.html"
fi

printf '[entroping-demo] Starting checkout demo through scripts/live_demo_smoke.sh\n'
printf '[entroping-demo] This starts a local fixture, generates Hurl tests, runs QAnstitution gates, and emits reports.\n'

"$repo_root/scripts/live_demo_smoke.sh"

if [[ -n "${ENTROPING_LIVE_DEMO_ARTIFACT_DIR:-}" ]]; then
  printf '[entroping-demo] Copied demo reports to %s\n' "$ENTROPING_LIVE_DEMO_ARTIFACT_DIR"
else
  printf '[entroping-demo] Demo passed. Set ENTROPING_LIVE_DEMO_ARTIFACT_DIR=<dir> to keep copied reports.\n'
fi
