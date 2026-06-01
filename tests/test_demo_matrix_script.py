"""Contract tests for the launch demo proof matrix."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "demo_matrix.sh"


def run_demo_matrix(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_demo_matrix_help_documents_launch_proofs() -> None:
    result = run_demo_matrix("--help")

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--skip-live-demos" in result.stdout
    assert "scripts/demo.sh" in result.stdout
    assert "scripts/ai_regression_demo.sh" in result.stdout
    assert "scripts/policy_pack_smoke.py --strict" in result.stdout


def test_demo_matrix_dry_run_lists_full_launch_rehearsal() -> None:
    result = run_demo_matrix("--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would run: scripts/demo.sh" in result.stdout
    assert "Would run: scripts/ai_regression_demo.sh" in result.stdout
    assert "Would run: uv run python scripts/policy_pack_smoke.py --strict" in result.stdout
    assert "Would run: uv run python scripts/launch_readiness.py --strict" in result.stdout
    assert "Would run: uv run python scripts/backlog_health.py" in result.stdout


def test_demo_matrix_dry_run_can_skip_live_hurl_demos() -> None:
    result = run_demo_matrix("--dry-run", "--skip-live-demos")

    assert result.returncode == 0, result.stderr
    assert "skip live demos: yes" in result.stdout
    assert "scripts/demo.sh" not in result.stdout
    assert "scripts/ai_regression_demo.sh" not in result.stdout
    assert "scripts/policy_pack_smoke.py --strict" in result.stdout


def test_demo_matrix_rejects_unknown_options() -> None:
    result = run_demo_matrix("--bogus")

    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr
