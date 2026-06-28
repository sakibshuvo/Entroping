"""Smoke tests for the alpha release-readiness script."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "release_check.sh"


def run_release_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_release_check_help_documents_release_options() -> None:
    result = run_release_check("--help")

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--skip-security" in result.stdout
    assert "--skip-performance" in result.stdout
    assert "--skip-downstream-smoke" in result.stdout
    assert "--require-live-demo" in result.stdout
    assert "--allow-dirty" in result.stdout


def test_release_check_dry_run_shows_full_alpha_gate() -> None:
    result = run_release_check("--dry-run", "--require-live-demo")

    assert result.returncode == 0, result.stderr
    assert "scripts/repo_hygiene.sh" in result.stdout
    assert "scripts/regression.sh --security" in result.stdout
    assert "scripts/package_check.sh" in result.stdout
    assert "scripts/package_index_readiness.py --strict" in result.stdout
    assert "scripts/install_reference_sync.py --check" in result.stdout
    assert "scripts/local_wheel_install_smoke.py --skip-build" in result.stdout
    assert "scripts/downstream_smoke.py" in result.stdout
    assert "scripts/policy_pack_smoke.py --strict" in result.stdout
    assert "scripts/launch_readiness.py --strict" in result.stdout
    assert "scripts/performance_smoke.py" in result.stdout
    assert "scripts/live_demo_smoke.sh" in result.stdout
    assert "require live demo: yes" in result.stdout


def test_release_check_dry_run_can_skip_security_performance_and_live_demo() -> None:
    result = run_release_check(
        "--dry-run",
        "--skip-security",
        "--skip-performance",
        "--skip-live-demo",
    )

    assert result.returncode == 0, result.stderr
    assert "scripts/regression.sh" in result.stdout
    assert "scripts/regression.sh --security" not in result.stdout
    assert "scripts/performance_smoke.py" not in result.stdout
    assert "skip performance: yes" in result.stdout
    assert "scripts/downstream_smoke.py" in result.stdout
    assert "scripts/live_demo_smoke.sh" not in result.stdout
    assert "skip live demo: yes" in result.stdout


def test_release_check_dry_run_can_skip_downstream_smoke() -> None:
    result = run_release_check("--dry-run", "--skip-downstream-smoke")

    assert result.returncode == 0, result.stderr
    assert "skip downstream smoke: yes" in result.stdout
    assert "Skipping downstream smoke by request." in result.stdout
    assert "scripts/downstream_smoke.py" not in result.stdout


def test_release_check_rejects_unknown_options() -> None:
    result = run_release_check("--bogus")

    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr


def test_release_check_rejects_conflicting_live_demo_options() -> None:
    result = run_release_check("--skip-live-demo", "--require-live-demo")

    assert result.returncode == 2
    assert "--skip-live-demo and --require-live-demo cannot be used together" in result.stderr
