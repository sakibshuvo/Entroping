"""Smoke tests for bounded performance evidence generation."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "performance_smoke.py"


def run_performance_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_performance_smoke_script_writes_reviewable_evidence(tmp_path: Path) -> None:
    output = tmp_path / "performance-smoke.json"

    result = run_performance_smoke(
        "--hurl-files",
        "4",
        "--traffic-events",
        "6",
        "--traffic-retention",
        "3",
        "--suite-max-ms",
        "10000",
        "--traffic-max-ms",
        "10000",
        "--max-report-bytes",
        "500000",
        "--max-db-bytes",
        "500000",
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert "Performance smoke OK" in result.stdout
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "entroping.performance-smoke.v1"
    assert evidence["summary"] == {"total": 2, "passed": 2, "failed": 0}
    assert {check["name"] for check in evidence["checks"]} == {
        "large_suite",
        "traffic_store",
    }
    large_suite = next(
        check for check in evidence["checks"] if check["name"] == "large_suite"
    )
    traffic_store = next(
        check for check in evidence["checks"] if check["name"] == "traffic_store"
    )
    assert large_suite["metrics"]["hurl_files"] == 4
    assert large_suite["metrics"]["parallel_workers"] == 4
    assert traffic_store["metrics"]["inserted_events"] == 6
    assert traffic_store["metrics"]["retained_events"] == 3


def test_performance_smoke_script_fails_closed_on_threshold_breach(
    tmp_path: Path,
) -> None:
    output = tmp_path / "performance-smoke.json"

    result = run_performance_smoke(
        "--hurl-files",
        "2",
        "--traffic-events",
        "2",
        "--traffic-retention",
        "2",
        "--max-report-bytes",
        "1",
        "--output",
        str(output),
    )

    assert result.returncode == 1
    assert "Performance smoke FAILED" in result.stdout
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["summary"]["failed"] == 1
    failed = [check for check in evidence["checks"] if not check["passed"]]
    assert [check["name"] for check in failed] == ["large_suite"]


def test_performance_smoke_is_documented_as_release_owner_gate() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    test_strategy = (REPO_ROOT / "docs" / "meta" / "TEST_STRATEGY.md").read_text(
        encoding="utf-8"
    )
    release_checklist = (
        REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md"
    ).read_text(encoding="utf-8")

    assert "scripts/performance_smoke.py" in readme
    assert "scripts/performance_smoke.py" in test_strategy
    assert "scripts/performance_smoke.py" in release_checklist
    assert "reports/performance-smoke.json" in test_strategy
