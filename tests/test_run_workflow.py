"""Unit tests for the deterministic run workflow use case."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import pytest

from entroping.bridge.policy_to_hurl import HurlGateAssertion
from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import (
    HurlAssertionEvidence,
    HurlFileResult,
    HurlRunOptions,
    HurlSuiteResult,
)
from entroping.core.run_event_log import read_run_events
from entroping.core.run_workflow import (
    DependencyDriftObservationError,
    HurlVariablePreflightError,
    NoHurlTestsMatchedError,
    RunExecutionPlan,
    RunWorkflowError,
    _apply_gate_results,
    _display_path,
    _gate_results_for_result,
    _known_failure_source_key,
    execute_run_workflow,
    plan_run_workflow,
    run_execution_plan_to_dict,
    write_run_execution_plan,
)
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.qanstitution import Enforcement
from entroping.models.traffic import TrafficExchange, TrafficRequest, TrafficResponse


def _write_project(tmp_path: Path) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        "\n".join(
            [
                "project: entroping-project",
                "settings:",
                "  timeout: 2500",
                "  parallel_workers: 3",
                "gates:",
                "  - id: latency",
                '    condition: "true"',
                "    gate: duration < 2000",
                "    enforcement: block",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )


def _passed_result(
    path: Path,
    *,
    assertion_evidence: tuple[HurlAssertionEvidence, ...] | None = None,
) -> HurlFileResult:
    if assertion_evidence is None:
        assertion_evidence = _gate_assertion_evidence(path, success=True)
    return HurlFileResult(
        path=path,
        command=("hurl", str(path)),
        status="passed",
        exit_code=0,
        stdout="ok\n",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_ms=12,
        assertion_evidence=assertion_evidence,
    )


def _failed_result(path: Path) -> HurlFileResult:
    return HurlFileResult(
        path=path,
        command=("hurl", str(path)),
        status="failed",
        exit_code=3,
        stdout="",
        stderr="assertion failed\n",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_ms=12,
        assertion_evidence=_gate_assertion_evidence(path, success=False),
    )


def _gate_assertion_evidence(
    path: Path,
    *,
    success: bool,
) -> tuple[HurlAssertionEvidence, ...]:
    return tuple(
        HurlAssertionEvidence(line=index + 2, success=success)
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines())
        if line.startswith("# entroping-gate:")
    )


def _workflow_gate(
    *,
    rule_id: str = "gate",
    enforcement: Enforcement = "block",
) -> HurlGateAssertion:
    return HurlGateAssertion(
        rule_id=rule_id,
        assertion="status == 200",
        enforcement=enforcement,
        condition="true",
    )


def _workflow_execution_copy(
    source: Path,
    execution: Path,
    *,
    gates: tuple[HurlGateAssertion, ...],
    gate_lines: tuple[tuple[int, HurlGateAssertion], ...] = (),
) -> HurlExecutionCopy:
    return HurlExecutionCopy(
        source_path=source,
        execution_path=execution,
        injected_gates=gates,
        injected_gate_lines=gate_lines,
    )


def _write_enforcement_project(project_root: Path, *, block_gate: str) -> Path:
    policy_path = project_root / "qanstitution.yaml"
    policy_path.write_text(
        "\n".join(
            [
                "project: enforcement-project",
                "settings:",
                "  timeout: 2500",
                "  parallel_workers: 1",
                "gates:",
                "  - id: block_gate",
                '    condition: "true"',
                f"    gate: {block_gate}",
                "    enforcement: block",
                "  - id: warn_gate",
                '    condition: "true"',
                '    gate: header "X-Missing-Warn" exists',
                "    enforcement: warn",
                "  - id: audit_gate",
                '    condition: "true"',
                '    gate: header "X-Missing-Audit" exists',
                "    enforcement: audit_only",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = project_root / "tests"
    tests_dir.mkdir(exist_ok=True)
    source_path = tests_dir / "health.hurl"
    source_path.write_text(
        "GET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    return source_path


def _assert_gate_report_fields(
    report_path: Path,
    expected: dict[str, tuple[str, str, int]],
) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(report, dict)
    tests = report["tests"]
    assert isinstance(tests, list)
    test = tests[0]
    assert isinstance(test, dict)
    gate_results = test["gate_results"]
    assert isinstance(gate_results, list)
    assert {
        item["rule_id"]: (item["enforcement"], item["result"], item["exit_code"])
        for item in gate_results
    } == expected


def test_execute_run_workflow_reports_nonblocking_gate_failures_without_failing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = _write_enforcement_project(tmp_path, block_gate="status < 500")
    source_before = source_path.read_bytes()

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        del options, max_workers, fail_fast
        results = []
        for path in paths:
            evidence = tuple(
                HurlAssertionEvidence(
                    line=index + 2,
                    success=line.split()[2] == "block_gate",
                )
                for index, line in enumerate(path.read_text(encoding="utf-8").splitlines())
                if line.startswith("# entroping-gate:")
            )
            results.append(_passed_result(path, assertion_evidence=evidence))
        return HurlSuiteResult(results=tuple(results))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        report_formats=("json", "junit", "html"),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 0
    latest = json.loads((tmp_path / ".entroping" / "latest-run.json").read_text(encoding="utf-8"))
    assert latest["summary"]["exit_code"] == 0
    assert latest["summary"]["failed"] == 0
    expected = {
        "block_gate": ("block", "passed", 0),
        "warn_gate": ("warn", "failed", 1),
        "audit_gate": ("audit_only", "failed", 1),
    }
    _assert_gate_report_fields(tmp_path / "reports" / "run-latest.json", expected)
    junit = ElementTree.parse(tmp_path / "reports" / "junit.xml")
    junit_properties = junit.getroot().find("testcase/properties")
    assert junit_properties is not None
    properties = {
        property.attrib["name"]: property.attrib["value"]
        for property in junit_properties
    }
    assert properties["entroping.gate.warn_gate.enforcement"] == "warn"
    assert properties["entroping.gate.warn_gate.result"] == "failed"
    assert properties["entroping.gate.audit_gate.enforcement"] == "audit_only"
    html = (tmp_path / "reports" / "run-latest.html").read_text(encoding="utf-8")
    assert "warn_gate" in html and "audit_gate" in html and "audit_only" in html
    assert source_path.read_bytes() == source_before
    assert not list((tmp_path / ".entroping").glob("run-*"))


def test_execute_run_workflow_block_gate_failure_fails_run_and_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_enforcement_project(tmp_path, block_gate='header "X-Missing-Block" exists')

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        del options, max_workers, fail_fast
        return HurlSuiteResult(results=tuple(_failed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 1
    _assert_gate_report_fields(
        tmp_path / "reports" / "run-latest.json",
        {
            "block_gate": ("block", "failed", 3),
            "warn_gate": ("warn", "failed", 3),
            "audit_gate": ("audit_only", "failed", 3),
        },
    )


def test_gate_results_reject_missing_and_duplicate_assertion_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.hurl"
    execution = tmp_path / "execution.hurl"
    gate = _workflow_gate()
    copy_without_lines = _workflow_execution_copy(
        source,
        execution,
        gates=(gate,),
    )
    execution.write_text("", encoding="utf-8")
    invalid_results, invalid = _gate_results_for_result(
        copy_without_lines,
        _passed_result(execution, assertion_evidence=()),
    )

    assert invalid is True
    assert invalid_results[0].result == "error"

    missing_results, missing = _gate_results_for_result(
        copy_without_lines,
        replace(_passed_result(execution), assertion_evidence=None),
    )

    assert missing is True
    assert missing_results[0].result == "error"

    copy_with_line = _workflow_execution_copy(
        source,
        execution,
        gates=(gate,),
        gate_lines=((2, gate),),
    )
    duplicate_results, duplicate = _gate_results_for_result(
        copy_with_line,
        _passed_result(
            execution,
            assertion_evidence=(
                HurlAssertionEvidence(line=2, success=True),
                HurlAssertionEvidence(line=2, success=True),
            ),
        ),
    )

    assert duplicate is True
    assert duplicate_results[0].result == "error"


def test_apply_gate_results_rejects_path_mismatch_and_block_evidence_drift(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.hurl"
    execution = tmp_path / "execution.hurl"
    gate = _workflow_gate()
    copy_with_missing_lines = _workflow_execution_copy(
        source,
        execution,
        gates=(gate,),
    )

    with pytest.raises(RunWorkflowError, match="does not match"):
        _apply_gate_results(
            HurlSuiteResult(
                results=(_passed_result(tmp_path / "other.hurl", assertion_evidence=()),),
            ),
            execution_copies=(copy_with_missing_lines,),
        )

    updated_suite, results_by_source = _apply_gate_results(
        HurlSuiteResult(results=(_passed_result(execution, assertion_evidence=()),)),
        execution_copies=(copy_with_missing_lines,),
    )

    assert updated_suite.results[0].status == "error"
    assert updated_suite.results[0].exit_code == 126
    assert results_by_source[source.resolve()][0].result == "error"

    copy_with_failed_block = _workflow_execution_copy(
        source,
        execution,
        gates=(gate,),
        gate_lines=((2, gate),),
    )
    failed_suite, _failed_results = _apply_gate_results(
        HurlSuiteResult(
            results=(
                _passed_result(
                    execution,
                    assertion_evidence=(HurlAssertionEvidence(line=2, success=False),),
                ),
            ),
        ),
        execution_copies=(copy_with_failed_block,),
    )

    assert failed_suite.results[0].status == "failed"
    assert failed_suite.results[0].exit_code == 1

    no_gate_copy = _workflow_execution_copy(source, execution, gates=())
    unchanged_suite, no_gate_results = _apply_gate_results(
        HurlSuiteResult(results=(_passed_result(execution, assertion_evidence=()),)),
        execution_copies=(no_gate_copy,),
    )

    assert unchanged_suite.results[0].status == "passed"
    assert no_gate_results == {}


def test_known_failure_source_key_keeps_external_absolute_path(tmp_path: Path) -> None:
    external_path = tmp_path.parent / "external.hurl"

    assert _known_failure_source_key(external_path, project_root=tmp_path) == (
        external_path.resolve().as_posix()
    )


def _write_matching_drift_baseline(project_root: Path) -> None:
    state_dir = project_root / ".entroping"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "drift-baseline.json").write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "rule_ids": ["latency"],
                    }
                ],
            },
        ),
        encoding="utf-8",
    )


def _write_dependency_baseline(project_root: Path) -> None:
    state_dir = project_root / ".entroping"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "dependency-baseline.json").write_text(
        json.dumps(
            {
                "source_label": "client",
                "routes": [
                    {
                        "destination_host": "payments.example.test",
                        "method": "POST",
                        "path_template": "/charges/{id}",
                    }
                ],
            },
        ),
        encoding="utf-8",
    )


def test_execute_run_workflow_writes_reports_and_cleans_execution_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    (env_dir / "local.env").write_text("base_url=http://localhost:18080\n", encoding="utf-8")
    captured_paths: list[Path] = []
    captured_options: list[HurlRunOptions] = []
    captured_workers: list[int] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        captured_paths.extend(paths)
        captured_options.append(options)
        captured_workers.append(max_workers)
        contents = [path.read_text(encoding="utf-8") for path in paths]
        assert all("duration < 2000" in content for content in contents)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="local",
        tag_filters=("smoke",),
        report_formats=("json", "junit", "html"),
        parallel=True,
        drift_check=False,
    )

    assert result.exit_code == 0
    assert result.latest_state_path == (tmp_path / ".entroping" / "latest-run.json").resolve()
    assert {path.relative_to(tmp_path) for path in result.artifacts} == {
        Path("reports/run-latest.json"),
        Path("reports/junit.xml"),
        Path("reports/run-latest.html"),
    }
    assert captured_paths and not captured_paths[0].exists()
    assert captured_options[0].timeout_ms == 2500
    assert captured_options[0].variables == {"base_url": "http://localhost:18080"}
    assert captured_workers == [3]
    assert not (tmp_path / ".entroping" / "latest-run-events.lock").exists()
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/health.hurl"


def test_execute_run_workflow_loads_auth_variables_without_reporting_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    (env_dir / "local.env").write_text(
        "base_url=http://localhost:18080\naccess_token=live-auth-secret\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke,auth",
                "# entroping: auth_flow=oauth2-client-credentials",
                "# entroping: auth_requires=access_token",
                "",
                "GET {{base_url}}/profile",
                "Authorization: Bearer {{access_token}}",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )
    captured_options: list[HurlRunOptions] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (max_workers, fail_fast)
        captured_options.append(options)
        return HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=paths[0],
                    command=("hurl", str(paths[0])),
                    status="failed",
                    exit_code=1,
                    stdout="Authorization: Bearer live-auth-secret\n",
                    stderr="token=live-auth-secret\n",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=12,
                    timeout_ms=options.timeout_ms,
                    assertion_evidence=_gate_assertion_evidence(paths[0], success=False),
                ),
            ),
        )

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="local",
        tag_filters=("auth",),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
    )

    assert captured_options[0].variables == {
        "access_token": "live-auth-secret",
        "base_url": "http://localhost:18080",
    }
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["auth"] == {
        "flow": "oauth2-client-credentials",
        "requires": ["access_token"],
        "produces": [],
    }
    serialized = json.dumps(latest)
    assert "live-auth-secret" not in serialized
    assert "Authorization: [REDACTED]" in serialized
    assert "token=[REDACTED]" in serialized


def test_execute_run_workflow_applies_known_failure_gate_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        "\n".join(
            [
                "project: entroping-project",
                "gates:",
                "  - id: latency",
                '    condition: "true"',
                "    gate: duration < 2000",
                "    enforcement: block",
                "  - id: status_ceiling",
                '    condition: "true"',
                "    gate: status < 500",
                "    enforcement: block",
                "ignore_failures:",
                "  - test: tests/health.hurl",
                "    rule_id: latency",
                "    issue_id: GH-123",
                "    expires: '2999-01-01'",
                "    reason: Temporary upstream latency regression.",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        contents = [path.read_text(encoding="utf-8") for path in paths]
        assert all("duration < 2000" not in content for content in contents)
        assert all("status < 500" in content for content in contents)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=(),
        parallel=False,
        drift_check=False,
    )

    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["rule_ids"] == ["status_ceiling"]
    assert latest["tests"][0]["known_failures"] == [
        {
            "expires": "2999-01-01",
            "issue_id": "GH-123",
            "reason": "Temporary upstream latency regression.",
            "rule_id": "latency",
            "test": "tests/health.hurl",
        }
    ]


def test_execute_run_workflow_selects_by_operation_id_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    tests_dir = tmp_path / "tests"
    (tests_dir / "health.hurl").write_text(
        "# entroping: operation_id=getHealth\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tests_dir / "checkout.hurl").write_text(
        "# entroping: operation_id=createCheckout\n\n"
        "POST http://localhost:18080/checkout\nHTTP 201\n",
        encoding="utf-8",
    )
    captured_paths: list[Path] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        captured_paths.extend(paths)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        operation_ids=("createCheckout",),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
    )

    assert result.selection.selected_count == 1
    assert result.selection.skipped_count == 1
    assert captured_paths and captured_paths[0].name.startswith("checkout-")
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/checkout.hurl"
    assert latest["tests"][0]["operation_id"] == "createCheckout"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_execute_run_workflow_blocks_unsafe_mutating_tests_in_protected_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "production.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        f"# entroping: tags=smoke\n\n{method} http://localhost:18080/orders\nHTTP 200\n",
        encoding="utf-8",
    )
    subprocess_called = False

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        nonlocal subprocess_called
        _ = (paths, options, max_workers, fail_fast)
        subprocess_called = True
        raise AssertionError("Hurl should not run when protected safety preflight blocks")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="production",
        tag_filters=("smoke",),
        report_formats=("json", "junit", "html"),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 1
    assert subprocess_called is False
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["summary"] == {
        "total": 1,
        "passed": 0,
        "failed": 1,
        "exit_code": 1,
    }
    assert latest["tests"][0]["status"] == "blocked"
    assert latest["tests"][0]["safety"] == {
        "protected_environment": True,
        "safety": None,
        "safety_source": None,
        "methods": [method],
        "blocked_reason": (
            f"mutating method {method} requires safety metadata in protected environments"
        ),
    }
    assert "localhost:18080" not in json.dumps(latest)
    assert (tmp_path / "reports" / "run-latest.json").is_file()
    assert (tmp_path / "reports" / "junit.xml").is_file()
    assert (tmp_path / "reports" / "run-latest.html").is_file()


def test_execute_run_workflow_counts_unrun_selected_tests_when_protected_block_stops_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "production.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "checkout.hurl").write_text(
        "# entroping: tags=smoke\n\nPOST http://localhost:18080/orders\nHTTP 201\n",
        encoding="utf-8",
    )
    subprocess_called = False

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        nonlocal subprocess_called
        _ = (paths, options, max_workers, fail_fast)
        subprocess_called = True
        raise AssertionError("Hurl should not run when protected safety preflight blocks")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="production",
        tag_filters=("smoke",),
        report_formats=("json", "junit", "html"),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 1
    assert subprocess_called is False
    assert result.selection.selected_count == 2
    assert result.suite.total == 1
    assert result.suite.not_scheduled == 1
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["summary"] == {
        "total": 1,
        "passed": 0,
        "failed": 1,
        "exit_code": 1,
        "selected": 2,
        "executed": 1,
        "not_scheduled": 1,
        "fail_fast": False,
    }
    assert [test["path"] for test in latest["tests"]] == ["tests/checkout.hurl"]
    assert latest["tests"][0]["status"] == "blocked"
    assert "localhost:18080" not in json.dumps(latest)
    assert (tmp_path / "reports" / "run-latest.json").is_file()
    assert (tmp_path / "reports" / "junit.xml").is_file()
    assert (tmp_path / "reports" / "run-latest.html").is_file()


def test_execute_run_workflow_blocks_read_only_metadata_on_mutating_protected_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "production.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        "# entroping: tags=smoke\n"
        "# entroping: safety=read-only\n\n"
        "DELETE http://localhost:18080/orders/123\nHTTP 204\n",
        encoding="utf-8",
    )
    subprocess_called = False

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        nonlocal subprocess_called
        _ = (paths, options, max_workers, fail_fast)
        subprocess_called = True
        raise AssertionError("read-only contradiction must block before Hurl")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="production",
        tag_filters=("smoke",),
        report_formats=("json", "junit", "html"),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 1
    assert subprocess_called is False
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["status"] == "blocked"
    assert latest["tests"][0]["safety"] == {
        "protected_environment": True,
        "safety": "read-only",
        "safety_source": "test metadata",
        "methods": ["DELETE"],
        "blocked_reason": (
            "read-only safety metadata conflicts with mutating method DELETE "
            "in protected environments"
        ),
    }
    assert "localhost:18080" not in json.dumps(latest)
    assert (tmp_path / "reports" / "run-latest.json").is_file()
    assert (tmp_path / "reports" / "junit.xml").is_file()
    assert (tmp_path / "reports" / "run-latest.html").is_file()


def test_execute_run_workflow_allows_idempotent_mutation_in_protected_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "prod.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        "# entroping: tags=smoke\n"
        "# entroping: safety=idempotent\n\n"
        "POST http://localhost:18080/reindex\nHTTP 202\n",
        encoding="utf-8",
    )
    executed_paths: list[Path] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers, fail_fast)
        executed_paths.extend(paths)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="prod",
        tag_filters=("smoke",),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 0
    assert len(executed_paths) == 1
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["status"] == "passed"
    assert latest["tests"][0]["safety"] == {
        "protected_environment": True,
        "safety": "idempotent",
        "safety_source": "test metadata",
        "methods": ["POST"],
        "blocked_reason": None,
    }


def test_execute_run_workflow_blocks_destructive_test_metadata_over_suite_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "staging.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        "# entroping: tags=smoke\n"
        "# entroping: safety=destructive\n\n"
        "DELETE http://localhost:18080/accounts/123\nHTTP 204\n",
        encoding="utf-8",
    )
    subprocess_called = False

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        nonlocal subprocess_called
        _ = (paths, options, max_workers, fail_fast)
        subprocess_called = True
        raise AssertionError("destructive metadata must block before Hurl")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="staging",
        tag_filters=("smoke",),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
        protected_run=True,
        suite_safety="idempotent",
    )

    assert result.exit_code == 1
    assert subprocess_called is False
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["status"] == "blocked"
    assert latest["tests"][0]["safety"] == {
        "protected_environment": True,
        "safety": "destructive",
        "safety_source": "test metadata",
        "methods": ["DELETE"],
        "blocked_reason": "destructive tests are blocked in protected environments",
    }


def test_plan_run_workflow_reports_protected_safety_blockers(tmp_path: Path) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "protected.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nPATCH http://localhost:18080/profile\nHTTP 200\n",
        encoding="utf-8",
    )

    plan = plan_run_workflow(
        project_root=tmp_path,
        environment="protected",
        tag_filters=("smoke",),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
    )

    assert plan.status == "blocked"
    assert plan.message == "Run plan blocked by protected-environment safety preflight"
    assert plan.tests[0].safety is not None
    assert plan.tests[0].safety.methods == ("PATCH",)
    assert plan.tests[0].safety.blocked_reason == (
        "mutating method PATCH requires safety metadata in protected environments"
    )
    payload = json.dumps(run_execution_plan_to_dict(plan))
    assert "localhost:18080" not in payload


def test_plan_run_workflow_reports_auth_chain_names_and_missing_secret_variables(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "envs").mkdir()
    (tmp_path / "envs" / "local.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "health.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=auth",
                "# entroping: auth_flow=oauth2-client-credentials",
                "# entroping: auth_requires=access_token,csrf_token",
                "# entroping: auth_produces=session_cookie",
                "",
                "GET {{base_url}}/profile",
                "Authorization: Bearer {{access_token}}",
                "X-CSRF-Token: {{csrf_token}}",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    plan = plan_run_workflow(
        project_root=tmp_path,
        environment="local",
        tag_filters=("auth",),
        report_formats=("json",),
        parallel=False,
        drift_check=False,
    )

    assert plan.status == "blocked"
    assert plan.message == "Run plan blocked by unresolved Hurl variables"
    assert plan.tests[0].auth is not None
    assert plan.tests[0].auth.flow == "oauth2-client-credentials"
    assert plan.tests[0].auth.requires == ("access_token", "csrf_token")
    assert plan.tests[0].auth.produces == ("session_cookie",)
    assert [(item.name, item.paths) for item in plan.missing_variables] == [
        ("access_token", ("tests/health.hurl",)),
        ("csrf_token", ("tests/health.hurl",)),
    ]
    payload = run_execution_plan_to_dict(plan)
    tests_payload = cast(list[dict[str, object]], payload["tests"])
    assert tests_payload[0]["auth"] == {
        "flow": "oauth2-client-credentials",
        "requires": ["access_token", "csrf_token"],
        "produces": ["session_cookie"],
    }
    serialized = json.dumps(payload)
    assert "localhost:18080" not in serialized
    assert "live-auth-secret" not in serialized


def test_execute_run_workflow_reports_no_matching_operation_ids(tmp_path: Path) -> None:
    _write_project(tmp_path)

    with pytest.raises(NoHurlTestsMatchedError, match="OpenAPI operation IDs 'createCheckout'"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            operation_ids=("createCheckout",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


def test_execute_run_workflow_rejects_operation_id_and_tag_filter_mix(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(
        RunWorkflowError,
        match="operation ID filters cannot be combined with tag filters",
    ):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=("smoke",),
            operation_ids=("createCheckout",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


def test_execute_run_workflow_rejects_operation_id_and_tag_expression_mix(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(
        RunWorkflowError,
        match="operation ID filters cannot be combined with tag expressions",
    ):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            tag_expression="smoke",
            operation_ids=("createCheckout",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


def test_execute_run_workflow_rejects_changed_from_with_operation_ids(tmp_path: Path) -> None:
    _write_project(tmp_path)

    with pytest.raises(
        RunWorkflowError,
        match="changed-from cannot be combined with operation ID filters",
    ):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            operation_ids=("createCheckout",),
            report_formats=(),
            parallel=False,
            drift_check=False,
            changed_from="origin/main",
        )


def test_execute_run_workflow_rejects_unmatched_known_failure_for_selected_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        "\n".join(
            [
                "project: entroping-project",
                "gates:",
                "  - id: latency",
                '    condition: "true"',
                "    gate: duration < 2000",
                "    enforcement: block",
                "ignore_failures:",
                "  - test: tests/health.hurl",
                "    rule_id: missing_latency",
                "    issue_id: GH-404",
                "    expires: '2999-01-01'",
                "    reason: Stale rule id should fail closed.",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    hurl_called = False

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        nonlocal hurl_called
        _ = (paths, options, max_workers)
        hurl_called = True
        raise AssertionError("Hurl should not run with unmatched known failure")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    with pytest.raises(
        RunWorkflowError,
        match="Known failure exception did not match.*GH-404.*tests/health\\.hurl.*missing_latency",
    ):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=("smoke",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )

    assert hurl_called is False
    assert not (tmp_path / ".entroping" / "latest-run.json").exists()


def test_execute_run_workflow_ignores_known_failure_for_filtered_out_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        "\n".join(
            [
                "project: entroping-project",
                "gates:",
                "  - id: latency",
                '    condition: "true"',
                "    gate: duration < 2000",
                "    enforcement: block",
                "ignore_failures:",
                "  - test: tests/slow.hurl",
                "    rule_id: latency",
                "    issue_id: GH-405",
                "    expires: '2999-01-01'",
                "    reason: Slow test is outside this filtered run.",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tests_dir / "slow.hurl").write_text(
        "# entroping: tags=slow\n\nGET http://localhost:18080/slow\nHTTP 200\n",
        encoding="utf-8",
    )

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=(),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 0
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/health.hurl"
    assert "known_failures" not in latest["tests"][0]


def test_execute_run_workflow_reports_no_matching_hurl_tests(tmp_path: Path) -> None:
    _write_project(tmp_path)

    with pytest.raises(NoHurlTestsMatchedError):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=("missing",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


def test_execute_run_workflow_selects_by_tag_expression_with_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    tests_dir = tmp_path / "tests"
    (tests_dir / "slow.hurl").write_text(
        "# entroping: tags=smoke,slow\n\nGET http://localhost:18080/slow\nHTTP 200\n",
        encoding="utf-8",
    )
    (tests_dir / "billing.hurl").write_text(
        "# entroping: tags=regression,billing\n\nGET http://localhost:18080/billing\nHTTP 200\n",
        encoding="utf-8",
    )
    captured_paths: list[Path] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        captured_paths.extend(paths)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        tag_expression="smoke and not slow",
        report_formats=(),
        parallel=False,
        drift_check=False,
    )

    assert result.selection.discovered_count == 3
    assert result.selection.selected_count == 1
    assert result.selection.skipped_count == 2
    assert len(captured_paths) == 1
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/health.hurl"


def test_execute_run_workflow_reports_no_matching_tag_expression_with_counts(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(NoHurlTestsMatchedError, match="0 selected, 1 skipped"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            tag_expression="critical and not slow",
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


def test_execute_run_workflow_rejects_tag_filter_and_expression_mix(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(RunWorkflowError, match="tag filters cannot be combined"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=("smoke",),
            tag_expression="checkout",
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


@pytest.mark.parametrize(
    ("tag_filters", "tag_expression", "operation_ids", "message"),
    [
        (
            ("smoke",),
            "checkout",
            (),
            "tag filters cannot be combined",
        ),
        (
            ("smoke",),
            None,
            ("health",),
            "operation ID filters cannot be combined with tag filters",
        ),
        (
            (),
            "smoke",
            ("health",),
            "operation ID filters cannot be combined with tag expressions",
        ),
    ],
)
def test_plan_run_workflow_rejects_selector_conflicts(
    tmp_path: Path,
    tag_filters: tuple[str, ...],
    tag_expression: str | None,
    operation_ids: tuple[str, ...],
    message: str,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(RunWorkflowError, match=message):
        plan_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=tag_filters,
            tag_expression=tag_expression,
            operation_ids=operation_ids,
            report_formats=(),
            parallel=False,
            drift_check=False,
        )


def test_plan_run_workflow_reports_all_requested_artifact_paths(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    plan = plan_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        report_formats=("junit", "html", "drift"),
        parallel=True,
        fail_fast=True,
        drift_check=True,
    )

    assert plan.status == "ready"
    assert plan.worker_count == 3
    assert plan.fail_fast is True
    assert plan.drift_check is True
    assert plan.would_write_reports == (
        "reports/junit.xml",
        "reports/run-latest.html",
        "reports/drift.json",
        "reports/drift-baseline.candidate.json",
    )


def test_plan_run_workflow_rejects_changed_from_custom_roots(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(
        RunWorkflowError,
        match="changed-from cannot be combined with custom Hurl discovery roots",
    ):
        plan_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            report_formats=(),
            parallel=False,
            drift_check=False,
            changed_from="origin/main",
            discovery_roots=(tmp_path / "tests",),
        )


def test_plan_run_workflow_rejects_changed_from_operation_filters(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(
        RunWorkflowError,
        match="changed-from cannot be combined with operation ID filters",
    ):
        plan_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            operation_ids=("health",),
            report_formats=(),
            parallel=False,
            drift_check=False,
            changed_from="origin/main",
        )


def test_plan_run_workflow_describes_changed_tag_expression_no_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)

    def fake_select_changed_hurl_tests(
        *,
        project_root: Path,
        base_ref: str,
    ) -> tuple[Path, ...]:
        assert project_root == tmp_path.resolve()
        assert base_ref == "origin/main"
        return ()

    monkeypatch.setattr(
        "entroping.core.run_workflow.select_changed_hurl_tests",
        fake_select_changed_hurl_tests,
    )

    plan = plan_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        tag_expression="smoke and not slow",
        report_formats=(),
        parallel=False,
        drift_check=False,
        changed_from="origin/main",
    )

    assert plan.status == "no_match"
    assert (
        "changed Hurl tests matching tag expression 'smoke and not slow' "
        "from base ref 'origin/main'"
    ) in plan.message


def test_write_run_execution_plan_rejects_paths_outside_project(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    plan = RunExecutionPlan(
        status="ready",
        message="Run plan ready; Hurl was not executed",
        project="entroping-project",
        environment="default",
        tag_filters=(),
        tag_expression=None,
        operation_ids=(),
        changed_from=None,
        selection_label=None,
        report_formats=(),
        would_write_reports=(),
        parallel=False,
        fail_fast=False,
        drift_check=False,
        worker_count=1,
        timeout_ms=2500,
        retry=0,
        discovered_count=0,
        selected_count=0,
        skipped_count=0,
        effective_rule_ids=(),
        injected_rule_ids=(),
        provided_variable_count=0,
        missing_variables=(),
        tests=(),
    )

    with pytest.raises(RunWorkflowError, match="must stay under"):
        write_run_execution_plan(
            plan,
            tmp_path.parent / "run-plan.json",
            project_root=tmp_path,
        )


def test_display_path_keeps_external_absolute_path(tmp_path: Path) -> None:
    external_path = tmp_path.parent / "external.hurl"

    assert _display_path(external_path, tmp_path) == external_path.resolve().as_posix()


def test_execute_run_workflow_uses_custom_discovery_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    (tmp_path / "tests" / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    selected = tmp_path / "tests" / "regression.hurl"
    selected.write_text(
        "# entroping: tags=regression\n\nGET http://localhost:18080/regression\nHTTP 200\n",
        encoding="utf-8",
    )
    captured_paths: list[Path] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        captured_paths.extend(paths)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("regression",),
        report_formats=(),
        parallel=False,
        drift_check=False,
        discovery_roots=(selected,),
        selection_label="suite 'regression'",
    )

    assert result.exit_code == 0
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/regression.hurl"
    assert len(captured_paths) == 1


def test_execute_run_workflow_reports_empty_custom_selection(tmp_path: Path) -> None:
    _write_project(tmp_path)

    with pytest.raises(NoHurlTestsMatchedError, match="suite 'empty'"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            report_formats=(),
            parallel=False,
            drift_check=False,
            discovery_roots=(),
            selection_label="suite 'empty'",
        )


def test_execute_run_workflow_rejects_changed_ref_with_custom_discovery_roots(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(RunWorkflowError, match="changed-from"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            report_formats=(),
            parallel=False,
            drift_check=False,
            changed_from="main",
            discovery_roots=(tmp_path / "tests" / "health.hurl",),
        )


def test_execute_run_workflow_runs_only_changed_hurl_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    changed = tmp_path / "tests" / "checkout.hurl"
    changed.write_text(
        "# entroping: tags=changed\n\nGET http://localhost:18080/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    captured_paths: list[Path] = []

    def fake_select_changed_hurl_tests(*, project_root: Path, base_ref: str) -> tuple[Path, ...]:
        assert project_root == tmp_path.resolve()
        assert base_ref == "main"
        return (changed.resolve(),)

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        captured_paths.extend(paths)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr(
        "entroping.core.run_workflow.select_changed_hurl_tests",
        fake_select_changed_hurl_tests,
    )
    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=(),
        report_formats=(),
        parallel=False,
        drift_check=False,
        changed_from="main",
    )

    assert result.exit_code == 0
    assert captured_paths
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert [test["path"] for test in latest["tests"]] == ["tests/checkout.hurl"]


def test_execute_run_workflow_reports_empty_changed_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    monkeypatch.setattr(
        "entroping.core.run_workflow.select_changed_hurl_tests",
        lambda *, project_root, base_ref: (),
    )

    with pytest.raises(NoHurlTestsMatchedError, match="No changed Hurl tests matched"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            report_formats=(),
            parallel=False,
            drift_check=False,
            changed_from="main",
        )


def test_execute_run_workflow_reports_empty_changed_tag_expression_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    monkeypatch.setattr(
        "entroping.core.run_workflow.select_changed_hurl_tests",
        lambda *, project_root, base_ref: (),
    )

    with pytest.raises(NoHurlTestsMatchedError, match="matching tag expression 'smoke'"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            tag_expression="smoke",
            report_formats=(),
            parallel=False,
            drift_check=False,
            changed_from="main",
        )


def test_execute_run_workflow_preflights_missing_hurl_variables_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    (env_dir / "local.env").write_text("base_url=http://localhost:18080\n", encoding="utf-8")
    (tmp_path / "tests" / "health.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke",
                "",
                "GET {{base_url}}/health/{{api_token}}/{{api_token}}",
                "HTTP 200",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess_called = False

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        nonlocal subprocess_called
        _ = (paths, options, max_workers)
        subprocess_called = True
        raise AssertionError("Hurl should not run when variables are missing")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    with pytest.raises(HurlVariablePreflightError) as excinfo:
        execute_run_workflow(
            project_root=tmp_path,
            environment="local",
            tag_filters=("smoke",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )

    message = str(excinfo.value)
    assert subprocess_called is False
    assert "Unresolved Hurl variables before execution" in message
    assert "api_token" in message
    assert "base_url" not in message
    assert "http://localhost:18080" not in message


def test_execute_run_workflow_records_events_for_environment_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    (env_dir / "local.env").write_text("base_url=http://localhost:18080\n", encoding="utf-8")

    def fail_load_environment_variables(environment_name: str, *, root: Path) -> dict[str, str]:
        _ = (environment_name, root)
        raise ValueError("failed to load local environment")

    monkeypatch.setattr(
        "entroping.core.run_workflow.load_environment_variables",
        fail_load_environment_variables,
    )

    with pytest.raises(ValueError, match="failed to load local environment"):
        execute_run_workflow(
            project_root=tmp_path,
            environment="local",
            tag_filters=("smoke",),
            report_formats=(),
            parallel=False,
            drift_check=False,
        )

    events = read_run_events(tmp_path / ".entroping" / "latest-run-events.jsonl")
    assert [event["event"] for event in events] == [
        "run_started",
        "run_error",
        "run_completed",
    ]
    assert events[0]["environment"] == "local"
    assert events[1]["error_type"] == "ValueError"
    assert "failed to load local environment" in cast(str, events[1]["message"])
    assert events[2]["status"] == "error"
    assert events[2]["exit_code"] == 1


def test_execute_run_workflow_invalid_tag_expression_does_not_start_event_log(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    with pytest.raises(ValueError, match="Expected tag or"):
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=(),
            tag_expression="smoke and or slow",
            report_formats=(),
            parallel=False,
            drift_check=False,
        )

    assert not (tmp_path / ".entroping" / "latest-run-events.jsonl").exists()


def test_execute_run_workflow_accepts_env_file_shell_env_and_local_hurl_definitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    (env_dir / "local.env").write_text("base_url=http://localhost:18080\n", encoding="utf-8")
    monkeypatch.setenv("HURL_VARIABLE_api_token", "secret-token")
    (tmp_path / "tests" / "health.hurl").write_text(
        "\n".join(
            [
                "# entroping: note={{ignored_metadata_variable}}",
                "# comment {{ignored_comment_variable}}",
                "# entroping: tags=smoke",
                "",
                "GET {{base_url}}/health/{{checkout_id}}",
                "[Options]",
                "variable: checkout_id=demo-checkout",
                "HTTP 200",
                "[Captures]",
                'csrf_token: header "x-csrf-token"',
                "",
                "POST {{base_url}}/checkout",
                "Authorization: Bearer {{api_token}}",
                "X-CSRF-Token: {{csrf_token}}",
                "{",
                '  "request_id": "{{newUuid}}",',
                '  "requested_at": "{{newDate}}"',
                "}",
                "HTTP 201",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    captured_options: list[HurlRunOptions] = []

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = max_workers
        captured_options.append(options)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment="local",
        tag_filters=("smoke",),
        report_formats=(),
        parallel=False,
        drift_check=False,
    )

    assert result.exit_code == 0
    assert captured_options[0].variables == {
        "api_token": "secret-token",
        "base_url": "http://localhost:18080",
    }


def test_execute_run_workflow_drift_findings_affect_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    (state_dir / "drift-baseline.json").write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "rule_ids": ["old_rule"],
                    }
                ],
            },
        ),
        encoding="utf-8",
    )

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=("drift",),
        parallel=False,
        drift_check=True,
    )

    assert result.drift_report is not None
    assert result.drift_report.summary.drifted == 1
    assert result.exit_code == 1
    assert (tmp_path / "reports" / "drift.json").exists()
    assert (tmp_path / "reports" / "drift-baseline.candidate.json").exists()
    baseline_after_run = json.loads((state_dir / "drift-baseline.json").read_text(encoding="utf-8"))
    assert baseline_after_run["tests"][0]["rule_ids"] == ["old_rule"]


def test_execute_run_workflow_missing_drift_baseline_affects_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=(),
        parallel=False,
        drift_check=True,
    )

    assert result.drift_report is not None
    assert result.drift_report.summary.missing_baseline is True
    assert result.exit_code == 1
    assert not (tmp_path / "reports" / "drift-baseline.candidate.json").exists()


def test_execute_run_workflow_writes_reviewed_drift_baseline_candidate_for_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=("drift",),
        parallel=False,
        drift_check=False,
    )

    candidate_path = tmp_path / "reports" / "drift-baseline.candidate.json"
    assert candidate_path in result.artifacts
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["tests"] == [
        {
            "duration_ms": 12,
            "exit_code": 0,
            "path": "tests/health.hurl",
            "rule_ids": ["latency"],
            "status": "passed",
        }
    ]
    assert not (tmp_path / ".entroping" / "drift-baseline.json").exists()


def test_execute_run_workflow_preserves_hurl_failure_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_failed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=(),
        parallel=False,
        drift_check=True,
    )

    assert result.suite.exit_code == 1
    assert result.exit_code == result.suite.exit_code


def test_execute_run_workflow_includes_dependency_call_drift_from_redacted_traffic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    _write_matching_drift_baseline(tmp_path)
    _write_dependency_baseline(tmp_path)
    TrafficStore.open_project(tmp_path).record_exchange(
        redact_traffic_exchange(
            TrafficExchange(
                captured_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
                duration_ms=33,
                request=TrafficRequest(
                    method="GET",
                    url="https://inventory.example.test/items/123?token=secret-token",
                    headers={"Authorization": "Bearer secret-token"},
                    body=None,
                ),
                response=TrafficResponse(status_code=200),
            )
        )
    )

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=("drift",),
        parallel=False,
        drift_check=True,
    )

    assert result.drift_report is not None
    assert [finding.kind for finding in result.drift_report.findings] == [
        "missing_dependency_route",
        "new_dependency_route",
    ]
    assert result.exit_code == 1
    drift_json = (tmp_path / "reports" / "drift.json").read_text(encoding="utf-8")
    assert "inventory.example.test" in drift_json
    assert "secret-token" not in drift_json


def test_execute_run_workflow_reads_dependency_observations_without_write_initializer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    _write_matching_drift_baseline(tmp_path)
    _write_dependency_baseline(tmp_path)
    TrafficStore.open_project(tmp_path).record_exchange(
        redact_traffic_exchange(
            TrafficExchange(
                captured_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
                duration_ms=33,
                request=TrafficRequest(
                    method="GET",
                    url="https://inventory.example.test/items/123?token=readonly-token",
                    headers={"Authorization": "Bearer readonly-token"},
                    body=None,
                ),
                response=TrafficResponse(status_code=200),
            )
        )
    )
    state_path = tmp_path / ".entroping" / "state.db"
    before = state_path.stat().st_mtime_ns

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    def fail_open_project(project_root: Path) -> TrafficStore:
        _ = project_root
        raise TrafficStoreError("write-capable traffic store opened")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)
    monkeypatch.setattr(TrafficStore, "open_project", fail_open_project)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=("drift",),
        parallel=False,
        drift_check=True,
    )
    after = state_path.stat().st_mtime_ns

    assert result.drift_report is not None
    assert [finding.kind for finding in result.drift_report.findings] == [
        "missing_dependency_route",
        "new_dependency_route",
    ]
    assert after == before


def test_execute_run_workflow_dependency_baseline_without_traffic_state_reports_missing_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    _write_matching_drift_baseline(tmp_path)
    _write_dependency_baseline(tmp_path)

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=("drift",),
        parallel=False,
        drift_check=True,
    )

    assert result.drift_report is not None
    assert [finding.kind for finding in result.drift_report.findings] == [
        "missing_dependency_route"
    ]


def test_execute_run_workflow_dependency_baseline_with_empty_traffic_state_reports_missing_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    _write_matching_drift_baseline(tmp_path)
    _write_dependency_baseline(tmp_path)
    TrafficStore.open_project(tmp_path)

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = execute_run_workflow(
        project_root=tmp_path,
        environment=None,
        tag_filters=("smoke",),
        report_formats=("drift",),
        parallel=False,
        drift_check=True,
    )

    assert result.drift_report is not None
    assert [finding.kind for finding in result.drift_report.findings] == [
        "missing_dependency_route"
    ]


def test_execute_run_workflow_dependency_observation_errors_are_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_project(tmp_path)
    _write_matching_drift_baseline(tmp_path)
    _write_dependency_baseline(tmp_path)
    (tmp_path / ".entroping" / "state.db").write_text("not sqlite\n", encoding="utf-8")

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
        fail_fast: bool = False,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    def fail_readonly(project_root: Path) -> tuple[TrafficExchange, ...]:
        _ = project_root
        raise TrafficStoreError("traffic state unavailable")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)
    monkeypatch.setattr(
        "entroping.core.run_workflow.list_project_exchanges_readonly",
        fail_readonly,
    )

    with pytest.raises(
        DependencyDriftObservationError,
        match="Could not build dependency drift observations",
    ) as exc_info:
        execute_run_workflow(
            project_root=tmp_path,
            environment=None,
            tag_filters=("smoke",),
            report_formats=("drift",),
            parallel=False,
            drift_check=True,
        )

    assert isinstance(exc_info.value, RunWorkflowError)
