"""Unit tests for the deterministic run workflow use case."""

import json
from pathlib import Path

import pytest

from entroping.core.hurl_runner import HurlFileResult, HurlRunOptions, HurlSuiteResult
from entroping.core.run_workflow import NoHurlTestsMatchedError, execute_run_workflow


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
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
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
