"""Alpha launch-readiness evidence aggregation."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "launch_readiness.py"


def run_launch_readiness(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_launch_readiness_json_distinguishes_alpha_from_stable_core() -> None:
    result = run_launch_readiness("--format", "json", "--strict")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.alpha-launch-readiness.v1"
    assert payload["alpha_launch_ready"] is True
    assert payload["stable_core_ready"] is False
    assert "stable-core still requires repeated release evidence" in payload["stable_core_blockers"]
    assert payload["checks"]["policy_pack_smoke"]["status"] == "present"
    assert payload["checks"]["demo_matrix"]["status"] == "present"
    assert payload["checks"]["public_claims_audit"]["status"] == "present"


def test_launch_readiness_strict_rejects_missing_evidence(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Entroping\n", encoding="utf-8")

    result = run_launch_readiness("--root", str(tmp_path), "--strict")

    assert result.returncode == 1
    assert "alpha launch-readiness check failed" in result.stderr
    assert "scripts/policy_pack_smoke.py" in result.stderr
    assert "scripts/demo_matrix.sh" in result.stderr


def test_release_check_runs_launch_readiness_gate() -> None:
    release_script = (REPO_ROOT / "scripts" / "release_check.sh").read_text(encoding="utf-8")

    assert "scripts/launch_readiness.py --strict" in release_script
