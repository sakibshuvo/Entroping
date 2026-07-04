"""Smoke tests for the alpha release-readiness script."""

import os
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


def write_fake_script(path: Path, status: int, log_path: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "{path.name} invoked" >> "{log_path}"
exit {status}
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_fake_uv(path: Path, statuses: dict[str, int], log_path: Path) -> None:
    case_lines = "\n".join(
        f'  "{script}") exit_code="{exit_code}" ;;'
        for script, exit_code in sorted(statuses.items())
    )
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv invoked: $*" >> "{log_path}"
if [[ "${{1:-}}" != "run" || "${{2:-}}" != "python" ]]; then
  exit 0
fi

target="${{3:-}}"
target="${{target##*/}}"

case "$target" in
{case_lines}
  *) exit_code="0" ;;
esac

exit "$exit_code"
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def run_release_check_in_fixture(
    fixture_root: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    fixture_env = os.environ.copy()
    fixture_env["PATH"] = (
        f"{fixture_root / 'scripts'}"
        + os.pathsep
        + fixture_env["PATH"]
    )
    if env is not None:
        fixture_env.update(env)
    return subprocess.run(
        [str(fixture_root / "scripts" / "release_check.sh"), *args],
        check=False,
        cwd=fixture_root,
        env=fixture_env,
        capture_output=True,
        text=True,
    )


def build_release_check_fixture(
    tmp_path: Path,
    uv_status: dict[str, int] | None = None,
    direct_status: dict[str, int] | None = None,
) -> Path:
    uv_status = uv_status or {}
    direct_status = direct_status or {}

    fixture_root = tmp_path / "repo"
    fixture_scripts = fixture_root / "scripts"
    fixture_scripts.mkdir(parents=True, exist_ok=True)

    fixture_log = fixture_root / "commands.log"
    shutil.copy2(SCRIPT, fixture_scripts / "release_check.sh")

    default_uv_status = {
        "policy_pack_smoke.py": 0,
        "launch_readiness.py": 0,
        "release_evidence.py": 0,
        "package_index_readiness.py": 0,
        "install_reference_sync.py": 0,
        "stable_core_readiness.py": 0,
        "local_wheel_install_smoke.py": 0,
        "regression.py": 0,
        "performance_smoke.py": 0,
        "downstream_smoke.py": 0,
    }
    default_uv_status.update(uv_status)

    for script_name in (
        "repo_hygiene.sh",
        "regression.sh",
        "package_check.sh",
        "live_demo_smoke.sh",
    ):
        status = direct_status.get(script_name, 0)
        write_fake_script(fixture_scripts / script_name, status, fixture_log)

    for script_name, status in direct_status.items():
        if script_name in {
            "repo_hygiene.sh",
            "regression.sh",
            "package_check.sh",
            "live_demo_smoke.sh",
        }:
            continue
        write_fake_script(fixture_scripts / script_name, status, fixture_log)

    write_fake_uv(fixture_scripts / "uv", default_uv_status, fixture_log)
    fake_hurl = fixture_scripts / "hurl"
    fake_hurl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_hurl.chmod(0o755)

    return fixture_root


def test_release_check_help_documents_release_options() -> None:
    result = run_release_check("--help")

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--skip-security" in result.stdout
    assert "--aggregate" in result.stdout
    assert "--skip-performance" in result.stdout
    assert "--skip-downstream-smoke" in result.stdout
    assert "--require-live-demo" in result.stdout
    assert "--skip-release-evidence-freshness" in result.stdout
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
    assert "scripts/release_evidence.py --check-freshness --strict" in result.stdout
    assert "scripts/downstream_smoke.py" in result.stdout
    assert "scripts/policy_pack_smoke.py --strict" in result.stdout
    assert "scripts/launch_readiness.py --strict" in result.stdout
    assert "scripts/performance_smoke.py" in result.stdout
    assert "scripts/live_demo_smoke.sh" in result.stdout
    assert "scripts/aha_readiness.py --format json" in result.stdout
    assert "Aha demo gate: informational dry-run only" in result.stdout
    assert "release evidence freshness: yes" in result.stdout
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


def test_release_check_dry_run_can_skip_release_evidence_freshness() -> None:
    result = run_release_check("--dry-run", "--skip-release-evidence-freshness")

    assert result.returncode == 0, result.stderr
    assert "release evidence freshness: no" in result.stdout
    assert "scripts/release_evidence.py --strict" in result.stdout
    assert "scripts/release_evidence.py --check-freshness" not in result.stdout


def test_release_check_dry_run_skips_aha_gate_when_script_is_missing(
    tmp_path: Path,
) -> None:
    fixture = build_release_check_fixture(tmp_path)
    result = run_release_check_in_fixture(fixture, "--dry-run", "--allow-dirty")

    assert result.returncode == 0, result.stderr
    assert "Aha demo gate not planned because scripts/aha_readiness.py is missing." in (
        result.stdout
    )
    assert "scripts/aha_readiness.py --format json" not in result.stdout


def test_release_check_runtime_does_not_run_aha_gate_until_promoted(
    tmp_path: Path,
) -> None:
    fixture = build_release_check_fixture(tmp_path)
    (fixture / "scripts" / "aha_readiness.py").write_text(
        "#!/usr/bin/env python\n",
        encoding="utf-8",
    )

    result = run_release_check_in_fixture(
        fixture,
        "--aggregate",
        "--allow-dirty",
        "--skip-downstream-smoke",
        "--skip-live-demo",
        "--skip-performance",
    )

    assert result.returncode == 0, result.stderr
    log = (fixture / "commands.log").read_text(encoding="utf-8")
    assert "scripts/aha_readiness.py" not in log
    assert "Aha demo gate" not in result.stdout


def test_release_check_rejects_unknown_options() -> None:
    result = run_release_check("--bogus")

    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr


def test_release_check_rejects_conflicting_live_demo_options() -> None:
    result = run_release_check("--skip-live-demo", "--require-live-demo")

    assert result.returncode == 2
    assert (
        "--skip-live-demo and --require-live-demo cannot be used together"
        in result.stderr
    )


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


def test_release_check_aggregate_mode_succeeds_when_all_gates_pass(
    tmp_path: Path,
) -> None:
    fixture = build_release_check_fixture(tmp_path)
    result = run_release_check_in_fixture(
        fixture,
        "--aggregate",
        "--allow-dirty",
        "--skip-downstream-smoke",
        "--skip-live-demo",
        "--skip-performance",
    )

    assert result.returncode == 0, result.stderr
    assert "Release readiness gate finished." in result.stdout
    log = (fixture / "commands.log").read_text(encoding="utf-8")
    assert (
        "uv invoked: run python scripts/release_evidence.py --check-freshness --strict"
        in log
    )


def test_release_check_aggregate_mode_reports_single_failure(tmp_path: Path) -> None:
    fixture = build_release_check_fixture(
        tmp_path,
        uv_status={"policy_pack_smoke.py": 2},
    )

    result = run_release_check_in_fixture(
        fixture,
        "--aggregate",
        "--allow-dirty",
        "--skip-downstream-smoke",
        "--skip-live-demo",
        "--skip-performance",
    )

    assert result.returncode == 1, result.stderr
    assert "Release check failed with 1 failed gate(s)." in result.stdout
    assert (
        "policy_pack_smoke :: uv run python "
        "scripts/policy_pack_smoke.py --strict (exit 2)"
    ) in result.stdout


def test_release_check_aggregate_mode_reports_multiple_failures(tmp_path: Path) -> None:
    fixture = build_release_check_fixture(
        tmp_path,
        uv_status={"policy_pack_smoke.py": 2, "launch_readiness.py": 3},
        direct_status={"repo_hygiene.sh": 4, "regression.sh": 5},
    )

    result = run_release_check_in_fixture(
        fixture,
        "--aggregate",
        "--allow-dirty",
        "--skip-downstream-smoke",
        "--skip-live-demo",
        "--skip-performance",
    )

    assert result.returncode == 1, result.stderr
    assert "Release check failed with 4 failed gate(s)." in result.stdout
    assert (
        "policy_pack_smoke :: uv run python "
        "scripts/policy_pack_smoke.py --strict (exit 2)"
    ) in result.stdout
    assert (
        "launch_readiness :: uv run python "
        "scripts/launch_readiness.py --strict (exit 3)"
    ) in result.stdout
    assert "repo_hygiene :: scripts/repo_hygiene.sh (exit 4)" in result.stdout
    assert "regression_security :: scripts/regression.sh --security (exit 5)" in result.stdout


def test_aha_failure_demo_script_is_syntax_valid() -> None:
    script = REPO_ROOT / "scripts" / "aha_failure_demo.sh"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_aha_failure_demo_wrapper_documents_expected_block() -> None:
    script = (REPO_ROOT / "scripts" / "aha_failure_demo.sh").read_text(encoding="utf-8")

    assert "expected output: entroping run blocks on request_id_header" in script
    assert "scripts/ai_regression_demo.sh" in script
