"""CLI adapter tests for watch, freeze, map, and studio commands."""

from cli_test_support import (
    CliRunner,
    HurlValidationError,
    MitmproxyUnavailableError,
    Path,
    StudioDependencyError,
    WatchConfig,
    _record_freeze_exchange,
    _record_mock_exchange,
    app,
    json,
    pytest,
    render_studio_status,
    subprocess,
)


def test_watch_invokes_capture_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[WatchConfig] = []

    async def fake_run_watch(config: WatchConfig) -> None:
        calls.append(config)
        return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.run_watch", fake_run_watch)

    result = CliRunner().invoke(
        app,
        ["watch", "--port", "8090", "--target", "https://api.example.test"],
    )

    assert result.exit_code == 0
    assert "not implemented" not in result.output
    assert "Capturing traffic on 127.0.0.1:8090" in result.output
    assert calls == [
        WatchConfig(
            project_root=tmp_path,
            listen_port=8090,
            target_url="https://api.example.test",
        )
    ]


def test_watch_accepts_explicit_capture_scope_and_prints_safe_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[WatchConfig] = []

    async def fake_run_watch(config: WatchConfig) -> object:
        calls.append(config)
        from entroping.core.traffic_proxy import WatchRunSummary

        return WatchRunSummary(recorded_count=2, ignored_count=1, malformed_count=1)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.run_watch", fake_run_watch)

    result = CliRunner().invoke(
        app,
        [
            "watch",
            "--scope-host",
            "API.EXAMPLE.TEST",
            "--scope-url-prefix",
            "https://payments.example.test/api/v1",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        WatchConfig(
            project_root=tmp_path,
            scope_hosts=("api.example.test",),
            scope_url_prefixes=("https://payments.example.test/api/v1",),
        )
    ]
    assert "Capture scope: 1 host, 1 URL prefix" in result.output
    assert "Recorded 2 in-scope traffic flows" in result.output
    assert "Ignored 1 out-of-scope traffic flow" in result.output
    assert "Ignored 1 malformed traffic flow" in result.output
    assert "payments.example.test/api/v1" not in result.output


def test_watch_requires_explicit_capture_scope_without_calling_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_run_watch(config: WatchConfig) -> None:
        nonlocal called
        _ = config
        called = True

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.run_watch", fake_run_watch)

    result = CliRunner().invoke(app, ["watch"])

    assert result.exit_code == 1
    assert "explicit capture scope" in result.output
    assert called is False


def test_watch_prints_actionable_missing_proxy_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_run_watch(config: WatchConfig) -> None:
        _ = config
        raise MitmproxyUnavailableError("mitmproxy is required; run uv sync --extra proxy")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.run_watch", fail_run_watch)

    result = CliRunner().invoke(app, ["watch", "--scope-host", "api.example.test"])

    assert result.exit_code == 1
    assert "mitmproxy is required" in result.output
    assert "uv sync --extra proxy" in result.output


def test_watch_handles_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def interrupt_run_watch(config: WatchConfig) -> None:
        _ = config
        raise KeyboardInterrupt

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.run_watch", interrupt_run_watch)

    result = CliRunner().invoke(app, ["watch", "--scope-host", "api.example.test"])

    assert result.exit_code == 0
    assert "Stopped traffic capture" in result.output


def test_freeze_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["freeze", "--name", "checkout_flow"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output
    assert not Path("tests/generated/checkout_flow.hurl").exists()


def test_freeze_rejects_unsafe_flow_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["freeze", "--name", "../checkout"])

    assert result.exit_code == 1
    assert "freeze name" in result.output
    assert not Path("tests/generated/checkout.hurl").exists()


def test_freeze_writes_validated_hurl_from_redacted_traffic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path, secret="live-secret")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "entroping.core.freeze.validate_hurl_content",
        lambda content, display_path: None,
    )

    result = CliRunner().invoke(app, ["freeze", "--name", "checkout_flow", "--golden"])

    output = Path("tests/generated/checkout_flow.hurl")
    manifest = Path("reports/approvals/freeze-checkout_flow.json")
    assert result.exit_code == 0
    assert "Wrote Hurl test: tests/generated/checkout_flow.hurl" in result.output
    assert "Wrote approval manifest: reports/approvals/freeze-checkout_flow.json" in result.output
    assert output.is_file()
    assert manifest.is_file()
    content = output.read_text(encoding="utf-8")
    manifest_content = manifest.read_text(encoding="utf-8")
    assert "# entroping: source=traffic" in content
    assert "POST https://api.example.test/checkout?token=%5BREDACTED%5D" in content
    assert "Authorization: [REDACTED]" in content
    assert "live-secret" not in content
    assert "live-secret" not in manifest_content
    assert 'jsonpath "$.status" == "accepted"' in content


def test_freeze_applies_cli_capture_filters_before_hurl_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path, secret="checkout-secret")
    _record_mock_exchange(tmp_path, secret="wire-secret")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "entroping.core.freeze.validate_hurl_content",
        lambda content, display_path: None,
    )

    result = CliRunner().invoke(
        app,
        [
            "freeze",
            "--name",
            "checkout_flow",
            "--include-host",
            "api.example.test",
            "--include-method",
            "post",
            "--include-path",
            "/checkout",
            "--exclude-host",
            "payments.example.test",
        ],
    )

    output = Path("tests/generated/checkout_flow.hurl")
    assert result.exit_code == 0
    assert "Froze 1 traffic record into Hurl" in result.output
    content = output.read_text(encoding="utf-8")
    assert "POST https://api.example.test/checkout?token=%5BREDACTED%5D" in content
    assert "payments.example.test" not in content
    assert "checkout-secret" not in content
    assert "wire-secret" not in content


def test_freeze_reports_empty_cli_capture_filters_without_writing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["freeze", "--name", "checkout_flow", "--include-host", "missing.example.test"],
    )

    assert result.exit_code == 1
    assert "No traffic records matched capture filters" in result.output
    assert not Path("tests/generated/checkout_flow.hurl").exists()


def test_freeze_rejects_unsafe_cli_capture_filter_without_leaking_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["freeze", "--name", "checkout_flow", "--include-path", "/checkout?token=secret"],
    )

    assert result.exit_code == 1
    assert "path" in result.output
    assert "secret" not in result.output
    assert not Path("tests/generated/checkout_flow.hurl").exists()


def test_freeze_validation_failure_does_not_write_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fail_validation(content: str, display_path: str) -> None:
        _ = content
        raise HurlValidationError(f"Generated Hurl failed parser validation: {display_path}")

    monkeypatch.setattr("entroping.core.freeze.validate_hurl_content", fail_validation)

    result = CliRunner().invoke(app, ["freeze", "--name", "checkout_flow"])

    assert result.exit_code == 1
    assert (
        "Generated Hurl failed parser validation: tests/generated/checkout_flow.hurl"
        in result.output
    )
    assert not Path("tests/generated/checkout_flow.hurl").exists()


def test_freeze_mock_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["freeze", "--name", "refund_flow", "--mock", "payments"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output
    assert not Path("mocks/payments").exists()


def test_freeze_mock_rejects_unsafe_mock_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_mock_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["freeze", "--name", "refund_flow", "--mock", "../payments"])

    assert result.exit_code == 1
    assert "mock service" in result.output
    assert not Path("mocks/payments").exists()


def test_freeze_mock_reports_no_matching_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_mock_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["freeze", "--name", "refund_flow", "--mock", "shipping"])

    assert result.exit_code == 1
    assert "No traffic records matched mock service" in result.output
    assert not Path("mocks/shipping").exists()


def test_freeze_mock_writes_wiremock_mapping_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_mock_exchange(tmp_path, secret="wire-secret")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["freeze", "--name", "refund_flow", "--mock", "payments"])

    output = Path("mocks/payments/refund_flow-001.json")
    manifest = Path("reports/approvals/freeze-refund_flow-mock-payments.json")
    assert result.exit_code == 0
    assert "Wrote WireMock mapping: mocks/payments/refund_flow-001.json" in result.output
    assert (
        "Wrote approval manifest: reports/approvals/freeze-refund_flow-mock-payments.json"
        in result.output
    )
    assert output.is_file()
    assert manifest.is_file()
    content = output.read_text(encoding="utf-8")
    manifest_content = manifest.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["request"] == {"method": "POST", "urlPath": "/charge"}
    assert payload["response"]["status"] == 201
    assert payload["response"]["headers"] == {"Content-Type": "application/json"}
    assert payload["response"]["jsonBody"]["token"] == "[REDACTED]"
    assert "wire-secret" not in manifest_content
    assert "wire-secret" not in content


def test_freeze_mock_applies_cli_capture_filters_before_mapping_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path, secret="checkout-secret")
    _record_mock_exchange(tmp_path, secret="wire-secret")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "freeze",
            "--name",
            "refund_flow",
            "--mock",
            "payments",
            "--include-host",
            "payments.example.test",
            "--include-path",
            "/charge",
        ],
    )

    output = Path("mocks/payments/refund_flow-001.json")
    assert result.exit_code == 0
    assert "Froze 1 traffic mapping into WireMock" in result.output
    content = output.read_text(encoding="utf-8")
    assert "payments.example.test" not in content
    assert "checkout" not in content
    assert "checkout-secret" not in content
    assert "wire-secret" not in content


