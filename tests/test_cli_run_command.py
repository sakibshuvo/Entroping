"""CLI adapter tests for run command behavior."""

import re

from cli_test_support import (
    ArchitectPromptPackage,
    BinaryIO,
    CliRunner,
    DependencyDriftObservationError,
    ElementTree,
    HurlFileResult,
    HurlRunOptions,
    HurlSuiteResult,
    LiteLLMCompletionResult,
    NoHurlTestsMatchedError,
    Path,
    RunWorkflowError,
    SimpleNamespace,
    app,
    execution_cli,
    json,
    pytest,
    subprocess,
)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _read_run_events() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in Path(".entroping/latest-run-events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]


def test_run_executes_discovered_hurl_with_injected_gates_and_cleans_temp_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    source = Path("tests") / "health.hurl"
    source.write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")
    executed_paths: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, shell)
        executed_path = Path(args[-1])
        executed_paths.append(executed_path)
        assert executed_path != source.resolve()
        assert ".entroping" in executed_path.parts
        assert "duration < 2000" in executed_path.read_text(encoding="utf-8")
        stdout.write(b"ok\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    def fail_provider(self: object, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
        _ = (self, package)
        raise AssertionError("entroping run must not call LiteLLM")

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fail_provider)

    result = runner.invoke(app, ["run", "--tag", "smoke"])

    assert result.exit_code == 0
    assert "Hurl run: 1 passed, 0 failed" in result.output
    assert executed_paths
    assert not executed_paths[0].exists()
    assert not list(Path(".entroping").glob("run-*"))
    assert "# entroping-gate:" not in source.read_text(encoding="utf-8")


def test_run_returns_non_zero_when_hurl_execution_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, timeout, check, shell)
        stderr.write(b"Authorization: Bearer live-secret\nassert failed\n")
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = runner.invoke(app, ["run", "--tag", "smoke"])

    assert result.exit_code == 1
    assert "Hurl run: 0 passed, 1 failed" in result.output
    assert "live-secret" not in result.output
    assert "Authorization: [REDACTED]" in result.output
    events = _read_run_events()
    assert [event["event"] for event in events] == [
        "run_started",
        "test_selected",
        "test_result",
        "artifact_written",
        "run_completed",
    ]
    failed_event = events[2]
    assert failed_event["path"] == "tests/health.hurl"
    assert failed_event["status"] == "failed"
    assert failed_event["exit_code"] == 1
    event_log_text = Path(".entroping/latest-run-events.jsonl").read_text(encoding="utf-8")
    assert "live-secret" not in event_log_text
    assert "Authorization: [REDACTED]" in event_log_text


def test_run_reports_missing_hurl_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    result = runner.invoke(app, ["run", "--tag", "smoke"])

    assert result.exit_code == 1
    assert "Hurl binary not found" in result.output


def test_run_writes_json_junit_reports_and_latest_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    source = Path("tests") / "health.hurl"
    source.write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    env_file = Path("envs") / "local.env"
    env_file.write_text(
        "base_url=http://localhost:18080\ncart_id=demo-cart-001\n",
        encoding="utf-8",
    )
    executed_args: list[list[str]] = []
    variables_files: list[Path] = []

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stderr, timeout, check, shell)
        executed_args.append(args)
        variables_file = Path(args[args.index("--variables-file") + 1])
        variables_files.append(variables_file)
        assert variables_file.read_text(encoding="utf-8") == (
            "base_url=http://localhost:18080\ncart_id=demo-cart-001\n"
        )
        stdout.write(b"Authorization: Bearer live-secret\nbase_url=http://localhost:18080\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = runner.invoke(
        app,
        [
            "run",
            "--env",
            "local",
            "--tag",
            "smoke",
            "--report",
            "json",
            "--report",
            "junit",
            "--report",
            "html",
        ],
    )

    assert result.exit_code == 0
    assert "reports/run-latest.json" in result.output
    assert "reports/junit.xml" in result.output
    assert "reports/run-latest.html" in result.output
    assert executed_args
    assert "--variables-file" in executed_args[0]
    assert "base_url=http://localhost:18080" not in " ".join(executed_args[0])
    assert variables_files and not variables_files[0].exists()
    report_json = json.loads(Path("reports/run-latest.json").read_text(encoding="utf-8"))
    latest_json = json.loads(Path(".entroping/latest-run.json").read_text(encoding="utf-8"))
    junit_root = ElementTree.parse(Path("reports/junit.xml")).getroot()
    assert report_json["environment"] == "local"
    assert report_json["tests"][0]["path"] == "tests/health.hurl"
    assert "live-secret" not in Path("reports/run-latest.json").read_text(encoding="utf-8")
    assert "http://localhost:18080" not in Path("reports/run-latest.json").read_text(
        encoding="utf-8"
    )
    assert "http://localhost:18080" not in Path("reports/run-latest.html").read_text(
        encoding="utf-8"
    )
    assert report_json == latest_json
    assert junit_root.attrib["tests"] == "1"
    assert junit_root.attrib["failures"] == "0"


