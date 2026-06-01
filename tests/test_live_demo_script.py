"""Regression tests for the live checkout demo smoke script."""

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_SHELL_PATH = os.pathsep.join(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_live_demo_fake_hurl(path: Path) -> None:
    _write_executable(
        path,
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
    )


def test_demo_script_delegates_to_live_demo_smoke_and_keeps_reports(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_live_demo_fake_hurl(fake_bin / "hurl")

    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_ARTIFACT_DIR"] = str(artifact_dir)
    env["ENTROPING_DEMO_PORT"] = "18080"

    result = subprocess.run(
        ["bash", "scripts/demo.sh"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "[entroping-demo] Starting checkout demo" in result.stdout
    assert "scripts/live_demo_smoke.sh" in result.stdout
    assert str(artifact_dir) in result.stdout
    assert (artifact_dir / "run-latest.html").is_file()
    assert (artifact_dir / "run-latest.json").is_file()
    assert (artifact_dir / "junit.xml").is_file()


def test_demo_script_explains_missing_hurl_before_running_demo(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", "#!/usr/bin/env bash\nexit 0\n")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{SYSTEM_SHELL_PATH}"

    result = subprocess.run(
        ["/bin/bash", "scripts/demo.sh"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "Hurl is required" in result.stderr
    assert "https://hurl.dev/docs/installation.html" in result.stderr


def test_live_demo_smoke_script_explains_missing_hurl_install_options(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uv", "#!/usr/bin/env bash\nexit 0\n")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{SYSTEM_SHELL_PATH}"

    result = subprocess.run(
        ["/bin/bash", "scripts/live_demo_smoke.sh"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "Hurl is required" in result.stderr
    assert "brew install hurl" in result.stderr
    assert "scripts/demo.sh" in result.stderr


def test_live_demo_smoke_documents_readiness_probe_boundary() -> None:
    source = (REPO_ROOT / "scripts" / "live_demo_smoke.sh").read_text(encoding="utf-8")

    assert "readiness probe" in source
    assert "API assertions still run through Entroping and Hurl" in source


def test_live_demo_smoke_script_uses_hurl_and_copies_artifacts(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_live_demo_fake_hurl(fake_bin / "hurl")

    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_ARTIFACT_DIR"] = str(artifact_dir)
    env["ENTROPING_DEMO_PORT"] = "18080"

    result = subprocess.run(
        ["bash", "scripts/live_demo_smoke.sh"],
        cwd=REPO_ROOT,
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
    _write_executable(fake_bin / "hurl", "#!/usr/bin/env bash\nexit 0\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_WORKDIR"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/live_demo_smoke.sh"],
        cwd=REPO_ROOT,
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
    _write_executable(fake_bin / "hurl", "#!/usr/bin/env bash\nexit 0\n")

    workdir = tmp_path / "demo"
    workdir.mkdir()
    sentinel = workdir / "keep.txt"
    sentinel.write_text("do not delete\n", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_LIVE_DEMO_WORKDIR"] = str(workdir)

    result = subprocess.run(
        ["bash", "scripts/live_demo_smoke.sh"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert "Refusing to reuse non-empty live demo workdir" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "do not delete\n"
