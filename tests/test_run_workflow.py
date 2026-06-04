"""Unit tests for the deterministic run workflow use case."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from entroping.core.hurl_runner import HurlFileResult, HurlRunOptions, HurlSuiteResult
from entroping.core.run_workflow import (
    DependencyDriftObservationError,
    HurlVariablePreflightError,
    NoHurlTestsMatchedError,
    RunWorkflowError,
    execute_run_workflow,
)
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
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


def _passed_result(path: Path) -> HurlFileResult:
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
    ) -> HurlSuiteResult:
        captured_paths.extend(paths)
        captured_options.append(options)
        captured_workers.append(max_workers)
        for path in paths:
            assert "duration < 2000" in path.read_text(encoding="utf-8")
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
    latest = json.loads(result.latest_state_path.read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/health.hurl"


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
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        for path in paths:
            content = path.read_text(encoding="utf-8")
            assert "duration < 2000" not in content
            assert "status < 500" in content
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
                "csrf_token: header \"x-csrf-token\"",
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
    baseline_after_run = json.loads(
        (state_dir / "drift-baseline.json").read_text(encoding="utf-8")
    )
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
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(results=tuple(_passed_result(path) for path in paths))

    def fail_open_project(project_root: Path) -> TrafficStore:
        _ = project_root
        raise TrafficStoreError("traffic state unavailable")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)
    monkeypatch.setattr(TrafficStore, "open_project", fail_open_project)

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