def test_run_writes_sanitized_execution_event_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    source = Path("tests") / "health.hurl"
    source.write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stderr, timeout, check, env, shell)
        stdout.write(b"Authorization: Bearer live-secret\nbase_url=http://localhost:18080\n")
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = runner.invoke(app, ["run", "--tag", "smoke", "--report", "json"])

    assert result.exit_code == 0
    assert "Wrote execution events: .entroping/latest-run-events.jsonl" in result.output
    events = _read_run_events()
    assert [event["event"] for event in events] == [
        "run_started",
        "test_selected",
        "test_result",
        "artifact_written",
        "artifact_written",
        "run_completed",
    ]
    assert {event["schema_version"] for event in events} == {"entroping.run-events.v1"}
    selected_event = events[1]
    assert selected_event["path"] == "tests/health.hurl"
    assert selected_event["tags"] == ["smoke"]
    assert selected_event["rule_ids"] == [
        "no_server_errors",
        "global_latency",
        "request_id_header",
    ]
    result_event = events[2]
    assert result_event["path"] == "tests/health.hurl"
    assert result_event["status"] == "passed"
    assert isinstance(result_event["duration_ms"], int)
    assert result_event["duration_ms"] >= 0
    assert result_event["stdout_truncated"] is False
    assert result_event["stderr_truncated"] is False
    artifact_paths = [
        event["path"] for event in events if event["event"] == "artifact_written"
    ]
    assert artifact_paths == [".entroping/latest-run.json", "reports/run-latest.json"]
    completed_event = events[-1]
    assert completed_event["status"] == "passed"
    assert completed_event["exit_code"] == 0
    assert completed_event["total"] == 1
    event_log_text = Path(".entroping/latest-run-events.jsonl").read_text(encoding="utf-8")
    assert "live-secret" not in event_log_text
    assert "http://localhost:18080" not in event_log_text
    assert "base_url" not in event_log_text


def test_run_report_drift_writes_missing_baseline_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, shell)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = runner.invoke(app, ["run", "--tag", "smoke", "--report", "drift"])

    assert result.exit_code == 0
    assert "Drift baseline not found" in result.output
    assert "reports/drift.json" in result.output
    assert "reports/drift-baseline.candidate.json" in result.output
    drift = json.loads(Path("reports/drift.json").read_text(encoding="utf-8"))
    assert drift["summary"]["missing_baseline"] is True
    assert drift["findings"][0]["kind"] == "missing_baseline"
    candidate = json.loads(
        Path("reports/drift-baseline.candidate.json").read_text(encoding="utf-8")
    )
    assert len(candidate["tests"]) == 1
    candidate_test = candidate["tests"][0]
    assert candidate_test.pop("duration_ms") >= 0
    assert candidate_test == {
        "exit_code": 0,
        "path": "tests/health.hurl",
        "rule_ids": ["no_server_errors", "global_latency", "request_id_header"],
        "status": "passed",
    }
    assert not (Path(".entroping") / "drift-baseline.json").exists()


def test_run_drift_check_fails_when_current_run_differs_from_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")
    baseline = Path(".entroping") / "drift-baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "project": "entroping-project",
                "environment": "default",
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "rule_ids": ["old_rule"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (stdout, stderr, timeout, check, shell)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

    result = runner.invoke(app, ["run", "--tag", "smoke", "--drift-check", "--report", "drift"])

    assert result.exit_code == 1
    assert "Drift check: 1 finding" in result.output
    drift = json.loads(Path("reports/drift.json").read_text(encoding="utf-8"))
    assert drift["findings"][0]["kind"] == "assertions_changed"
    assert drift["findings"][0]["path"] == "tests/health.hurl"


def test_run_parallel_uses_qanstitution_worker_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    qanstitution = Path("qanstitution.yaml")
    qanstitution.write_text(
        qanstitution.read_text(encoding="utf-8").replace(
            "  retry: 0\n",
            "  retry: 2\n",
        ),
        encoding="utf-8",
    )
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (Path("tests") / "checkout.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")
    captured: dict[str, object] = {}

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
    ) -> HurlSuiteResult:
        captured["max_workers"] = max_workers
        captured["timeout_ms"] = options.timeout_ms
        captured["retry"] = options.retry
        return HurlSuiteResult(
            results=tuple(
                HurlFileResult(
                    path=path,
                    command=("hurl", str(path)),
                    status="passed",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=1,
                )
                for path in paths
            )
        )

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = runner.invoke(app, ["run", "--tag", "smoke", "--parallel"])

    assert result.exit_code == 0
    assert captured == {"max_workers": 2, "timeout_ms": 30_000, "retry": 2}
    assert "Hurl run: 2 passed, 0 failed" in result.output


def test_run_selects_by_tag_expression_and_prints_selection_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (Path("tests") / "slow.hurl").write_text(
        "# entroping: tags=smoke,slow\n\nGET http://localhost:18080/slow\nHTTP 200\n",
        encoding="utf-8",
    )
    (Path("tests") / "billing.hurl").write_text(
        "# entroping: tags=regression,billing\n\nGET http://localhost:18080/billing\nHTTP 200\n",
        encoding="utf-8",
    )

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
    ) -> HurlSuiteResult:
        _ = (options, max_workers)
        return HurlSuiteResult(
            results=tuple(
                HurlFileResult(
                    path=path,
                    command=("hurl", str(path)),
                    status="passed",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=1,
                )
                for path in paths
            )
        )

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = runner.invoke(app, ["run", "--tag-expression", "smoke and not slow"])

    assert result.exit_code == 0
    assert "Hurl selection: 1 selected, 2 skipped by tag expression" in result.output
    latest = json.loads(Path(".entroping/latest-run.json").read_text(encoding="utf-8"))
    assert latest["tests"][0]["path"] == "tests/health.hurl"


def test_run_tag_expression_prints_zero_skipped_selection_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
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
        return HurlSuiteResult(
            results=tuple(
                HurlFileResult(
                    path=path,
                    command=("hurl", str(path)),
                    status="passed",
                    exit_code=0,
                    stdout="",
                    stderr="",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=1,
                )
                for path in paths
            )
        )

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fake_run_hurl_files)

    result = runner.invoke(app, ["run", "--tag-expression", "smoke"])

    assert result.exit_code == 0
    assert "Hurl selection: 1 selected, 0 skipped by tag expression" in result.output


def test_run_tag_expression_no_matches_reports_counts_without_hurl_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    def fail_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
    ) -> HurlSuiteResult:
        _ = (paths, options, max_workers)
        raise AssertionError("no-match tag expression must fail before Hurl execution")

    monkeypatch.setattr("entroping.core.run_workflow.run_hurl_files", fail_run_hurl_files)

    result = runner.invoke(app, ["run", "--tag-expression", "critical and not slow"])

    assert result.exit_code == 0
    assert "No Hurl tests matched tag expression 'critical and not slow'" in result.output
    assert "0 selected, 1 skipped" in " ".join(result.output.split())
    events = _read_run_events()
    assert [event["event"] for event in events] == [
        "run_started",
        "selection_no_match",
        "run_completed",
    ]
    assert events[1]["selected_count"] == 0
    assert events[1]["skipped_count"] == 1
    assert events[-1]["status"] == "no_match"


def test_run_env_fails_with_actionable_missing_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["run", "--env", "local", "--tag", "smoke"])

    assert result.exit_code == 1
    assert "Environment file not found" in result.output


def test_run_preflights_missing_variables_before_hurl_binary_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    result = runner.invoke(app, ["run", "--tag", "smoke"])

    assert result.exit_code == 1
    assert "Unresolved Hurl variables before execution" in result.output
    assert "base_url" in result.output
    assert "Hurl binary not found" not in result.output


def test_run_missing_hurl_binary_writes_error_event_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: None)

    result = runner.invoke(app, ["run", "--tag", "smoke"])

    assert result.exit_code == 1
    assert "Hurl binary not found" in result.output
    events = _read_run_events()
    assert [event["event"] for event in events] == [
        "run_started",
        "test_selected",
        "run_error",
        "run_completed",
    ]
    assert events[2]["error_type"] == "HurlBinaryNotFoundError"
    assert "Hurl binary not found" in str(events[2]["message"])
    assert events[-1]["status"] == "error"
    assert events[-1]["exit_code"] == 1


def test_run_reports_no_matching_hurl_tests_with_ci_exit_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise NoHurlTestsMatchedError("No Hurl tests matched the requested filters.")

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    local_result = CliRunner().invoke(app, ["run", "--tag", "smoke"])
    ci_result = CliRunner().invoke(app, ["run", "--tag", "smoke", "--ci"])

    assert local_result.exit_code == 0
    assert ci_result.exit_code == 1
    assert "No Hurl tests matched" in local_result.output
    assert "No Hurl tests matched" in ci_result.output


def test_run_forwards_changed_from_to_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    captured_kwargs: dict[str, object] = {}

    def fake_execute_run_workflow(**kwargs: object) -> object:
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            suite=HurlSuiteResult(results=()),
            drift_report=None,
            latest_state_path=tmp_path / ".entroping" / "latest-run.json",
            artifacts=(),
            exit_code=0,
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run", "--changed-from", "origin/main"])

    assert result.exit_code == 0
    assert captured_kwargs["changed_from"] == "origin/main"


def test_run_forwards_operation_id_filters_to_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    captured_kwargs: dict[str, object] = {}

    def fake_execute_run_workflow(**kwargs: object) -> object:
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            suite=HurlSuiteResult(results=()),
            drift_report=None,
            latest_state_path=tmp_path / ".entroping" / "latest-run.json",
            artifacts=(),
            exit_code=0,
            selection=SimpleNamespace(selected_count=2, skipped_count=1),
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(
        app,
        ["run", "--operation-id", "createCheckout", "--operation-id", "createRefund"],
    )

    assert result.exit_code == 0
    assert captured_kwargs["operation_ids"] == ("createCheckout", "createRefund")
    assert "Hurl selection: 2 selected, 1 skipped by operation ID" in result.output


def test_run_prints_tag_filter_selection_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        return SimpleNamespace(
            suite=HurlSuiteResult(results=()),
            drift_report=None,
            latest_state_path=tmp_path / ".entroping" / "latest-run.json",
            artifacts=(),
            exit_code=0,
            selection=SimpleNamespace(selected_count=1, skipped_count=2),
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run", "--tag", "smoke"])

    assert result.exit_code == 0
    assert "Hurl selection: 1 selected, 2 skipped by tag filters" in result.output


def test_run_operation_id_no_matches_respects_ci_exit_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise NoHurlTestsMatchedError("No Hurl tests matched OpenAPI operation IDs 'missing'.")

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    local_result = CliRunner().invoke(app, ["run", "--operation-id", "missing"])
    ci_result = CliRunner().invoke(app, ["run", "--operation-id", "missing", "--ci"])

    assert local_result.exit_code == 0
    assert ci_result.exit_code == 1
    assert "No Hurl tests matched OpenAPI operation IDs" in local_result.output
    assert "No Hurl tests matched OpenAPI operation IDs" in ci_result.output


def test_run_loads_named_suite_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "suites").mkdir()
    (tmp_path / "tests").mkdir()
    selected = tmp_path / "tests" / "health.hurl"
    selected.write_text("# entroping: tags=smoke\n", encoding="utf-8")
    (tmp_path / "suites" / "smoke.yaml").write_text(
        """
version: entroping.suite.v1
name: smoke
env: local
tags:
  - smoke
paths:
  - tests/*.hurl
reports:
  - json
  - junit
parallel: true
drift_check: true
""".lstrip(),
        encoding="utf-8",
    )
    captured_kwargs: dict[str, object] = {}

    def fake_execute_run_workflow(**kwargs: object) -> object:
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            suite=HurlSuiteResult(results=()),
            drift_report=None,
            latest_state_path=tmp_path / ".entroping" / "latest-run.json",
            artifacts=(),
            exit_code=0,
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run", "--suite", "smoke", "--ci"])

    assert result.exit_code == 0
    assert captured_kwargs["environment"] == "local"
    assert captured_kwargs["tag_filters"] == ("smoke",)
    assert captured_kwargs["report_formats"] == ("json", "junit")
    assert captured_kwargs["parallel"] is True
    assert captured_kwargs["drift_check"] is True
    assert captured_kwargs["changed_from"] is None
    assert captured_kwargs["selection_label"] == "suite 'smoke'"
    assert captured_kwargs["discovery_roots"] == (selected.resolve(),)


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--suite", "smoke", "--tag", "security"],
        ["run", "--suite", "smoke", "--tag-expression", "smoke and not slow"],
        ["run", "--suite", "smoke", "--operation-id", "createCheckout"],
        ["run", "--suite", "smoke", "--env", "local"],
        ["run", "--suite", "smoke", "--report", "json"],
        ["run", "--suite", "smoke", "--changed-from", "main"],
        ["run", "--suite", "smoke", "--parallel"],
        ["run", "--suite", "smoke", "--drift-check"],
    ],
)
def test_run_rejects_suite_ad_hoc_selector_conflicts(args: list[str]) -> None:
    result = CliRunner().invoke(
        app,
        args,
        env={"CI": "true", "GITHUB_ACTIONS": "true", "TERM": "xterm-256color"},
    )
    plain_output = ANSI_RE.sub("", result.output)

    assert result.exit_code == 2
    assert f"{args[3]} cannot be combined with --suite" in plain_output


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--operation-id", "createCheckout", "--tag", "smoke"],
        ["run", "--operation-id", "createCheckout", "--tag-expression", "smoke"],
        ["run", "--operation-id", "createCheckout", "--changed-from", "main"],
    ],
)
def test_run_rejects_operation_id_ad_hoc_selector_conflicts(args: list[str]) -> None:
    result = CliRunner().invoke(
        app,
        args,
        env={"CI": "true", "GITHUB_ACTIONS": "true", "TERM": "xterm-256color"},
    )
    plain_output = ANSI_RE.sub("", result.output)

    assert result.exit_code == 2
    assert "--operation-id cannot be combined with" in plain_output


def test_run_rejects_empty_operation_id_filter() -> None:
    result = CliRunner().invoke(app, ["run", "--operation-id", ""])

    assert result.exit_code == 2
    assert "Operation ID filters must not be empty" in result.output


