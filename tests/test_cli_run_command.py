"""CLI adapter tests for run command behavior."""

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
    SimpleNamespace,
    app,
    execution_cli,
    json,
    pytest,
    subprocess,
)


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
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (Path("tests") / "checkout.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run_hurl_files(
        paths: list[Path],
        options: HurlRunOptions,
        *,
        max_workers: int = 1,
    ) -> HurlSuiteResult:
        captured["max_workers"] = max_workers
        captured["timeout_ms"] = options.timeout_ms
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
    assert captured == {"max_workers": 2, "timeout_ms": 30_000}
    assert "Hurl run: 2 passed, 0 failed" in result.output


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


def test_run_reports_no_matching_hurl_tests_with_ci_exit_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_execute_run_workflow(**kwargs: object) -> object:
        _ = kwargs
        raise NoHurlTestsMatchedError("no matches")

    monkeypatch.setattr(execution_cli, "execute_run_workflow", fake_execute_run_workflow)

    local_result = CliRunner().invoke(app, ["run", "--tag", "smoke"])
    ci_result = CliRunner().invoke(app, ["run", "--tag", "smoke", "--ci"])

    assert local_result.exit_code == 0
    assert ci_result.exit_code == 1
    assert "No Hurl tests matched" in local_result.output
    assert "No Hurl tests matched" in ci_result.output


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


def test_run_rejects_unsupported_report_format() -> None:
    result = CliRunner().invoke(app, ["run", "--report", "xml"])

    assert result.exit_code == 2
    assert "Unsupported report format" in result.output


def test_run_rejects_empty_tag_filter() -> None:
    result = CliRunner().invoke(app, ["run", "--tag", ""])

    assert result.exit_code == 2
    assert "Tag filters must not be empty" in result.output
