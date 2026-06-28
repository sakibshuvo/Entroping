"""Smoke tests for the alpha release-readiness script."""

import shutil
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


def test_package_index_readiness_invoked_in_script_source() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "scripts/package_index_readiness.py --strict" in source, (
        "release_check.sh must invoke package_index_readiness.py --strict; "
        "removing it would silently drop the package-index gate"
    )


def test_package_index_readiness_not_skippable() -> None:
    """No --skip flag exists that would bypass package_index_readiness."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "skip-package-index" not in source
    assert "skip_package_index" not in source
    assert "skip package index" not in source.lower()
    assert "skip-pypi" not in source.lower()


def test_package_index_readiness_appears_in_all_dry_run_modes() -> None:
    """Package-index check is always present, even with all skips enabled."""
    max_skip = run_release_check(
        "--dry-run",
        "--skip-security",
        "--skip-performance",
        "--skip-downstream-smoke",
        "--skip-live-demo",
    )
    assert max_skip.returncode == 0, max_skip.stderr
    assert "scripts/package_index_readiness.py --strict" in max_skip.stdout, (
        "package_index_readiness must not be skippable"
    )

    minimal = run_release_check("--dry-run")
    assert minimal.returncode == 0, minimal.stderr
    assert "scripts/package_index_readiness.py --strict" in minimal.stdout


def test_package_index_failure_blocks_release_check(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for relative in (
        ".github/workflows/publish-python-package.yml",
        "docs/meta/PYPI_RELEASE_RUNBOOK.md",
        "docs/meta/release-evidence.json",
        "pyproject.toml",
    ):
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    result = subprocess.run(
        ["python", str(REPO_ROOT / "scripts" / "package_index_readiness.py"),
         "--root", str(root), "--strict"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"baseline must pass: {result.stderr}"

    (root / "docs" / "meta" / "release-evidence.json").unlink()
    broken = subprocess.run(
        ["python", str(REPO_ROOT / "scripts" / "package_index_readiness.py"),
         "--root", str(root), "--strict"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert broken.returncode == 1, (
        "package_index_readiness must exit 1 when evidence is missing; "
        "otherwise the release-check gate is meaningless"
    )
