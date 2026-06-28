"""Unit tests for deterministic drift report comparison."""

import json
from pathlib import Path

import pytest

import entroping.core.drift_report as drift_report
from entroping.core.drift_report import (
    DRIFT_BASELINE_SCHEMA_VERSION,
    DriftBaselineNotFoundError,
    DriftReportError,
    append_dependency_drift_findings,
    build_drift_report,
    build_missing_baseline_report,
    build_reviewed_drift_baseline,
    load_dependency_drift_baseline,
    load_drift_baseline,
    promote_reviewed_drift_baseline_candidate,
    write_drift_report,
    write_reviewed_drift_baseline_candidate,
)
from entroping.core.safe_write import SafeWriteError
from entroping.models.drift import (
    DependencyDriftBaseline,
    DependencyDriftRoute,
    DriftBaseline,
    DriftBaselineTest,
)
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
                        "response": {
                            "status_code": 200,
                            "headers": {
                                "content-type": "application/json",
                                "date": "volatile",
                                "x-request-id": "req_123",
                            },
                            "body_shape": ["$.status:string", "$:object"],
                        },
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
            duration_ms=10,
            response_status_code=200,
            response_headers=(("content-type", "application/json"),),
            response_body_shape=("$:object", "$.status:string"),
        ),
    )


def test_load_drift_baseline_accepts_missing_optional_project_fields(tmp_path: Path) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text('{"tests":[]}\n', encoding="utf-8")

    baseline = load_drift_baseline(baseline_path)

    assert baseline.project == ""
    assert baseline.environment == ""
    assert baseline.tests == ()


def test_load_drift_baseline_wraps_json_parse_errors(tmp_path: Path) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text("{", encoding="utf-8")

    with pytest.raises(DriftReportError, match="Could not parse drift baseline"):
        load_drift_baseline(baseline_path)


def test_load_drift_baseline_rejects_oversize_baseline_before_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text('{"tests":[]}\n', encoding="utf-8")
    monkeypatch.setattr(drift_report, "_MAX_DRIFT_BASELINE_BYTES", 8, raising=False)

    with pytest.raises(DriftReportError, match="exceeds 8 bytes"):
        load_drift_baseline(baseline_path)


def test_load_dependency_drift_baseline_accepts_stable_route_shape(tmp_path: Path) -> None:
    baseline_path = tmp_path / ".entroping" / "dependency-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        json.dumps(
            {
                "source_label": "checkout-ui",
                "routes": [
                    {
                        "destination_host": "PAYMENTS.EXAMPLE.TEST",
                        "method": "post",
                        "path_template": "/charges/{id}",
                        "call_count": 27,
                        "latency_average_ms": 35,
                    }
                ],
            },
        ),
        encoding="utf-8",
    )

    baseline = load_dependency_drift_baseline(baseline_path)

    assert baseline == DependencyDriftBaseline(
        source_label="checkout-ui",
        routes=(
            DependencyDriftRoute(
                destination_host="payments.example.test",
                method="POST",
                path_template="/charges/{id}",
            ),
        ),
    )


def test_load_dependency_drift_baseline_wraps_json_parse_errors(tmp_path: Path) -> None:
    baseline_path = tmp_path / ".entroping" / "dependency-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text("{", encoding="utf-8")

    with pytest.raises(DriftReportError, match="Could not parse dependency drift baseline"):
        load_dependency_drift_baseline(baseline_path)


def test_load_dependency_drift_baseline_rejects_oversize_baseline_before_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / ".entroping" / "dependency-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text('{"routes":[]}\n', encoding="utf-8")
    monkeypatch.setattr(drift_report, "_MAX_DRIFT_BASELINE_BYTES", 8, raising=False)

    with pytest.raises(DriftReportError, match="exceeds 8 bytes"):
        load_dependency_drift_baseline(baseline_path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("[]", "must be a JSON object"),
        ('{"source_label":123,"routes":[]}', "source_label"),
        ('{"source_label":"client"}', "must contain a routes list"),
        ('{"routes":[null]}', "must be a JSON object"),
        (
            '{"routes":[{"destination_host":"","method":"GET","path_template":"/health"}]}',
            "destination_host",
        ),
        (
            '{"routes":[{"destination_host":"api.example.test","method":"","path_template":"/health"}]}',
            "method",
        ),
        (
            '{"routes":[{"destination_host":"user:secret@api.example.test",'
            '"method":"GET","path_template":"/health"}]}',
            "destination_host",
        ),
        (
            '{"routes":[{"destination_host":"api.example.test","method":"GET POST",'
            '"path_template":"/health"}]}',
            "method",
        ),
        (
            '{"routes":[{"destination_host":"api.example.test","method":"GET","path_template":"health"}]}',
            "path_template",
        ),
        (
            '{"routes":[{"destination_host":"api.example.test","method":"GET",'
            '"path_template":"/health?token=secret"}]}',
            "path_template",
        ),
    ],
)
def test_load_dependency_drift_baseline_rejects_malformed_routes(
    tmp_path: Path,
    payload: str,
    message: str,
) -> None:
    baseline_path = tmp_path / ".entroping" / "dependency-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(payload + "\n", encoding="utf-8")

    with pytest.raises(DriftReportError, match=message):
        load_dependency_drift_baseline(baseline_path)


def test_load_drift_baseline_accepts_absent_and_partial_response_fields(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "path": "tests/no-response.hurl",
                        "status": "passed",
                        "exit_code": 0,
                    },
                    {
                        "path": "tests/partial-response.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "response": {
                            "headers": {
                                "content-type": 123,
                                "date": "volatile",
                                7: "ignored",
                            },
                            "body_shape": ["$:object", "bad\n"],
                        },
                    },
                    {
                        "path": "tests/malformed-optional-response.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "response": {
                            "headers": "not-a-dict",
                            "body_shape": "not-a-list",
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    baseline = load_drift_baseline(baseline_path)

    assert baseline.tests[0].response_status_code is None
    assert baseline.tests[0].response_headers == ()
    assert baseline.tests[0].response_body_shape == ()
    assert baseline.tests[1].response_status_code is None
    assert baseline.tests[1].response_headers == ()
    assert baseline.tests[1].response_body_shape == ("$:object",)
    assert baseline.tests[2].response_headers == ()
    assert baseline.tests[2].response_body_shape == ()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("[]", "must be a JSON object"),
        ('{"project":"checkout-api"}', "must contain a tests list"),
        ('{"tests":[null]}', "must be a JSON object"),
        ('{"tests":[{"path":"tests/health.hurl","status":"passed","exit_code":"0"}]}', "exit_code"),
        (
            '{"tests":[{"path":"tests/health.hurl","status":"passed","exit_code":0,'
            '"rule_ids":[1]}]}',
            "rule_ids",
        ),
        ('{"tests":[{"path":"","status":"passed","exit_code":0}]}', "non-empty string"),
        (
            '{"tests":[{"path":"tests/health.hurl","status":"bad\\n","exit_code":0}]}',
            "non-empty string",
        ),
        ('{"project":123,"tests":[]}', "project/environment fields must be strings"),
        (
            '{"tests":[{"path":"tests/health.hurl","status":"passed","exit_code":0,'
            '"response":[]}]}',
            "response must be a JSON object",
        ),
        (
            '{"tests":[{"path":"tests/health.hurl","status":"passed","exit_code":0,'
            '"response":{"status_code":"200"}}]}',
            "response.status_code must be an integer",
        ),
        (
            '{"tests":[{"path":"tests/health.hurl","status":"passed","exit_code":0,'
            '"duration_ms":"10"}]}',
            "duration_ms must be a non-negative integer",
        ),
    ],
)
def test_load_drift_baseline_rejects_malformed_baseline_json(
    tmp_path: Path,
    payload: str,
    message: str,
) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(payload + "\n", encoding="utf-8")

    with pytest.raises(DriftReportError, match=message):
        load_drift_baseline(baseline_path)


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


def test_append_dependency_drift_findings_compares_routes_in_stable_order(tmp_path: Path) -> None:
    run_report = build_drift_report(
        current=_run_report(_test_report("tests/health.hurl")),
        baseline=DriftBaseline(
            project="checkout-api",
            environment="staging",
            tests=(
                DriftBaselineTest(
                    path="tests/health.hurl",
                    status="passed",
                    exit_code=0,
                    rule_ids=("global_latency",),
                ),
            ),
        ),
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )
    dependency_baseline = DependencyDriftBaseline(
        source_label="client",
        routes=(
            DependencyDriftRoute(
                destination_host="billing.example.test",
                method="GET",
                path_template="/accounts/{id}",
            ),
            DependencyDriftRoute(
                destination_host="payments.example.test",
                method="POST",
                path_template="/charges/{id}",
            ),
        ),
    )

    report = append_dependency_drift_findings(
        run_report,
        baseline=dependency_baseline,
        current_routes=(
            DependencyDriftRoute(
                destination_host="inventory.example.test",
                method="GET",
                path_template="/items/{id}",
            ),
            DependencyDriftRoute(
                destination_host="payments.example.test",
                method="POST",
                path_template="/charges/{id}",
            ),
        ),
        baseline_path=tmp_path / ".entroping" / "dependency-baseline.json",
    )

    assert [finding.kind for finding in report.findings] == [
        "missing_dependency_route",
        "new_dependency_route",
    ]
    assert [finding.path for finding in report.findings] == [
        "dependency:billing.example.test GET /accounts/{id}",
        "dependency:inventory.example.test GET /items/{id}",
    ]
    assert report.findings[0].baseline == {
        "destination_host": "billing.example.test",
        "method": "GET",
        "path_template": "/accounts/{id}",
    }
    assert report.findings[0].current == {}
    assert report.summary.baseline_tests == 1
    assert report.summary.current_tests == 1
    assert report.summary.drifted == 2
    assert "dependency-baseline.json" in report.baseline_path


def test_build_drift_report_compares_structured_response_fingerprints(
    tmp_path: Path,
) -> None:
    baseline = DriftBaseline(
        project="checkout-api",
        environment="staging",
        tests=(
            DriftBaselineTest(
                path="tests/checkout.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                response_status_code=201,
                response_headers=(("content-type", "application/json"),),
                response_body_shape=("$:object", "$.id:string"),
            ),
            DriftBaselineTest(
                path="tests/no-current-response.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                response_status_code=200,
                response_headers=(("content-type", "application/json"),),
                response_body_shape=("$:object",),
            ),
        ),
    )
    current = _run_report(
        RunTestReport(
            path="tests/checkout.hurl",
            execution_path=".entroping/run/checkout.hurl",
            status="passed",
            exit_code=0,
            duration_ms=25,
            rule_ids=("global_latency",),
            stdout="",
            stderr="",
            response_status_code=500,
            response_headers=(
                ("content-type", "application/problem+json"),
                ("vary", "Accept"),
            ),
            response_body_shape=("$:object", "$.error:string"),
        ),
        _test_report("tests/no-current-response.hurl"),
    )

    report = build_drift_report(
        current=current,
        baseline=baseline,
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )

    assert [finding.kind for finding in report.findings] == [
        "response_status_changed",
        "response_header_changed",
        "response_body_shape_changed",
        "response_snapshot_missing",
    ]
    assert report.findings[0].baseline == {"response_status_code": 201}
    assert report.findings[0].current == {"response_status_code": 500}
    assert report.findings[1].baseline == {
        "header": "content-type",
        "value": "application/json",
    }
    assert report.findings[1].current == {
        "header": "content-type",
        "value": "application/problem+json",
    }
    assert report.summary.drifted == 4

    no_change_header_baseline = DriftBaseline(
        project="checkout-api",
        environment="staging",
        tests=(
            DriftBaselineTest(
                path="tests/vary.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                response_headers=(("vary", "Accept"),),
            ),
        ),
    )
    no_change_report = build_drift_report(
        current=_run_report(
            RunTestReport(
                path="tests/vary.hurl",
                execution_path=".entroping/run/vary.hurl",
                status="passed",
                exit_code=0,
                duration_ms=25,
                rule_ids=("global_latency",),
                stdout="",
                stderr="",
                response_headers=(("vary", "Accept"),),
            ),
        ),
        baseline=no_change_header_baseline,
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )
    assert no_change_report.findings == ()


def test_build_drift_report_ignores_current_response_when_baseline_has_none(
    tmp_path: Path,
) -> None:
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
        ),
    )
    current = _run_report(
        RunTestReport(
            path="tests/checkout.hurl",
            execution_path=".entroping/run/checkout.hurl",
            status="passed",
            exit_code=0,
            duration_ms=25,
            rule_ids=("global_latency",),
            stdout="",
            stderr="",
            response_status_code=201,
            response_headers=(("content-type", "application/json"),),
            response_body_shape=("$:object",),
        ),
    )

    report = build_drift_report(
        current=current,
        baseline=baseline,
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )

    assert report.findings == ()
    assert report.summary.drifted == 0


def test_build_drift_report_flags_material_latency_regressions_without_minor_noise(
    tmp_path: Path,
) -> None:
    baseline = DriftBaseline(
        project="checkout-api",
        environment="staging",
        tests=(
            DriftBaselineTest(
                path="tests/regressed.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                duration_ms=400,
            ),
            DriftBaselineTest(
                path="tests/minor-noise.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                duration_ms=400,
            ),
            DriftBaselineTest(
                path="tests/percent-noise.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
                duration_ms=1_000,
            ),
            DriftBaselineTest(
                path="tests/no-baseline-duration.hurl",
                status="passed",
                exit_code=0,
                rule_ids=("global_latency",),
            ),
        ),
    )
    current = _run_report(
        RunTestReport(
            path="tests/regressed.hurl",
            execution_path=".entroping/run/regressed.hurl",
            status="passed",
            exit_code=0,
            duration_ms=625,
            rule_ids=("global_latency",),
            stdout="",
            stderr="",
        ),
        RunTestReport(
            path="tests/minor-noise.hurl",
            execution_path=".entroping/run/minor-noise.hurl",
            status="passed",
            exit_code=0,
            duration_ms=480,
            rule_ids=("global_latency",),
            stdout="",
            stderr="",
        ),
        RunTestReport(
            path="tests/percent-noise.hurl",
            execution_path=".entroping/run/percent-noise.hurl",
            status="passed",
            exit_code=0,
            duration_ms=1_200,
            rule_ids=("global_latency",),
            stdout="",
            stderr="",
        ),
        RunTestReport(
            path="tests/no-baseline-duration.hurl",
            execution_path=".entroping/run/no-baseline-duration.hurl",
            status="passed",
            exit_code=0,
            duration_ms=2_000,
            rule_ids=("global_latency",),
            stdout="",
            stderr="",
        ),
    )

    report = build_drift_report(
        current=current,
        baseline=baseline,
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )

    assert [finding.kind for finding in report.findings] == ["latency_regressed"]
    assert report.findings[0].severity == "warning"
    assert report.findings[0].baseline == {"duration_ms": 400}
    assert report.findings[0].current == {
        "duration_ms": 625,
        "increase_ms": 225,
        "increase_percent": 56,
    }
    assert report.summary.drifted == 1


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
    assert "reports/drift-baseline.candidate.json" in data["findings"][0]["message"]


def test_build_reviewed_drift_baseline_is_value_free_and_deterministic() -> None:
    current = _run_report(
        RunTestReport(
            path="tests/z-health.hurl",
            execution_path=".entroping/run-1/z-health.hurl",
            status="passed",
            exit_code=0,
            duration_ms=42,
            rule_ids=("global_latency",),
            stdout="HTTP 200\nAuthorization: Bearer live-secret\n\n{\"token\":\"live-secret\"}",
            stderr="stderr live-secret",
            response_status_code=200,
            response_headers=(
                ("content-type", "application/json"),
                ("date", "volatile"),
                ("x-request-id", "req_123"),
                ("cache-control", "[REDACTED]"),
            ),
            response_body_shape=(
                "$.token:string",
                "$:object",
                "bad\u0000shape",
            ),
        ),
        _test_report("tests/a-health.hurl", rule_ids=("auth_required", "global_latency")),
    )

    baseline = build_reviewed_drift_baseline(current)

    assert [test.path for test in baseline.tests] == [
        "tests/a-health.hurl",
        "tests/z-health.hurl",
    ]
    assert baseline.tests[1] == DriftBaselineTest(
        path="tests/z-health.hurl",
        status="passed",
        exit_code=0,
        rule_ids=("global_latency",),
        duration_ms=42,
        response_status_code=200,
        response_headers=(("content-type", "application/json"),),
        response_body_shape=("$:object", "$.token:string"),
    )


def test_write_reviewed_drift_baseline_candidate_is_safe_and_sanitized(
    tmp_path: Path,
) -> None:
    current = _run_report(
        RunTestReport(
            path="tests/health.hurl",
            execution_path=".entroping/run-1/health.hurl",
            status="passed",
            exit_code=0,
            duration_ms=25,
            rule_ids=("global_latency",),
            stdout="HTTP 200\nContent-Type: application/json\n\n{\"secret\":\"live-secret\"}",
            stderr="live-secret",
            response_status_code=200,
            response_headers=(
                ("content-type", "application/json"),
                ("set-cookie", "session=live-secret"),
            ),
            response_body_shape=("$:object", "$.secret:string"),
        )
    )
    output = tmp_path / "reports" / "drift-baseline.candidate.json"

    write_reviewed_drift_baseline_candidate(current, output)

    content = output.read_text(encoding="utf-8")
    data = json.loads(content)
    assert data == {
        "environment": "staging",
        "project": "checkout-api",
        "schema_version": DRIFT_BASELINE_SCHEMA_VERSION,
        "tests": [
            {
                "duration_ms": 25,
                "exit_code": 0,
                "path": "tests/health.hurl",
                "response": {
                    "body_shape": ["$:object", "$.secret:string"],
                    "headers": {"content-type": "application/json"},
                    "status_code": 200,
                },
                "rule_ids": ["global_latency"],
                "status": "passed",
            }
        ],
    }
    assert "stdout" not in content
    assert "stderr" not in content
    assert "execution_path" not in content
    assert "set-cookie" not in content
    assert "live-secret" not in content


def test_promote_reviewed_drift_baseline_candidate_writes_active_baseline(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "reports" / "drift-baseline.candidate.json"
    active = tmp_path / ".entroping" / "drift-baseline.json"
    candidate.parent.mkdir()
    candidate.write_text(
        json.dumps(
            {
                "schema_version": DRIFT_BASELINE_SCHEMA_VERSION,
                "project": "checkout-api",
                "environment": "staging",
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 25,
                        "rule_ids": ["global_latency"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = promote_reviewed_drift_baseline_candidate(
        project_root=tmp_path,
        candidate_path=Path("reports") / "drift-baseline.candidate.json",
        output_path=Path(".entroping") / "drift-baseline.json",
    )

    assert result.candidate_path == candidate
    assert result.output_path == active
    assert result.test_count == 1
    assert json.loads(active.read_text(encoding="utf-8")) == json.loads(
        candidate.read_text(encoding="utf-8")
    )
    assert load_drift_baseline(active).tests == (
        DriftBaselineTest(
            path="tests/health.hurl",
            status="passed",
            exit_code=0,
            duration_ms=25,
            rule_ids=("global_latency",),
        ),
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("{", "Could not parse drift baseline candidate"),
        ('[]', "must be a JSON object"),
        ('{"tests":[]}', "schema_version"),
        (
            json.dumps({"schema_version": "entroping.drift-baseline.v0", "tests": []}),
            "Unsupported drift baseline candidate schema_version",
        ),
        (
            json.dumps({"schema_version": "entroping.drift-baseline.v999", "tests": []}),
            "Unsupported drift baseline candidate schema_version",
        ),
        (
            json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": {}}),
            "must contain a tests list",
        ),
    ],
)
def test_promote_reviewed_drift_baseline_candidate_rejects_invalid_candidates(
    tmp_path: Path,
    payload: str,
    message: str,
) -> None:
    candidate = tmp_path / "reports" / "drift-baseline.candidate.json"
    candidate.parent.mkdir()
    candidate.write_text(payload + "\n", encoding="utf-8")

    with pytest.raises(DriftReportError, match=message):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    assert not (tmp_path / ".entroping" / "drift-baseline.json").exists()


def test_promote_reviewed_drift_baseline_candidate_rejects_oversize_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "reports" / "drift-baseline.candidate.json"
    candidate.parent.mkdir()
    candidate.write_text(
        json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": []}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drift_report, "_MAX_DRIFT_BASELINE_BYTES", 8)

    with pytest.raises(DriftReportError, match="exceeds 8 bytes"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    assert not (tmp_path / ".entroping" / "drift-baseline.json").exists()


def test_promote_reviewed_drift_baseline_candidate_rejects_unsafe_paths(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-candidate.json"
    outside.write_text(
        json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": []}),
        encoding="utf-8",
    )

    with pytest.raises(DriftReportError, match="candidate path must stay under"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=outside,
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    candidate = tmp_path / "reports" / "drift-baseline.candidate.json"
    candidate.parent.mkdir()
    candidate.write_text(
        json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": []}),
        encoding="utf-8",
    )
    with pytest.raises(DriftReportError, match="active drift baseline path must stay under"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=tmp_path.parent / "outside-baseline.json",
        )


def test_promote_reviewed_drift_baseline_candidate_rejects_missing_candidate(
    tmp_path: Path,
) -> None:
    with pytest.raises(DriftBaselineNotFoundError, match="candidate not found"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    assert not (tmp_path / ".entroping" / "drift-baseline.json").exists()


def test_promote_reviewed_drift_baseline_candidate_rejects_candidate_directory(
    tmp_path: Path,
) -> None:
    candidate_dir = tmp_path / "reports" / "drift-baseline.candidate.json"
    candidate_dir.mkdir(parents=True)

    with pytest.raises(DriftReportError, match="candidate path is not a file"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    assert not (tmp_path / ".entroping" / "drift-baseline.json").exists()


def test_promote_reviewed_drift_baseline_candidate_rejects_symlinked_paths(
    tmp_path: Path,
) -> None:
    outside_reports = tmp_path / "outside-reports"
    outside_reports.mkdir()
    (outside_reports / "drift-baseline.candidate.json").write_text(
        json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": []}),
        encoding="utf-8",
    )
    (tmp_path / "reports").symlink_to(outside_reports, target_is_directory=True)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    (tmp_path / "reports").unlink()
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "drift-baseline.candidate.json").write_text(
        json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": []}),
        encoding="utf-8",
    )
    outside_state = tmp_path / "outside-state"
    outside_state.mkdir()
    (tmp_path / ".entroping").symlink_to(outside_state, target_is_directory=True)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )
    assert not (outside_state / "drift-baseline.json").exists()


def test_promote_reviewed_drift_baseline_candidate_preserves_active_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "reports" / "drift-baseline.candidate.json"
    active = tmp_path / ".entroping" / "drift-baseline.json"
    candidate.parent.mkdir()
    active.parent.mkdir()
    candidate.write_text(
        json.dumps({"schema_version": DRIFT_BASELINE_SCHEMA_VERSION, "tests": []}),
        encoding="utf-8",
    )
    active.write_text("old-baseline\n", encoding="utf-8")

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(drift_report, "safe_write_text", fail_safe_write)

    with pytest.raises(DriftReportError, match="temporary write failed"):
        promote_reviewed_drift_baseline_candidate(
            project_root=tmp_path,
            candidate_path=Path("reports") / "drift-baseline.candidate.json",
            output_path=Path(".entroping") / "drift-baseline.json",
        )

    assert active.read_text(encoding="utf-8") == "old-baseline\n"


def test_write_reviewed_drift_baseline_candidate_rejects_final_baseline_path(
    tmp_path: Path,
) -> None:
    current = _run_report(_test_report("tests/health.hurl"))
    active_baseline = tmp_path / ".entroping" / "drift-baseline.json"

    with pytest.raises(DriftReportError, match="candidate file"):
        write_reviewed_drift_baseline_candidate(current, active_baseline)

    assert not active_baseline.exists()


def test_write_reviewed_drift_baseline_candidate_rejects_symlinked_parent_directory(
    tmp_path: Path,
) -> None:
    current = _run_report(_test_report("tests/health.hurl"))
    outside_dir = tmp_path / "outside-reports"
    outside_dir.mkdir()
    (tmp_path / "reports").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        write_reviewed_drift_baseline_candidate(
            current,
            tmp_path / "reports" / "drift-baseline.candidate.json",
        )

    assert not (outside_dir / "drift-baseline.candidate.json").exists()


def test_write_drift_report_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = build_missing_baseline_report(
        current=_run_report(_test_report("tests/health.hurl")),
        baseline_path=tmp_path / ".entroping" / "drift-baseline.json",
    )
    output = tmp_path / "reports" / "drift.json"
    output.parent.mkdir()
    output.write_text("old\n", encoding="utf-8")

    def fail_safe_write(path: Path, content: str, *, artifact: str) -> Path:
        _ = path, content, artifact
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(drift_report, "safe_write_text", fail_safe_write)

    with pytest.raises(DriftReportError, match="temporary write failed"):
        write_drift_report(report, output)

    assert output.read_text(encoding="utf-8") == "old\n"


def test_load_drift_baseline_rejects_missing_or_symlinked_baseline(tmp_path: Path) -> None:
    missing = tmp_path / ".entroping" / "drift-baseline.json"
    with pytest.raises(DriftBaselineNotFoundError):
        load_drift_baseline(missing)

    missing.parent.mkdir(parents=True)
    target = tmp_path / "outside.json"
    missing.symlink_to(target)

    with pytest.raises(DriftReportError, match="symlinked path component"):
        load_drift_baseline(missing)


def test_load_drift_baseline_rejects_directory_baseline_path(tmp_path: Path) -> None:
    baseline_path = tmp_path / ".entroping" / "drift-baseline.json"
    baseline_path.mkdir(parents=True)

    with pytest.raises(DriftReportError, match="is not a file"):
        load_drift_baseline(baseline_path)


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
