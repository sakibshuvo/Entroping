"""Unit tests for deterministic drift report comparison."""

import json
from pathlib import Path

import pytest

from entroping.core.drift_report import (
    DriftBaselineNotFoundError,
    DriftReportError,
    build_drift_report,
    build_missing_baseline_report,
    load_drift_baseline,
    write_drift_report,
)
from entroping.models.drift import DriftBaseline, DriftBaselineTest
from entroping.models.report import RunReport, RunReportSummary, RunTestReport


def _run_report(*tests: RunTestReport) -> RunReport:
    return RunReport(
        project="checkout-api",
        environment="staging",
        generated_at="2026-05-30T00:00:00+00:00",
        summary=RunReportSummary(
            total=len(tests),
            passed=sum(1 for test in tests if test.passed),
            failed=sum(1 for test in tests if not test.passed),
            exit_code=0 if all(test.passed for test in tests) else 1,
        ),
        tests=tests,
    )


def _test_report(
    path: str,
    *,
    status: str = "passed",
    exit_code: int = 0,
    rule_ids: tuple[str, ...] = ("global_latency",),
) -> RunTestReport:
    return RunTestReport(
        path=path,
        execution_path=f".entroping/run-1/{Path(path).name}",
        status=status,
        exit_code=exit_code,
        duration_ms=25,
        rule_ids=rule_ids,
        stdout="",
        stderr="",
    )


def test_load_drift_baseline_accepts_small_and_run_report_shaped_json(tmp_path: Path) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        json.dumps(
            {
                "project": "checkout-api",
                "environment": "staging",
                "generated_at": "ignored",
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": "ignored",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": ["global_latency"],
                        "stdout": "ignored",
                        "stderr": "ignored",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    baseline = load_drift_baseline(baseline_path)

    assert baseline.project == "checkout-api"
    assert baseline.environment == "staging"
    assert baseline.tests == (
        DriftBaselineTest(
            path="tests/health.hurl",
            status="passed",
            exit_code=0,
            rule_ids=("global_latency",),
        ),
    )


def test_build_drift_report_compares_results_in_deterministic_path_order(tmp_path: Path) -> None:
    baseline = DriftBaseline(
        project="checkout-api",
        environment="staging",
        tests=(
            DriftBaselineTest(
                path="tests/checkout.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
            ),
            DriftBaselineTest(
                path="tests/health.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("old_rule",),
            ),
            DriftBaselineTest(
                path="tests/missing.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
            ),
        ),
    )
    current = _run_report(
        _test_report("tests/checkout.hurl", status="failed", exit_code=1),
        _test_report("tests/health.hurl", rule_ids=("global_latency",)),
        _test_report("tests/new.hurl"),
    )

    report = build_drift_report(
        current=current,
        baseline=baseline,
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )

    assert [finding.kind for finding in report.findings] == [
        "result_changed",
        "assertions_changed",
        "missing_current_test",
        "new_current_test",
    ]
    assert [finding.path for finding in report.findings] == [
        "tests/checkout.hurl",
        "tests/health.hurl",
        "tests/missing.hurl",
        "tests/new.hurl",
    ]
    assert report.summary.drifted == 4
    assert not report.summary.missing_baseline


def test_write_missing_baseline_drift_report_is_machine_readable(tmp_path: Path) -> None:
    current = _run_report(_test_report("tests/health.hurl"))
    report = build_missing_baseline_report(
        current=current,
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )
    output = tmp_path / "reports" / "drift.json"

    write_drift_report(report, output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["summary"]["missing_baseline"] is True
    assert data["summary"]["drifted"] == 1
    assert data["findings"][0]["kind"] == "missing_baseline"
    assert "Copy .entroping/latest-run.json" in data["findings"][0]["message"]


def test_load_drift_baseline_rejects_missing_or_symlinked_baseline(tmp_path: Path) -> None:
    missing = tmp_path / ".entroping" / "drift-baseline.json"
    with pytest.raises(DriftBaselineNotFoundError):
        load_drift_baseline(missing)

    missing.parent.mkdir(parents=True)
    target = tmp_path / "outside.json"
    missing.symlink_to(target)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        load_drift_baseline(missing)


def test_load_drift_baseline_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside-state"
    outside_dir.mkdir()
    (outside_dir / "drift-baseline.json").write_text('{"tests":[]}\n', encoding="utf-8")
    (tmp_path / ".entroping").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        load_drift_baseline(tmp_path / ".entroping" / "drift-baseline.json")


def test_write_drift_report_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    report = build_missing_baseline_report(
        current=_run_report(_test_report("tests/health.hurl")),
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )
    outside_dir = tmp_path / "outside-reports"
    outside_dir.mkdir()
    (tmp_path / "reports").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        write_drift_report(report, tmp_path / "reports" / "drift.json")

    assert not (outside_dir / "drift.json").exists()
