from cli_architect_test_helpers import (
    _agent_run_manifest_payloads,
)
from cli_test_support import (
    ArchitectPromptPackage,
    CliRunner,
    LiteLLMCompletionResult,
    LiteLLMUsage,
    Path,
    app,
    architect_cli,
    json,
    pytest,
    subprocess,
)


def test_architect_audit_reports_missing_openapi_coverage_as_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
  /checkout:
    post:
      operationId: createCheckout
      responses:
        "201":
          description: created
""".lstrip(),
        encoding="utf-8",
    )
    generated = Path("tests/generated")
    generated.mkdir(parents=True)
    (generated / "get_health.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=getHealth",
                "",
                "GET {{base_url}}/health",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )
    (generated / "stale_checkout.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=staleCheckout",
                "",
                "GET {{base_url}}/stale-checkout",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "audit", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.openapi-audit.v1"
    assert payload["status"] == "fail"
    assert payload["summary"]["missing_operations"] == 1
    assert payload["summary"]["happy_path_covered_operations"] == 1
    assert payload["summary"]["auth_negative_covered_operations"] == 0
    assert payload["summary"]["validation_negative_covered_operations"] == 0
    assert payload["summary"]["ambiguous_operations"] == 0
    assert payload["summary"]["stale_references"] == 1
    assert payload["findings"][0]["operation_id"] == "createCheckout"
    assert payload["operation_matrix"] == [
        {
            "operation_id": "getHealth",
            "method": "GET",
            "path": "/health",
            "status": "covered",
            "tests": ["tests/generated/get_health.hurl"],
            "negative_tests": [],
            "auth_negative_tests": [],
            "validation_negative_tests": [],
        },
        {
            "operation_id": "createCheckout",
            "method": "POST",
            "path": "/checkout",
            "status": "uncovered",
            "tests": [],
            "negative_tests": [],
            "auth_negative_tests": [],
            "validation_negative_tests": [],
        },
    ]
    assert payload["stale_references"] == [
        {
            "operation_id": "staleCheckout",
            "test_path": "tests/generated/stale_checkout.hurl",
        }
    ]
    assert str(tmp_path) not in result.output


def test_architect_audit_reports_traffic_routes_without_leaking_query_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from entroping.core.traffic_redactor import redact_traffic_exchange
    from entroping.core.traffic_store import TrafficStore
    from entroping.models.traffic import TrafficExchange, TrafficRequest, TrafficResponse

    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
  traffic: .entroping/state.db
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
  /orders/{order_id}:
    get:
      operationId: getOrder
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )
    generated = Path("tests/generated")
    generated.mkdir(parents=True)
    (generated / "get_health.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=getHealth",
                "",
                "GET {{base_url}}/health",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )
    (generated / "get_order.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=getOrder",
                "",
                "GET {{base_url}}/orders/123",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )
    store = TrafficStore.open_project(tmp_path)
    for method, url in (
        ("GET", "https://api.example.test/health"),
        ("GET", "https://api.example.test/orders/123"),
        ("POST", "https://api.example.test/internal-debug?token=live-secret"),
    ):
        store.record_exchange(
            redact_traffic_exchange(
                TrafficExchange(
                    captured_at=datetime(2026, 6, 4, 8, 0, tzinfo=UTC),
                    duration_ms=20,
                    request=TrafficRequest(method=method, url=url),
                    response=TrafficResponse(status_code=200),
                )
            )
        )

    result = CliRunner().invoke(app, ["architect", "audit", "--output", "json"])

    assert result.exit_code == 1
    assert "live-secret" not in result.output
    assert "token" not in result.output
    payload = json.loads(result.output)
    assert payload["summary"]["missing_operations"] == 0
    traffic_routes = payload["traffic_routes"]
    assert traffic_routes["summary"] == {
        "documented_routes": 2,
        "undocumented_routes": 1,
        "ambiguous_routes": 0,
        "spec_only_routes": 0,
    }
    assert traffic_routes["documented_routes"][1]["operation_ids"] == ["getOrder"]
    assert traffic_routes["undocumented_routes"] == [
        {
            "method": "POST",
            "path_template": "/internal-debug",
            "call_count": 1,
            "failure_count": 0,
        }
    ]


def test_architect_audit_traffic_helper_skips_missing_or_empty_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.core.traffic_store import TrafficStoreError

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    def missing_state(root: Path) -> tuple[object, ...]:
        _ = root
        raise TrafficStoreError("traffic state not found")

    monkeypatch.setattr(architect_cli, "list_project_exchanges_readonly", missing_state)
    assert architect_cli._load_traffic_openapi_audit(document) is None

    monkeypatch.setattr(
        architect_cli,
        "list_project_exchanges_readonly",
        lambda root: (),
    )
    assert architect_cli._load_traffic_openapi_audit(document) is None


def test_architect_audit_traffic_helper_wraps_store_and_compilation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.bridge.traffic_sessions import TrafficSessionError
    from entroping.core.traffic_store import TrafficStoreError

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    def broken_state(root: Path) -> tuple[object, ...]:
        _ = root
        raise TrafficStoreError("schema broken")

    monkeypatch.setattr(architect_cli, "list_project_exchanges_readonly", broken_state)
    with pytest.raises(ValueError, match="could not read traffic state"):
        architect_cli._load_traffic_openapi_audit(document)

    monkeypatch.setattr(
        architect_cli,
        "list_project_exchanges_readonly",
        lambda root: ("record",),
    )

    def unsafe_session(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise TrafficSessionError("requires redacted traffic")

    monkeypatch.setattr(architect_cli, "build_traffic_session_candidate", unsafe_session)
    with pytest.raises(ValueError, match="could not audit traffic routes"):
        architect_cli._load_traffic_openapi_audit(document)


def test_architect_audit_passes_when_openapi_operations_are_covered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )
    generated = Path("tests/generated")
    generated.mkdir(parents=True)
    (generated / "get_health.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=getHealth",
                "",
                "GET {{base_url}}/health",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "audit"])

    assert result.exit_code == 0
    assert "Architect Audit" in result.output
    assert "## Operation Coverage Matrix" in result.output
    assert (
        "| getHealth | GET | /health | covered | tests/generated/get_health.hurl |"
        in result.output
    )
    assert "No OpenAPI coverage gaps found." in result.output


def test_architect_audit_changed_from_reports_breaking_diff_and_linked_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Entroping Test"],
        check=True,
        capture_output=True,
        text=True,
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
  /legacy:
    delete:
      operationId: deleteLegacy
      responses:
        "204":
          description: deleted
""".lstrip(),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True, text=True)
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )
    generated = Path("tests/generated")
    generated.mkdir(parents=True)
    (generated / "get_health.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=getHealth",
                "",
                "GET {{base_url}}/health",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )
    (generated / "delete_legacy.hurl").write_text(
        "\n".join(
            [
                "# entroping: source=openapi",
                "# entroping: operation_id=deleteLegacy",
                "",
                "DELETE {{base_url}}/legacy",
                "HTTP 204",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["architect", "audit", "--changed-from", "HEAD", "--output", "json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["openapi_diff"]["schema_version"] == "entroping.openapi-breaking-diff.v1"
    assert payload["openapi_diff"]["base_ref"] == "HEAD"
    assert payload["openapi_diff"]["summary"]["breaking_findings"] == 1
    assert payload["openapi_diff"]["findings"] == [
        {
            "code": "OPENAPI_OPERATION_REMOVED",
            "severity": "error",
            "operation_id": "deleteLegacy",
            "method": "DELETE",
            "path": "/legacy",
            "message": "OpenAPI operation 'deleteLegacy' was removed from DELETE /legacy.",
            "base_operation_id": None,
            "base_method": "DELETE",
            "base_path": "/legacy",
            "evidence": [],
            "test_paths": ["tests/generated/delete_legacy.hurl"],
        },
    ]
    assert not Path("reports").exists()


def test_architect_audit_changed_from_outputs_markdown_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Entroping Test"],
        check=True,
        capture_output=True,
        text=True,
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True, text=True)
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
  /refunds:
    post:
      operationId: createRefund
      responses:
        "202":
          description: accepted
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["architect", "audit", "--changed-from", "HEAD", "--output", "md"],
    )

    assert result.exit_code == 1
    assert "## OpenAPI Breaking-Change Diff" in result.output
    assert "| info | OPENAPI_OPERATION_ADDED | createRefund | POST | /refunds | - | - |" in (
        result.output
    )


def test_architect_audit_changed_from_rejects_remote_spec_before_git_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: https://example.invalid/openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "audit", "--changed-from", "HEAD"])

    assert result.exit_code == 1
    assert "--changed-from requires a local OpenAPI sources.spec path" in result.output


def test_architect_audit_auditor_focus_outputs_validated_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/auditor.md").write_text(
        "Review committed tests for coverage and policy gaps.",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
agents:
  auditor:
    source: agents/auditor.md
    model: openai/auditor-model
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /checkout:
    post:
      operationId: createCheckout
      responses:
        "201":
          description: created
""".lstrip(),
        encoding="utf-8",
    )
    packages: list[ArchitectPromptPackage] = []

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = self
        packages.append(package)
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "Checkout authorization is under-tested.",
                    "findings": [
                        {
                            "code": "AUTH_NEGATIVE_COVERAGE",
                            "severity": "error",
                            "title": "Missing unauthorized checkout test",
                            "detail": "No committed Hurl test asserts 401 or 403.",
                            "recommendation": "Generate a Breaker invalid-token test.",
                            "evidence": ["operation:createCheckout"],
                        }
                    ],
                },
            ),
            model="openai/auditor-model",
            latency_ms=33,
            usage=LiteLLMUsage(prompt_tokens=11, completion_tokens=22, total_tokens=33),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "audit", "--focus", "auditor", "--output", "json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "fail"
    assert payload["agent"] == "auditor"
    assert payload["model"] == "openai/auditor-model"
    assert payload["findings"][0]["code"] == "AUTH_NEGATIVE_COVERAGE"
    assert packages
    assert packages[0].role == "auditor"
    assert "OPENAPI_COVERAGE_MISSING" in packages[0].messages[1].content
    assert not Path("reports").exists()
    manifests = _agent_run_manifest_payloads()
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest["command"] == "architect audit"
    assert manifest["mode"] == "review"
    assert manifest["agent"] == "auditor"
    assert manifest["model"] == "openai/auditor-model"
    assert manifest["output_paths"] == []
    assert manifest["validation"] == {
        "hurl_validated": False,
        "status": "passed",
        "structured_output_validated": True,
    }


def test_architect_audit_auditor_focus_outputs_validated_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/auditor.md").write_text("Review committed tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
agents:
  auditor:
    source: agents/auditor.md
    model: openai/auditor-model
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "Coverage is acceptable.",
                    "findings": [],
                    "warnings": ["Keep generated tests reviewed."],
                },
            ),
            model="openai/auditor-model",
            latency_ms=15,
            usage=LiteLLMUsage(prompt_tokens=5, completion_tokens=7, total_tokens=12),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "audit", "--focus", "auditor", "--output", "md"],
    )

    assert result.exit_code == 0
    assert "# Architect Auditor Review" in result.output
    assert "Status: pass" in result.output
    assert "Coverage is acceptable." in result.output
    assert "No Auditor findings." in result.output


def test_architect_audit_auditor_focus_rejects_missing_agent_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )
    provider_called = False

    def fake_complete(self: object, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
        nonlocal provider_called
        _ = (self, package)
        provider_called = True
        raise AssertionError("provider should not be called")

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(app, ["architect", "audit", "--focus", "auditor"])

    assert result.exit_code == 1
    assert "No agent config found for role auditor" in result.output
    assert provider_called is False


def test_architect_audit_auditor_focus_rejects_invalid_provider_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/auditor.md").write_text("Review committed tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
agents:
  auditor:
    source: agents/auditor.md
    model: openai/auditor-model
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content="not-json sk-proj-live-secret",
            model="openai/auditor-model",
            latency_ms=1,
            usage=LiteLLMUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(app, ["architect", "audit", "--focus", "auditor"])

    assert result.exit_code == 1
    assert "sk-proj-live-secret" not in result.output
    assert "[REDACTED]" in result.output
    assert "Auditor output validation failed before display." in result.output
    assert "No files were written." in result.output


def test_architect_audit_rejects_unsupported_focus() -> None:
    result = CliRunner().invoke(app, ["architect", "audit", "--focus", "security"])

    assert result.exit_code == 1
    assert "Unsupported architect audit focus" in result.output
    assert "supported focus: logic, auditor" in result.output


def test_architect_audit_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["architect", "audit", "--output", "yaml"])

    assert result.exit_code == 1
    assert "Unsupported architect audit output" in result.output


def test_architect_audit_requires_configured_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["architect", "audit"])

    assert result.exit_code == 1
    assert "sources.spec is required for architect audit" in result.output
