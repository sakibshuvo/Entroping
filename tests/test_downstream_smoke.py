"""Stable-core downstream smoke evidence harness."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "downstream_smoke.py"
SYSTEM_SHELL_PATH = os.pathsep.join(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_hurl(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env bash
set -euo pipefail

for arg in "$@"; do
  case "$arg" in
    *Entroping-issue-*|*projects/Entroping*)
      echo "repo path leaked into hurl argv: $arg" >&2
      exit 42
      ;;
  esac
done

printf 'fake downstream hurl ok\\n'
""",
    )


def _write_failing_hurl(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--version" ]]; then
  printf 'hurl fake-failing\\n'
  exit 0
fi

printf 'fake downstream hurl failure\\n' >&2
exit 42
""",
    )


def run_downstream_smoke(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_downstream_smoke_json_dry_run_describes_external_project() -> None:
    result = run_downstream_smoke("--dry-run", "--format", "json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.downstream-smoke.v1"
    assert payload["status"] == "planned"
    assert payload["stable_core_ready"] is False
    assert payload["uses_public_cli"] is True
    assert payload["requires_hurl"] is True
    assert "uv run --project" in payload["command"]
    assert "entroping run --ci" in payload["command"]


def test_downstream_smoke_runs_from_outside_repo_with_fake_hurl(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_hurl(fake_bin / "hurl")
    artifact_dir = tmp_path / "artifacts"
    workdir = tmp_path / "downstream-project"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = run_downstream_smoke(
        "--format",
        "json",
        "--workdir",
        str(workdir),
        "--artifact-dir",
        str(artifact_dir),
        env=env,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["stable_core_ready"] is False
    assert payload["uses_public_cli"] is True
    assert payload["downstream_project_path"] == str(workdir)
    assert REPO_ROOT not in Path(payload["downstream_project_path"]).parents
    assert payload["artifacts"] == [
        "downstream-smoke-evidence.json",
        "junit.xml",
        "run-latest.html",
        "run-latest.json",
    ]
    assert (artifact_dir / "downstream-smoke-evidence.json").is_file()
    assert (artifact_dir / "run-latest.json").is_file()
    assert (artifact_dir / "run-latest.html").is_file()
    assert (artifact_dir / "junit.xml").is_file()


def test_downstream_smoke_rejects_repo_workdir(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_hurl(fake_bin / "hurl")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{SYSTEM_SHELL_PATH}"

    result = run_downstream_smoke("--workdir", str(REPO_ROOT), env=env)

    assert result.returncode == 1
    assert "Refusing unsafe downstream workdir" in result.stderr


def test_downstream_smoke_reports_missing_hurl_before_entroping_run(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PATH"] = SYSTEM_SHELL_PATH

    result = run_downstream_smoke(
        "--format",
        "json",
        "--workdir",
        str(tmp_path / "missing-hurl-project"),
        env=env,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert "Hurl is required for downstream smoke evidence" in payload["failure"]
    assert "downstream smoke failed" in result.stderr


def test_downstream_smoke_reports_entroping_run_failure(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_failing_hurl(fake_bin / "hurl")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = run_downstream_smoke(
        "--format",
        "json",
        "--workdir",
        str(tmp_path / "run-failure-project"),
        env=env,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert "fake downstream hurl failure" in payload["failure"]
    assert "Entroping run failed with exit code" in result.stderr


def test_stable_core_readiness_knows_downstream_smoke_harness_exists() -> None:
    source = (REPO_ROOT / "scripts" / "stable_core_readiness.py").read_text(
        encoding="utf-8"
    )

    assert "downstream_smoke_evidence" in source
    assert "scripts/downstream_smoke.py" in source


def test_release_docs_link_downstream_smoke_evidence() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")
    docs = (REPO_ROOT / "docs" / "meta" / "DOWNSTREAM_SMOKE_EVIDENCE.md").read_text(
        encoding="utf-8"
    )

    assert "[[docs/meta/DOWNSTREAM_SMOKE_EVIDENCE|DOWNSTREAM_SMOKE_EVIDENCE]]" in index
    assert "scripts/downstream_smoke.py" in docs
    assert "scripts/release_check.sh --require-live-demo" in docs
    assert "--skip-downstream-smoke" in docs
    assert "does not satisfy real downstream user feedback" in docs