def test_run_named_suite_no_matches_respects_ci_exit_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "empty.yaml").write_text(
        "version: entroping.suite.v1\nname: empty\npaths:\n  - tests/nope*.hurl\n",
        encoding="utf-8",
    )

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise NoHurlTestsMatchedError("No Hurl tests matched suite 'empty'.")

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    local_result = CliRunner().invoke(app, ["run", "--suite", "empty"])
    ci_result = CliRunner().invoke(app, ["run", "--suite", "empty", "--ci"])

    assert local_result.exit_code == 0
    assert ci_result.exit_code == 1
    assert "No Hurl tests matched suite 'empty'" in local_result.output
    assert "No Hurl tests matched suite 'empty'" in ci_result.output


def test_run_named_suite_reports_manifest_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text("[", encoding="utf-8")

    result = CliRunner().invoke(app, ["run", "--suite", "smoke"])

    assert result.exit_code == 1
    assert "Invalid YAML" in result.output


def test_run_reports_empty_changed_selection_with_ci_exit_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise NoHurlTestsMatchedError("No changed Hurl tests matched from base ref 'main'.")

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    local_result = CliRunner().invoke(app, ["run", "--changed-from", "main"])
    ci_result = CliRunner().invoke(app, ["run", "--changed-from", "main", "--ci"])

    assert local_result.exit_code == 0
    assert ci_result.exit_code == 1
    assert "No changed Hurl tests matched" in local_result.output
    assert "No changed Hurl tests matched" in ci_result.output


def test_run_prints_failed_stdout_from_workflow_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    failed = HurlFileResult(
        path=tmp_path / "tests" / "health.hurl",
        command=("hurl", "health.hurl"),
        status="failed",
        exit_code=1,
        stdout="assertion failed on stdout",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_ms=12,
    )

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        return SimpleNamespace(
            suite=HurlSuiteResult(results=(failed,)),
            drift_report=None,
            latest_state_path=tmp_path / ".entroping" / "latest-run.json",
            artifacts=(),
            exit_code=1,
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code == 1
    assert "health.hurl: failed" in result.output
    assert "assertion failed on stdout" in result.output


def test_run_prints_typed_dependency_drift_observation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise DependencyDriftObservationError(
            "Could not build dependency drift observations: traffic state unavailable"
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run", "--report", "drift"])

    assert result.exit_code == 1
    assert "Could not build dependency drift observations" in result.output
    assert "traffic state unavailable" in result.output


def test_run_known_failure_configuration_errors_exit_nonzero_in_ci(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise RunWorkflowError(
            "Known failure exception did not match any selected injected gate: "
            "GH-404 tests/health.hurl rule missing_latency"
        )

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run", "--ci"])

    assert result.exit_code == 1
    assert "Known failure exception did not match" in result.output
    assert "GH-404" in result.output
    assert "missing_latency" in result.output


def test_run_rejects_unsupported_report_format() -> None:
    result = CliRunner().invoke(app, ["run", "--report", "xml"])

    assert result.exit_code == 2
    assert "Unsupported report format" in result.output


def test_run_rejects_empty_tag_filter() -> None:
    result = CliRunner().invoke(app, ["run", "--tag", ""])

    assert result.exit_code == 2
    assert "Tag filters must not be empty" in result.output


def test_run_rejects_tag_filter_and_tag_expression_mix() -> None:
    result = CliRunner().invoke(
        app,
        ["run", "--tag", "smoke", "--tag-expression", "checkout"],
    )

    assert result.exit_code == 2
    plain_output = " ".join(ANSI_RE.sub("", result.output).split())
    assert "--tag cannot be combined with" in plain_output
    assert "--tag-expression" in plain_output


def test_run_rejects_invalid_tag_expression_before_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise AssertionError("invalid tag expressions must fail before workflow execution")

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fail_execute_run_workflow)

    result = CliRunner().invoke(app, ["run", "--tag-expression", "smoke and"])

    assert result.exit_code == 2
    assert "Invalid tag expression" in result.output
