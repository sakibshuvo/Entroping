#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

show_help() {
  cat <<'EOF'
Usage: scripts/package_check.sh [OPTIONS]

Builds local package artifacts and verifies release-critical metadata.

The check removes dist/, runs uv build, then inspects the wheel and sdist for
expected project metadata, including License-Expression and license files.

Options:
  --dry-run   Show deterministic package verification steps without running them.
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

log() {
  printf '[package-check] %s\n' "$*"
}

if ((dry_run)); then
  log "Would remove dist/"
  log "Would run: uv build"
  log "Would verify wheel metadata and sdist contents"
  exit 0
fi

cd "$repo_root"

log "Removing dist/"
rm -rf dist

log "Running: uv build"
uv build

uv run python - <<'PY'
from __future__ import annotations

import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

repo_root = Path.cwd()
dist_dir = repo_root / "dist"

pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
project = pyproject["project"]
name = project["name"]
version = project["version"]

expected_wheel = dist_dir / f"{name}-{version}-py3-none-any.whl"
expected_sdist = dist_dir / f"{name}-{version}.tar.gz"


def fail(message: str) -> None:
    raise SystemExit(f"Package artifact check failed: {message}")


if not expected_wheel.is_file():
    fail(f"missing expected wheel {expected_wheel.relative_to(repo_root)}")
if not expected_sdist.is_file():
    fail(f"missing expected sdist {expected_sdist.relative_to(repo_root)}")

wheel_files = sorted(dist_dir.glob(f"{name}-*.whl"))
sdist_files = sorted(dist_dir.glob(f"{name}-*.tar.gz"))
if wheel_files != [expected_wheel]:
    found = ", ".join(path.name for path in wheel_files) or "none"
    fail(f"expected exactly one wheel, found {found}")
if sdist_files != [expected_sdist]:
    found = ", ".join(path.name for path in sdist_files) or "none"
    fail(f"expected exactly one sdist, found {found}")

with zipfile.ZipFile(expected_wheel) as wheel:
    names = wheel.namelist()
    metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        fail("wheel must contain exactly one METADATA file")
    metadata = Parser().parsestr(wheel.read(metadata_paths[0]).decode("utf-8"))

    expected_license_path = f"{name}-{version}.dist-info/licenses/LICENSE"
    if expected_license_path not in names:
        fail(f"wheel is missing {expected_license_path}")

metadata_name = metadata.get("Name")
metadata_version = metadata.get("Version")
license_expression = metadata.get("License-Expression")
license_files = metadata.get_all("License-File", [])
classifiers = metadata.get_all("Classifier", [])

if metadata_name != name:
    fail(f"Name metadata mismatch: expected {name}, found {metadata_name}")
if metadata_version != version:
    fail(f"Version metadata mismatch: expected {version}, found {metadata_version}")
if license_expression != "Apache-2.0":
    fail(f"License-Expression mismatch: found {license_expression}")
if "LICENSE" not in license_files:
    fail("License-File metadata must include LICENSE")
if "Development Status :: 3 - Alpha" not in classifiers:
    fail("alpha development-status classifier is missing")
if any(classifier == "Development Status :: 5 - Production/Stable" for classifier in classifiers):
    fail("production/stable classifier is not allowed for the alpha package")
if any(classifier.startswith("License ::") for classifier in classifiers):
    fail("legacy license classifiers should not be used with SPDX license metadata")

with tarfile.open(expected_sdist, "r:gz") as sdist:
    names = set(sdist.getnames())
    root = f"{name}-{version}"
    for required in ("LICENSE", "README.md", "pyproject.toml"):
        path = f"{root}/{required}"
        if path not in names:
            fail(f"sdist is missing {path}")

print("Package artifacts OK")
print(f"Wheel: {expected_wheel.relative_to(repo_root)}")
print(f"Sdist: {expected_sdist.relative_to(repo_root)}")
print("License-Expression: Apache-2.0")
PY
