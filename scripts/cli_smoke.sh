#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workdir="$(mktemp -d)"

cleanup() {
  rm -rf "$workdir"
}
trap cleanup EXIT

entroping_cli=(uv run --project "$repo_root" entroping)

echo "[entroping-cli-smoke] entroping --help"
"${entroping_cli[@]}" --help >/dev/null

echo "[entroping-cli-smoke] entroping --version"
"${entroping_cli[@]}" --version >/dev/null

cd "$workdir"

echo "[entroping-cli-smoke] entroping init --minimal"
"${entroping_cli[@]}" init --minimal >/dev/null

echo "[entroping-cli-smoke] entroping doctor"
doctor_output="$("${entroping_cli[@]}" doctor 2>&1)"
printf '%s\n' "$doctor_output"

qanstitution_line=""
hurl_line=""
while IFS= read -r line; do
  case "$line" in
    QAnstitution:\ *)
      qanstitution_line="$line"
      ;;
    Hurl:\ *)
      hurl_line="$line"
      ;;
  esac
done <<<"$doctor_output"

case "$qanstitution_line" in
  *"valid"*)
    ;;
  *)
    echo "Expected entroping doctor to report a valid QAnstitution." >&2
    exit 1
    ;;
esac

case "$hurl_line" in
  *"not found"*)
    echo "[entroping-cli-smoke] Missing Hurl is acceptable for this no-Hurl smoke."
    ;;
  *"found"*)
    echo "[entroping-cli-smoke] Hurl is installed; smoke still avoided runtime execution."
    ;;
  *"version unparsable"*)
    echo "[entroping-cli-smoke] Hurl is installed but version output was not parseable; smoke still avoided runtime execution."
    ;;
  *)
    echo "Expected entroping doctor to report Hurl availability." >&2
    exit 1
    ;;
esac
