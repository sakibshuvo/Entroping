"""Proof fixture for a realistic AI-introduced runtime regression."""

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ai_regression_demo.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_ai_regression_demo_succeeds_only_when_entroping_blocks_regression(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "hurl",
        """#!/usr/bin/env bash
echo 'Assert failure: header "X-Request-Id" exists' >&2
exit 1
""",
    )
    artifact_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_AI_REGRESSION_ARTIFACT_DIR"] = str(artifact_dir)
    env["ENTROPING_AI_REGRESSION_PORT"] = "18181"

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Entroping blocked the missing X-Request-Id regression" in result.stdout
    assert (artifact_dir / "run-latest.json").is_file()


def test_ai_regression_demo_fixture_documents_the_failure_mode() -> None:
    readme = (REPO_ROOT / "examples" / "ai-regression-demo" / "README.md").read_text(
        encoding="utf-8"
    )
    policy = (REPO_ROOT / "examples" / "ai-regression-demo" / "qanstitution.yaml").read_text(
        encoding="utf-8"
    )

    assert "AI-regression proof" in readme
    assert "X-Request-Id" in readme
    assert "request_id_header" in policy
    assert "enforcement: \"block\"" in policy
