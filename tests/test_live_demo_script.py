"""Regression tests for the live checkout demo smoke script."""

import os
import stat
import subprocess
from pathlib import Path


def test_live_demo_smoke_script_uses_hurl_and_copies_artifacts(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_hurl = fake_bin / "hurl"
    fake_hurl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

for arg in "$@"; do
  case "$arg" in
    *demo-cart-001*|*localhost:18080*|*127.0.0.1:18080*)
      echo "secret-bearing value leaked into argv: $arg" >&2
      exit 42
      ;;
  esac
done

vars_file=""
while (($#)); do
  case "$1" in
    --variables-file)
      shift
      vars_file="$1"
      ;;
  esac
  shift || true
done

test -n "$vars_file"
grep -q "base_url=http://127.0.0.1:18080" "$vars_file"
grep -q "cart_id=demo-cart-001" "$vars_file"
echo "fake hurl ok"
""",
        encoding="utf-8",
    )
    fake_hurl.chmod(fake_hurl.stat().st_mode | stat.S_IXUSR)

    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_ARTIFACT_DIR"] = str(artifact_dir)
    env["ENTROPING_DEMO_PORT"] = "18080"

    result = subprocess.run(
        ["bash", "scripts/live_demo_smoke.sh"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (artifact_dir / "run-latest.html").is_file()
    assert (artifact_dir / "run-latest.json").is_file()
    assert (artifact_dir / "junit.xml").is_file()


def test_live_demo_smoke_script_rejects_repo_workdir(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_hurl = fake_bin / "hurl"
    fake_hurl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_hurl.chmod(fake_hurl.stat().st_mode | stat.S_IXUSR)

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_WORKDIR"] = str(repo_root)

    result = subprocess.run(
        ["bash", "scripts/live_demo_smoke.sh"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "Refusing to use unsafe live demo workdir" in result.stderr


def test_live_demo_smoke_script_rejects_non_empty_custom_workdir(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_hurl = fake_bin / "hurl"
    fake_hurl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_hurl.chmod(fake_hurl.stat().st_mode | stat.S_IXUSR)

    workdir = tmp_path / "demo"
    workdir.mkdir()
    sentinel = workdir / "keep.txt"
    sentinel.write_text("do not delete\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_WORKDIR"] = str(workdir)

    result = subprocess.run(
        ["bash", "scripts/live_demo_smoke.sh"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "Refusing to reuse non-empty live demo workdir" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "do not delete\n"
