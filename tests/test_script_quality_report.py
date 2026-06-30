import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "script_quality_report.py"


def _run_script_quality(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
    )


def _prepare_repo(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "typed_script.py").write_text(
        "def typed(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (scripts / "partial_script.py").write_text(
        "def partial(value):\n    return value\n",
        encoding="utf-8",
    )


def _write_coverage_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "files": {
                    "scripts/typed_script.py": {
                        "summary": {
                            "num_statements": 2,
                            "covered_lines": 2,
                            "missing_lines": 0,
                            "percent_covered": 100.0,
                        }
                    },
                    "scripts/partial_script.py": {
                        "summary": {
                            "num_statements": 2,
                            "covered_lines": 1,
                            "missing_lines": 1,
                            "percent_covered": 50.0,
                        }
                    },
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_lower_coverage_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "files": {
                    "scripts/typed_script.py": {
                        "summary": {
                            "num_statements": 2,
                            "covered_lines": 1,
                            "missing_lines": 1,
                            "percent_covered": 50.0,
                        }
                    },
                    "scripts/partial_script.py": {
                        "summary": {
                            "num_statements": 2,
                            "covered_lines": 0,
                            "missing_lines": 2,
                            "percent_covered": 0.0,
                        }
                    },
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_script_quality_report_help_exposes_inputs() -> None:
    result = _run_script_quality("--help")

    assert result.returncode == 0
    assert "--repo-root" in result.stdout
    assert "--coverage-output" in result.stdout
    assert "--coverage-json" in result.stdout
    assert "--baseline" in result.stdout
    assert "--dry-run" in result.stdout


def test_script_quality_report_dry_run_lists_planned_actions(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    output = tmp_path / "reports" / "script-quality-report.json"
    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--output",
        str(output),
        "--dry-run",
    )

    assert result.returncode == 0
    assert "Script quality report dry run:" in result.stdout
    assert "Would run pytest --cov=scripts for script-focused test files." in result.stdout
    assert "Would write machine-readable JSON report under reports/." in result.stdout
    assert not output.exists()


def test_script_quality_report_generates_json_report_and_no_baseline(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    coverage_json = tmp_path / "script-coverage.json"
    _write_coverage_json(coverage_json)
    output = tmp_path / "reports" / "script-quality-report.json"
    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(coverage_json),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.script-quality-report.v1"
    assert payload["coverage"]["statements"] == 4
    assert payload["coverage"]["percent_covered"] == 75.0
    assert payload["typing"]["total_functions"] == 2
    assert payload["typing"]["typed_functions"] == 1
    assert payload["typing"]["function_annotation_coverage_percent"] == 50.0
    assert payload["ratchet"]["status"] == "not_configured"
    assert not payload["ratchet"]["enabled"]


def test_script_quality_report_baseline_regresses_fail(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    baseline_cov = tmp_path / "baseline-coverage.json"
    _write_coverage_json(baseline_cov)
    baseline_output = tmp_path / "reports" / "baseline.json"
    baseline = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(baseline_cov),
        "--output",
        str(baseline_output),
    )
    assert baseline.returncode == 0, baseline.stderr

    regression_cov = tmp_path / "regression-coverage.json"
    _write_lower_coverage_json(regression_cov)
    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(regression_cov),
        "--baseline",
        str(baseline_output),
        "--output",
        str(tmp_path / "reports" / "regression.json"),
    )

    assert result.returncode == 1
    assert "ratchet failed" in result.stderr.lower()
    regression = json.loads((tmp_path / "reports" / "regression.json").read_text(encoding="utf-8"))
    assert regression["ratchet"]["status"] == "regressed"
    assert regression["ratchet"]["coverage_delta"] < 0
