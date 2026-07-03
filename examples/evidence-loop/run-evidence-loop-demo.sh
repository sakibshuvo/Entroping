#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEMO_BASE="${ENTROPING_DEMO_TMP_BASE:-$HOME/.cache/entroping-demo}"
KEEP_ARTIFACTS="${ENTROPING_DEMO_KEEP_ARTIFACTS:-0}"
SERVER_PORT="${ENTROPING_EVIDENCE_LOOP_PORT:-18080}"
BASE_URL="http://127.0.0.1:${SERVER_PORT}"
SERVER_PID=""

mkdir -p "$DEMO_BASE"
WORK_DIR="$(mktemp -d "$DEMO_BASE/work.XXXXXX")"
ARTIFACT_DIR="$(mktemp -d "$DEMO_BASE/artifacts.XXXXXX")"
SERVER_LOG="$WORK_DIR/server.log"

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi

  if [ "${KEEP_ARTIFACTS}" != "1" ]; then
    rm -rf "$WORK_DIR"
    rm -rf "$ARTIFACT_DIR"
  else
    echo "Keeping artifacts for inspection at $ARTIFACT_DIR"
    echo "Working copy retained at $WORK_DIR"
  fi
}

trap cleanup EXIT

cp -R "$REPO_ROOT/examples/checkout-api" "$WORK_DIR/"
cp "$WORK_DIR/checkout-api/envs/local.env.example" "$WORK_DIR/checkout-api/envs/local.env"
python - <<PY
from pathlib import Path
path = Path("$WORK_DIR/checkout-api/envs/local.env")
content = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("base_url=")]
content.append(f"base_url={BASE_URL}")
path.write_text("\n".join(content) + "\n", encoding="utf-8")
PY
cd "$WORK_DIR/checkout-api"

echo "Using demo root: $WORK_DIR/checkout-api"
echo "Writing packet artifacts to: $ARTIFACT_DIR"

python demo_server.py --port "$SERVER_PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

# Allow the server to start.
sleep 1

uv run --project "$REPO_ROOT" entroping doctor
uv run --project "$REPO_ROOT" entroping run --env local --tag smoke --report json --report junit

# Stable launch packets.
uv run --project "$REPO_ROOT" entroping report runtime-card --output "$ARTIFACT_DIR/runtime-card.md"
uv run --project "$REPO_ROOT" entroping report handoff --output "$ARTIFACT_DIR/handoff.md"

# Design-partner packet surfaces.
uv run --project "$REPO_ROOT" entroping report design-partner-feedback --output "$ARTIFACT_DIR/design-partner-feedback.json"
uv run --project "$REPO_ROOT" entroping report evidence-links --output "$ARTIFACT_DIR/evidence-links.md"
uv run --project "$REPO_ROOT" entroping report notification-packet --output "$ARTIFACT_DIR/notification-packet.md"
uv run --project "$REPO_ROOT" entroping report evidence-portal --output "$ARTIFACT_DIR/evidence-portal.html"

printf '\nEvidence loop artifacts:\n'
ls -1 "$ARTIFACT_DIR"

printf '\nView logs (trimmed):\n'
tail -n 20 "$SERVER_LOG"
