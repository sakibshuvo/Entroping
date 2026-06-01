#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
demo_port="${ENTROPING_DEMO_PORT:-18080}"
artifact_dir="${ENTROPING_LIVE_DEMO_ARTIFACT_DIR:-}"
workdir="${ENTROPING_LIVE_DEMO_WORKDIR:-}"
own_workdir=0
server_pid=""

export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ -z "$workdir" ]]; then
  workdir="$(mktemp -d)"
  own_workdir=1
else
  workdir="$(
    python - "$repo_root" "$workdir" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1]).resolve()
candidate = Path(sys.argv[2]).expanduser()
if not candidate.is_absolute():
    candidate = (Path.cwd() / candidate)

current = Path(candidate.anchor or "/")
for part in candidate.parts[1:]:
    current = current / part
    if current.exists() or current.is_symlink():
        if current.is_symlink():
            raise SystemExit(f"Refusing to use symlinked live demo workdir component: {current}")

candidate.mkdir(parents=True, exist_ok=True)
resolved = candidate.resolve(strict=True)
if resolved == Path("/") or resolved == repo_root or repo_root in resolved.parents:
    raise SystemExit(f"Refusing to use unsafe live demo workdir: {resolved}")
if any(resolved.iterdir()):
    raise SystemExit(f"Refusing to reuse non-empty live demo workdir: {resolved}")
print(resolved)
PY
  )" || {
    echo "$workdir" >&2
    exit 1
  }
fi
workdir="$(cd "$workdir" && pwd)"

case "$workdir" in
  /|"$repo_root"|"$repo_root"/*)
    echo "Refusing to use unsafe live demo workdir: $workdir" >&2
    exit 1
    ;;
esac

cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ "$own_workdir" == "1" ]]; then
    rm -rf "$workdir"
  fi
}
trap cleanup EXIT

if ! command -v hurl >/dev/null 2>&1; then
  echo "Hurl is required for the live demo smoke." >&2
  echo "Install Hurl directly, for example: brew install hurl" >&2
  echo "For the guided demo entry point, run: scripts/demo.sh" >&2
  exit 1
fi

cp -R "$repo_root/examples/checkout-api/." "$workdir/"

python "$repo_root/examples/checkout-api/demo_server.py" --port "$demo_port" &
server_pid="$!"

# This urlopen call is only a local readiness probe for the fixture server.
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
raise SystemExit(f"Demo server did not become ready at {url}")
PY

cd "$workdir"

uv run --project "$repo_root" entroping architect build --new --tag smoke
printf "base_url=http://127.0.0.1:%s\ncart_id=demo-cart-001\n" "$demo_port" > envs/local.env
uv run --project "$repo_root" entroping run \
  --env local \
  --tag smoke \
  --report html \
  --report json \
  --report junit

if [[ -n "$artifact_dir" ]]; then
  mkdir -p "$artifact_dir"
  cp reports/run-latest.html reports/run-latest.json reports/junit.xml "$artifact_dir"/
fi