def test_map_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["map"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output


def test_map_reports_empty_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.core.traffic_store import TrafficStore

    TrafficStore.open_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["map", "--export", "mermaid"])

    assert result.exit_code == 1
    assert "contains no traffic records" in result.output


def test_map_rejects_unsupported_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["map", "--export", "svg"])

    assert result.exit_code == 1
    assert "Unsupported map export" in result.output
    assert "mermaid, dot, md, png" in result.output


def test_map_png_reports_missing_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: None)

    result = CliRunner().invoke(app, ["map", "--export", "png"])

    assert result.exit_code == 1
    assert "Graphviz dot is required" in result.output
    assert "use --export" in result.output
    assert "mermaid, dot, or md" in result.output


def test_map_png_writes_dependency_map_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path, secret="png-secret")

    def fake_run(
        args: list[str],
        *,
        input: bytes,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        _ = input, capture_output, text, timeout, check, shell
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=b"\x89PNG\r\n",
            stderr=b"",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.core.dependency_mapper.shutil.which", lambda name: "/bin/dot")
    monkeypatch.setattr("entroping.core.dependency_mapper.subprocess.run", fake_run)

    result = CliRunner().invoke(app, ["map", "--export", "png"])

    assert result.exit_code == 0
    assert Path("reports/dependency-map.png").read_bytes() == b"\x89PNG\r\n"
    assert "Wrote dependency map: reports/dependency-map.png" in result.output
    assert "Wrote approval manifest: reports/approvals/dependency-map-png.json" in result.output
    assert Path("reports/approvals/dependency-map-png.json").is_file()
    assert "png-secret" not in result.output


def test_map_outputs_markdown_from_redacted_traffic_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path, secret="map-secret")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["map", "--export", "md"])

    assert result.exit_code == 0
    assert "| Host | Method | Path | Calls | Failures | Min ms | Avg ms | Max ms |" in result.output
    assert "| api.example.test | POST | /checkout | 1 | 0 | 25 | 25 | 25 |" in result.output
    assert "flowchart LR" in result.output
    assert "map-secret" not in result.output


def test_map_applies_cli_capture_filters_before_graph_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_freeze_exchange(tmp_path, secret="map-secret")
    _record_mock_exchange(tmp_path, secret="wire-secret")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "map",
            "--export",
            "md",
            "--include-host",
            "api.example.test",
            "--exclude-path",
            "/charge",
        ],
    )

    assert result.exit_code == 0
    assert "| api.example.test | POST | /checkout | 1 | 0 | 25 | 25 | 25 |" in result.output
    assert "payments.example.test" not in result.output
    assert "map-secret" not in result.output
    assert "wire-secret" not in result.output


def test_studio_missing_optional_dependency_returns_setup_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_dependency_check() -> None:
        raise StudioDependencyError("Install Studio dependencies with: uv sync --extra studio")

    monkeypatch.setattr(
        "entroping.cli.commands.execution.ensure_studio_available",
        fail_dependency_check,
    )

    result = CliRunner().invoke(app, ["studio", "--env", "local"])

    assert result.exit_code == 1
    assert "uv sync --extra studio" in result.output
    assert "not built yet" not in result.output


def test_studio_read_only_status_without_latest_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.ensure_studio_available", lambda: None)
    monkeypatch.setattr(
        "entroping.cli.commands.execution.run_studio_app",
        lambda status: print(render_studio_status(status), end=""),
    )
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["studio", "--env", "local"])

    assert result.exit_code == 0
    assert "Entroping Studio (read-only)" in result.output
    assert "Environment: local" in result.output
    assert "Project: entroping-project" in result.output
    assert "Latest run: none" in result.output
    assert "Traffic state: missing" in result.output
    assert "not built yet" not in result.output


def test_studio_read_only_status_with_latest_run_and_no_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.commands.execution.ensure_studio_available", lambda: None)
    monkeypatch.setattr(
        "entroping.cli.commands.execution.run_studio_app",
        lambda status: print(render_studio_status(status), end=""),
    )
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    state_dir = Path(".entroping")
    state_dir.mkdir(exist_ok=True)
    (state_dir / "state.db").write_bytes(b"sqlite")
    (state_dir / "latest-run.json").write_text(
        json.dumps(
            {
                "project": "entroping-project",
                "environment": "local",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": ".entroping/run-1/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text("{}\n", encoding="utf-8")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    result = runner.invoke(app, ["studio", "--env", "local"])

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert result.exit_code == 0
    assert "Latest run: 1 passed, 0 failed, 1 total" in result.output
    assert "Reports: reports/run-latest.json" in result.output
    assert "Traffic state: available" in result.output
    assert after == before
