"""Tests for deterministic run-to-run delta reports."""

import json

import pytest

from entroping.core.run_delta import (
    RUN_DELTA_REPORT_SCHEMA_VERSION,
    RunDeltaError,
    build_run_delta_report,
    render_run_delta_markdown,
    run_delta_report_to_dict,
)
from entroping.models.report import RunReport, RunReportSummary, RunTestReport


def _report(*tests: RunTestReport) -> RunReport:
    failed = sum(1 for test in tests if not test.passed)
    return RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(
            total=len(tests),
            passed=len(tests) - failed,
            failed=failed,
            exit_code=1 if failed else 0,
        ),
        tests=tests,
    )


def _test(
    path: str,
    *,
    status: str = "passed",
    exit_code: int = 0,
    duration_ms: int = 10,
    rule_ids: tuple[str, ...] = (),
) -> RunTestReport:
    return RunTestReport(
        path=path,
        execution_path=f".entroping/run/{path}",
        status=status,
        exit_code=exit_code,
        duration_ms=duration_ms,
        timeout_ms=30_000,
        rule_ids=rule_ids,
        stdout="Authorization: Bearer live-secret",
        stderr="token=live-secret",
    )


def test_run_delta_reports_added_resolved_changed_and_unchanged_failures() -> None:
    base = _report(
        _test("tests/health.hurl"),
        _test("tests/old_failure.hurl", status="failed", exit_code=1, rule_ids=("old_gate",)),
        _test("tests/still_failing.hurl", status="failed", exit_code=1, rule_ids=("latency",)),
        _test("tests/changed_failure.hurl", status="failed", exit_code=1),
    )
    current = _report(
        _test("tests/health.hurl", duration_ms=25),
        _test("tests/new_failure.hurl", status="failed", exit_code=1, rule_ids=("new_gate",)),
        _test("tests/old_failure.hurl"),
        _test("tests/still_failing.hurl", status="failed", exit_code=1, rule_ids=("latency",)),
        _test("tests/changed_failure.hurl", status="timeout", exit_code=124),
    )

    report = build_run_delta_report(base=base, current=current)

    assert not report.passed
    assert [item.path for item in report.added_failures] == ["tests/new_failure.hurl"]
    assert [item.path for item in report.resolved_failures] == ["tests/old_failure.hurl"]
    assert [item.path for item in report.unchanged_failures] == ["tests/still_failing.hurl"]
    assert [item.path for item in report.changed_failures] == ["tests/changed_failure.hurl"]
    assert report.latency_deltas[0].path == "tests/health.hurl"
    assert report.latency_deltas[0].delta_ms == 15
    assert report.policy_gate_deltas[0].path == "tests/new_failure.hurl"
    assert report.policy_gate_deltas[0].added_rule_ids == ("new_gate",)
    assert report.policy_gate_deltas[1].path == "tests/old_failure.hurl"
    assert report.policy_gate_deltas[1].resolved_rule_ids == ("old_gate",)

    payload = run_delta_report_to_dict(report)
    assert payload["schema_version"] == RUN_DELTA_REPORT_SCHEMA_VERSION
    assert payload["summary"] == {
        "base_total": 4,
        "current_total": 5,
        "added_failures": 1,
        "resolved_failures": 1,
        "changed_failures": 1,
        "unchanged_failures": 1,
        "latency_deltas": 1,
        "policy_gate_deltas": 2,
    }
    serialized = json.dumps(payload, sort_keys=True)
    markdown = render_run_delta_markdown(report)
    assert "tests/new_failure.hurl" in markdown
    assert "live-secret" not in serialized
    assert "live-secret" not in markdown
    assert "token=" not in serialized
    assert "token=" not in markdown


def test_run_delta_passes_when_failures_only_resolve() -> None:
    base = _report(_test("tests/refund.hurl", status="failed", exit_code=1))
    current = _report(_test("tests/refund.hurl"))

    report = build_run_delta_report(base=base, current=current)

    assert report.passed
    assert run_delta_report_to_dict(report)["status"] == "pass"
    assert "## Policy Gate Deltas\n\nNone." in render_run_delta_markdown(report)


def test_run_delta_treats_missing_current_failure_as_resolved() -> None:
    base = _report(_test("tests/removed_failure.hurl", status="failed", exit_code=1))
    current = _report()

    report = build_run_delta_report(base=base, current=current)

    assert report.passed
    assert [item.path for item in report.resolved_failures] == ["tests/removed_failure.hurl"]
    markdown = render_run_delta_markdown(report)
    assert "tests/removed_failure.hurl" in markdown
    assert "missing" in markdown


def test_run_delta_treats_failed_policy_rule_change_as_changed_failure() -> None:
    base = _report(
        _test("tests/policy.hurl", status="failed", exit_code=1, rule_ids=("old_gate",)),
    )
    current = _report(
        _test(
            "tests/policy.hurl",
            status="failed",
            exit_code=1,
            rule_ids=("new_gate", "old_gate"),
        ),
    )

    report = build_run_delta_report(base=base, current=current)

    assert not report.passed
    assert [item.path for item in report.changed_failures] == ["tests/policy.hurl"]
    assert report.changed_failures[0].base_rule_ids == ("old_gate",)
    assert report.changed_failures[0].current_rule_ids == ("new_gate", "old_gate")
    assert report.unchanged_failures == ()
    assert report.policy_gate_deltas[0].added_rule_ids == ("new_gate",)


def test_run_delta_rejects_duplicate_or_unsafe_test_paths() -> None:
    duplicate = _report(_test("tests/health.hurl"), _test("tests/health.hurl"))
    safe = _report(_test("tests/health.hurl"))

    with pytest.raises(RunDeltaError, match="duplicate test path"):
        build_run_delta_report(base=duplicate, current=safe)

    unsafe = _report(_test("tests/bad\npath.hurl"))
    with pytest.raises(RunDeltaError, match="unsafe test path"):
        build_run_delta_report(base=safe, current=unsafe)
