import configparser
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "script_quality_report.py"
ANALYZER_SCRIPT_PATHS = (
    "scripts/pytest_collection_manifest.py",
    "scripts/test_taxonomy.py",
    "scripts/source_maintainability_ratchet.py",
)


def _load_script_quality_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("script_quality_report_under_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script_quality(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_script_coverage_subprocess_uses_ci_viable_bounded_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script_quality_module()
    script_test = tmp_path / "tests" / "test_example_script.py"
    script_test.parent.mkdir(parents=True)
    script_test.write_text("def test_example() -> None:\n    assert True\n", encoding="utf-8")
    coverage_output = tmp_path / "reports" / "script-coverage.json"
    captured_timeout: list[float] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeout = kwargs["timeout"]
        assert isinstance(timeout, (int, float))
        captured_timeout.append(float(timeout))
        coverage_output.write_text('{"files": {}}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module._run_script_coverage(
        tmp_path,
        Path("reports/script-coverage.json"),
        (script_test,),
    )

    assert result == coverage_output
    assert captured_timeout == [600.0]


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


def _write_selected_script_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.script-quality-ratchet-baseline.v1",
                "description": "Focused baseline for release-critical scripts.",
                "script_paths": ["scripts/typed_script.py"],
                "coverage": {
                    "statements": 2,
                    "covered_lines": 2,
                    "missing_lines": 0,
                    "percent_covered": 100.0,
                },
                "typing": {
                    "typed_functions": 1,
                    "total_functions": 1,
                    "function_annotation_coverage_percent": 100.0,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_generated_selected_scope_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.script-quality-report.v1",
                "coverage": {
                    "statements": 8,
                    "covered_lines": 2,
                    "missing_lines": 6,
                    "percent_covered": 25.0,
                    "files": [
                        {
                            "path": "scripts/typed_script.py",
                            "statements": 2,
                            "covered_lines": 2,
                            "missing_lines": 0,
                            "percent_covered": 100.0,
                        },
                        {
                            "path": "scripts/partial_script.py",
                            "statements": 6,
                            "covered_lines": 0,
                            "missing_lines": 6,
                            "percent_covered": 0.0,
                        },
                    ],
                },
                "typing": {
                    "typed_functions": 1,
                    "total_functions": 2,
                    "function_annotation_coverage_percent": 50.0,
                    "files": [
                        {
                            "path": "scripts/typed_script.py",
                            "typed_functions": 1,
                            "total_functions": 1,
                        },
                        {
                            "path": "scripts/partial_script.py",
                            "typed_functions": 0,
                            "total_functions": 1,
                        },
                    ],
                },
                "ratchet": {
                    "enabled": True,
                    "status": "passed",
                    "scope": "selected_scripts",
                    "script_paths": ["scripts/typed_script.py"],
                    "coverage_delta": 0.0,
                    "typing_delta": 0.0,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_selected_regression_coverage_json(path: Path) -> None:
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
                            "num_statements": 6,
                            "covered_lines": 0,
                            "missing_lines": 6,
                            "percent_covered": 0.0,
                        }
                    },
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _prepare_governed_repo(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir()
    for script_path in (*ANALYZER_SCRIPT_PATHS, "scripts/deferred.py"):
        path = root / script_path
        path.write_text(
            "def governed(value: int) -> int:\n    return value + 1\n",
            encoding="utf-8",
        )


def _write_governance_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.script-quality-ratchet-baseline.v1",
                "script_paths": list(ANALYZER_SCRIPT_PATHS),
                "deferred_subprocess_covered_scripts": ["scripts/deferred.py"],
                "coverage": {
                    "statements": 6,
                    "covered_lines": 3,
                    "missing_lines": 3,
                    "percent_covered": 50.0,
                    "files": [
                        {
                            "path": script_path,
                            "statements": 2,
                            "covered_lines": 1,
                            "missing_lines": 1,
                            "percent_covered": 50.0,
                        }
                        for script_path in ANALYZER_SCRIPT_PATHS
                    ],
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_governance_coverage_json(
    path: Path,
    *,
    regressed_path: str | None = None,
) -> None:
    covered_by_path = {script_path: 1 for script_path in ANALYZER_SCRIPT_PATHS}
    if regressed_path is not None:
        regressed_index = ANALYZER_SCRIPT_PATHS.index(regressed_path)
        compensating_path = ANALYZER_SCRIPT_PATHS[
            (regressed_index + 1) % len(ANALYZER_SCRIPT_PATHS)
        ]
        covered_by_path[regressed_path] = 0
        covered_by_path[compensating_path] = 2

    files: dict[str, object] = {}
    for script_path, covered_lines in covered_by_path.items():
        files[script_path] = {
            "summary": {
                "num_statements": 2,
                "covered_lines": covered_lines,
                "missing_lines": 2 - covered_lines,
                "percent_covered": covered_lines * 50.0,
            }
        }
    files["scripts/deferred.py"] = {
        "summary": {
            "num_statements": 2,
            "covered_lines": 0,
            "missing_lines": 2,
            "percent_covered": 0.0,
        }
    }
    path.write_text(json.dumps({"files": files}, sort_keys=True), encoding="utf-8")


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
    assert "subprocess coverage config:" in result.stdout
    assert "Would run pytest --cov=scripts for script-focused test files." in result.stdout
    assert "Would write machine-readable JSON report under reports/." in result.stdout
    assert not output.exists()


def test_script_quality_report_dry_run_lists_release_critical_tests() -> None:
    result = _run_script_quality("--dry-run")

    assert result.returncode == 0, result.stderr
    assert "tests/test_release_evidence.py" in result.stdout
    assert "tests/test_package_index_readiness.py" in result.stdout
    assert "tests/test_factory_review_packet.py" in result.stdout
    assert "tests/test_factory_inbox.py" in result.stdout
    assert "tests/test_doc_governance_script.py" in result.stdout


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


def test_script_quality_report_baseline_can_ratchet_selected_script_paths(
    tmp_path: Path,
) -> None:
    _prepare_repo(tmp_path)
    coverage_json = tmp_path / "script-coverage.json"
    _write_coverage_json(coverage_json)
    baseline_path = tmp_path / "ratchet-baseline.json"
    _write_selected_script_baseline(baseline_path)
    output = tmp_path / "reports" / "selected.json"

    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(coverage_json),
        "--baseline",
        str(baseline_path),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ratchet"]["status"] == "passed"
    assert payload["ratchet"]["scope"] == "selected_scripts"
    assert payload["ratchet"]["script_paths"] == ["scripts/typed_script.py"]
    assert payload["ratchet"]["coverage_delta"] == 0.0


def test_script_quality_report_generated_selected_baseline_uses_selected_metrics(
    tmp_path: Path,
) -> None:
    _prepare_repo(tmp_path)
    coverage_json = tmp_path / "script-coverage.json"
    _write_selected_regression_coverage_json(coverage_json)
    baseline_path = tmp_path / "selected-report-baseline.json"
    _write_generated_selected_scope_baseline(baseline_path)
    output = tmp_path / "reports" / "selected-regression.json"

    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(coverage_json),
        "--baseline",
        str(baseline_path),
        "--output",
        str(output),
    )

    assert result.returncode == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ratchet"]["status"] == "regressed"
    assert payload["ratchet"]["coverage_delta"] == -50.0


def test_release_analyzers_are_selected_for_subprocess_coverage_governance() -> None:
    baseline = json.loads(
        (REPO_ROOT / "docs/meta/script-quality-ratchet-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    selected = set(baseline["script_paths"])
    deferred = set(baseline["deferred_subprocess_covered_scripts"])

    assert set(ANALYZER_SCRIPT_PATHS) <= selected
    assert not set(ANALYZER_SCRIPT_PATHS) & deferred


def test_coverage_configuration_enables_subprocess_measurement() -> None:
    parser = configparser.ConfigParser()
    config_path = REPO_ROOT / "docs/meta/script-coverage.ini"
    parser.read(config_path, encoding="utf-8")

    assert parser["run"].get("patch", "").split() == ["subprocess"]


def test_script_quality_report_names_governance_populations(tmp_path: Path) -> None:
    _prepare_governed_repo(tmp_path)
    coverage_json = tmp_path / "script-coverage.json"
    _write_governance_coverage_json(coverage_json)
    baseline_path = tmp_path / "ratchet-baseline.json"
    _write_governance_baseline(baseline_path)
    output = tmp_path / "reports" / "governance.json"

    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(coverage_json),
        "--baseline",
        str(baseline_path),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["governance"]["selected"] == {
        "count": 3,
        "script_paths": list(ANALYZER_SCRIPT_PATHS),
    }
    assert payload["governance"]["deferred"] == {
        "count": 1,
        "script_paths": ["scripts/deferred.py"],
    }
    assert payload["governance"]["covered"]["count"] == 3
    assert set(payload["governance"]["covered"]["script_paths"]) == set(
        ANALYZER_SCRIPT_PATHS
    )
    assert payload["governance"]["aggregate"]["count"] == 4
    assert "Selected ratchet coverage: 50.0% (3/6 statements)" in result.stdout
    assert "Aggregate script coverage: 37.5% (3/8 statements)" in result.stdout
    assert (
        "Script governance populations: selected=3 deferred=1 covered=3 aggregate=4"
        in result.stdout
    )


@pytest.mark.parametrize("regressed_path", ANALYZER_SCRIPT_PATHS)
def test_each_governed_analyzer_regression_fails_without_aggregate_loss(
    tmp_path: Path,
    regressed_path: str,
) -> None:
    _prepare_governed_repo(tmp_path)
    coverage_json = tmp_path / "script-coverage.json"
    _write_governance_coverage_json(coverage_json, regressed_path=regressed_path)
    baseline_path = tmp_path / "ratchet-baseline.json"
    _write_governance_baseline(baseline_path)
    output = tmp_path / "reports" / "regression.json"

    result = _run_script_quality(
        "--repo-root",
        str(tmp_path),
        "--coverage-json",
        str(coverage_json),
        "--baseline",
        str(baseline_path),
        "--output",
        str(output),
    )

    assert result.returncode == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ratchet"]["coverage_delta"] == 0.0
    assert payload["ratchet"]["regressed_script_paths"] == [regressed_path]
    assert "ratchet failed" in result.stderr.lower()
