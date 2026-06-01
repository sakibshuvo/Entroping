#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
demo_port="${ENTROPING_AI_REGRESSION_PORT:-18180}"
artifact_dir="${ENTROPING_AI_REGRESSION_ARTIFACT_DIR:-}"
workdir="$(mktemp -d)"
server_pid=""

export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$workdir"
}
trap cleanup EXIT

if ! command -v hurl >/dev/null 2>&1; then
  echo "Hurl is required for the AI-regression proof demo." >&2
  echo "Install Hurl directly, for example: brew install hurl" >&2
  exit 1
fi

cp -R "$repo_root/examples/ai-regression-demo/." "$workdir/"
printf "base_url=http://127.0.0.1:%s\n" "$demo_port" > "$workdir/envs/local.env"

python "$workdir/demo_server.py" --port "$demo_port" &
server_pid="$!"

# This is only a local readiness probe for the intentionally broken fixture.
# API assertions still run through Entroping and Hurl below.
python - "$demo_port" <<'PY'
import sys
import time
from urllib.request import urlopen

port = sys.argv[1]
url = f"http://127.0.0.1:{port}/health"
deadline = time.monotonic() + 10
while time.monotonic() < deadline:
    try:
        with urlopen(url, timeout=0.5) as response:
            if response.status == 200:
                raise SystemExit(0)
    except OSError:
        time.sleep(0.2)
raise SystemExit(f"AI-regression fixture did not become ready at {url}")
PY

cd "$workdir"
set +e
uv run --project "$repo_root" entroping run \
  --env local \
  --tag ai-regression \
  --ci \
  --report json > entroping.stdout 2> entroping.stderr
status="$?"
set -e

if [[ "$status" -eq 0 ]]; then
  echo "Expected Entroping to fail because the fixture omits X-Request-Id." >&2
  cat entroping.stdout >&2
  cat entroping.stderr >&2
  exit 1
fi

if ! grep -q "request_id_header" reports/run-latest.json; then
  echo "Expected reports/run-latest.json to contain the request_id_header gate." >&2
  cat reports/run-latest.json >&2
  exit 1
fi

if ! grep -q "X-Request-Id" reports/run-latest.json; then
  echo "Expected reports/run-latest.json to contain the missing X-Request-Id assertion." >&2
  cat reports/run-latest.json >&2
  exit 1
fi

if [[ -n "$artifact_dir" ]]; then
  mkdir -p "$artifact_dir"
  cp reports/run-latest.json entroping.stdout entroping.stderr "$artifact_dir"/
fi

echo "Entroping blocked the missing X-Request-Id regression."
