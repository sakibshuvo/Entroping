"""CLI adapter tests for architect commands."""

from cli_test_support import (
    ArchitectPromptPackage,
    BrainProviderError,
    CliRunner,
    GeneratedHurlFile,
    HurlValidationError,
    LiteLLMCompletionResult,
    LiteLLMCostEstimate,
    LiteLLMUsage,
    OpenApiHurlCompilationResult,
    Path,
    _accept_architect_hurl_validation,
    _accept_architect_refactor_hurl_validation,
    _accept_openapi_hurl_validation,
    app,
    architect_cli,
    json,
    pytest,
    subprocess,
)


def _agent_run_manifest_payloads() -> list[dict[str, object]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((Path(".entroping") / "agent-runs").glob("*.json"))
    ]


def _assert_builder_prompt_package(package: ArchitectPromptPackage) -> None:
    assert package.role == "builder"
    assert package.model == "openai/gpt-4.1-mini"
    assert package.input_cost_per_1m_tokens_usd == 0.25
    assert package.output_cost_per_1m_tokens_usd == 1.25
    assert package.temperature == 0.1
    assert "Build minimal checkout Hurl tests." in package.messages[0].content
    assert "global_latency" in package.messages[0].content
    assert "Generate checkout smoke coverage." in package.messages[1].content
    assert "Requested Entroping tags: ai" in package.messages[1].content


def _assert_ai_checkout_hurl_output() -> None:
    output_path = Path("tests/generated/ai_checkout.hurl")
    assert output_path.is_file()
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: source=architect\n"
        "# entroping: tags=ai\n"
        "POST {{base_url}}/checkout\n"
        "HTTP 201\n"
    )


def _assert_builder_agent_manifest(manifest: dict[str, object]) -> None:
    assert manifest["schema_version"] == "entroping.agent-run-manifest.v1"
    assert manifest["command"] == "architect build"
    assert manifest["mode"] == "create"
    assert manifest["agent"] == "builder"
    assert manifest["model"] == "openai/gpt-4.1-mini"
    assert manifest["provider"] == "openai"
    assert manifest["cost"] == {
        "estimated_usd": 0.000042,
        "input_cost_per_1m_tokens_usd": 0.25,
        "output_cost_per_1m_tokens_usd": 1.25,
    }
    assert manifest["output_paths"] == ["tests/generated/ai_checkout.hurl"]
    assert manifest["tags"] == ["ai"]
    assert manifest["validation"] == {
        "hurl_validated": True,
        "status": "passed",
        "structured_output_validated": True,
    }
    raw_manifest = json.dumps(manifest, sort_keys=True)
    assert "Generate checkout smoke coverage." not in raw_manifest
    assert "Build minimal checkout Hurl tests." not in raw_manifest


def test_architect_build_new_generates_hurl_from_configured_openapi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_openapi_hurl_validation(monkeypatch)
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
          content:
            application/json:
              schema:
                type: object
                required:
                  - status
                properties:
                  status:
                    type: string
                    enum:
                      - ok
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new", "--tag", "smoke"])

    assert result.exit_code == 0
    assert "Generated 1 Hurl test" in result.output
    generated = Path("tests/generated/get_health.hurl")
    assert generated.is_file()
    content = generated.read_text(encoding="utf-8")
    assert "# entroping: tags=generated,smoke" in content
    assert "# entroping: source=openapi" in content
    assert "GET {{base_url}}/health" in content
    assert "HTTP 200" in content


def test_architect_build_new_generates_security_negative_tests_and_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_openapi_hurl_validation(monkeypatch)
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
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
    oauth:
      type: oauth2
      flows: {}
paths:
  /secure:
    get:
      operationId: getSecure
      security:
        - bearerAuth: []
        - oauth: []
      responses:
        "200":
          description: ok
        "401":
          description: unauthorized
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 0
    assert "Generated 3 Hurl tests" in result.output
    assert "OpenAPI security coverage warning: getSecure oauth" in result.output
    assert "unsupported security scheme type oauth2" in result.output
    missing = Path("tests/generated/security/get_secure_missing_auth.hurl")
    invalid = Path("tests/generated/security/get_secure_invalid_bearer_auth.hurl")
    assert missing.is_file()
    assert invalid.is_file()
    assert "# entroping: security=missing_auth" in missing.read_text(encoding="utf-8")
    assert "Authorization: Bearer invalid-token" in invalid.read_text(encoding="utf-8")


def test_architect_build_new_writes_parameterized_generated_hurl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_openapi_hurl_validation(monkeypatch)
    Path("qanstitution.yaml").write_text(
        """
project: orders-api
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
  /orders/{order_id}:
    get:
      operationId: getOrder
      parameters:
        - name: order_id
          in: path
          required: true
          schema:
            type: string
        - name: include
          in: query
          schema:
            type: string
            enum:
              - events
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new", "--tag", "orders"])

    assert result.exit_code == 0
    content = Path("tests/generated/get_order.hurl").read_text(encoding="utf-8")
    assert "GET {{base_url}}/orders/{{order_id}}?include=events" in content


def test_architect_build_new_changed_from_generates_only_changed_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_openapi_hurl_validation(monkeypatch)
    subprocess.run(["git", "init", "-b", "main"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "entroping@example.test"],
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
  /checkout:
    post:
      operationId: createCheckout
      responses:
        "200":
          description: ok
  /orders:
    get:
      operationId: listOrdersOld
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
  /checkout:
    post:
      operationId: createCheckout
      responses:
        "201":
          description: created
  /orders:
    get:
      operationId: listOrders
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
        ["architect", "build", "--new", "--changed-from", "HEAD", "--tag", "smoke"],
    )

    assert result.exit_code == 0
    assert "OpenAPI changes from HEAD: added=1, modified=1, renamed=1, removed=1, unchanged=1" in (
        result.output
    )
    assert "Removed OpenAPI operations require manual review: deleteLegacy" in result.output
    assert "Generated 3 Hurl tests" in result.output
    assert not Path("tests/generated/get_health.hurl").exists()
    assert Path("tests/generated/create_checkout.hurl").is_file()
    assert Path("tests/generated/list_orders.hurl").is_file()
    assert Path("tests/generated/create_refund.hurl").is_file()
    assert not Path("tests/generated/delete_legacy.hurl").exists()


def test_architect_build_new_changed_from_exits_cleanly_when_only_removed_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_openapi_hurl_validation(monkeypatch)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ./openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    Path("openapi.yaml").write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    monkeypatch.setattr(
        architect_cli,
        "load_openapi_document_at_ref",
        lambda project_root, base_ref, spec_path: {
            "openapi": "3.1.0",
            "paths": {"/legacy": {"delete": {"operationId": "deleteLegacy"}}},
        },
    )
    monkeypatch.setattr(
        architect_cli,
        "load_openapi_document",
        lambda path: {"openapi": "3.1.0", "paths": {}},
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new", "--changed-from", "HEAD"])

    assert result.exit_code == 0
    assert "No current OpenAPI operation changes require generation from HEAD." in result.output
    assert "Removed OpenAPI operations require manual review: deleteLegacy" in result.output
    assert not Path("tests/generated").exists()


def test_architect_build_new_refuses_symlinked_generated_parent(
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
    outside_dir = tmp_path / "outside-generated"
    outside_dir.mkdir()
    Path("tests").mkdir()
    Path("tests/generated").symlink_to(outside_dir, target_is_directory=True)

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 1
    assert "symlinked generated Hurl path component" in result.output
    assert not (outside_dir / "get_health.hurl").exists()


def test_architect_build_new_validates_each_generated_file_before_write(
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
paths: {}
""".lstrip(),
        encoding="utf-8",
    )
    generated = (
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content="# entroping: source=openapi\nGET {{base_url}}/health\nHTTP 200\n",
        ),
        GeneratedHurlFile(
            relative_path="tests/generated/orders.hurl",
            content="# entroping: source=openapi\nGET {{base_url}}/orders\nHTTP 200\n",
        ),
    )
    validated: list[tuple[str, str]] = []

    monkeypatch.setattr(
        architect_cli,
        "compile_openapi_to_hurl_with_report",
        lambda document, tags, operation_ids=None: OpenApiHurlCompilationResult(
            files=generated,
            security_findings=(),
        ),
    )
    monkeypatch.setattr(
        architect_cli,
        "validate_hurl_content",
        lambda content, display_path: validated.append((content, display_path)),
        raising=False,
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 0
    assert [display_path for _, display_path in validated] == [
        "tests/generated/health.hurl",
        "tests/generated/orders.hurl",
    ]
    assert Path("tests/generated/health.hurl").is_file()
    assert Path("tests/generated/orders.hurl").is_file()


def test_architect_build_new_validation_failure_does_not_write_partial_files(
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
paths: {}
""".lstrip(),
        encoding="utf-8",
    )
    generated = (
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content="# entroping: source=openapi\nGET {{base_url}}/health\nHTTP 200\n",
        ),
        GeneratedHurlFile(
            relative_path="tests/generated/bad.hurl",
            content="# entroping: source=openapi\nGET {{base_url}}/secret\nBAD\n",
        ),
    )

    def fail_validation(content: str, display_path: str) -> None:
        if display_path == "tests/generated/bad.hurl":
            raise HurlValidationError(f"Generated Hurl failed parser validation: {display_path}")
        _ = content

    monkeypatch.setattr(
        architect_cli,
        "compile_openapi_to_hurl_with_report",
        lambda document, tags, operation_ids=None: OpenApiHurlCompilationResult(
            files=generated,
            security_findings=(),
        ),
    )
    monkeypatch.setattr(architect_cli, "validate_hurl_content", fail_validation, raising=False)

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 1
    assert "Generated Hurl failed parser validation: tests/generated/bad.hurl" in result.output
    assert "GET {{base_url}}/secret" not in result.output
    assert "BAD" not in result.output
    assert not Path("tests/generated/health.hurl").exists()
    assert not Path("tests/generated/bad.hurl").exists()


def test_architect_build_new_requires_configured_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 1
    assert "sources.spec is required" in result.output


def test_architect_build_requires_supported_generation_mode() -> None:
    result = CliRunner().invoke(app, ["architect", "build"])

    assert result.exit_code == 2
    assert "Choose a supported architect build mode" in result.output
    assert "architect build --new" in result.output
    assert 'architect build --prompt "<intent>"' in result.output
    assert 'architect build --strategy merge --prompt "<intent>"' in result.output
    assert "not built yet" not in result.output
    assert "not implemented" not in result.output


def test_architect_build_rejects_unsupported_strategy() -> None:
    result = CliRunner().invoke(app, ["architect", "build", "--strategy", "replace"])

    assert result.exit_code == 2
    assert "Unsupported architect build strategy" in result.output


def test_architect_build_rejects_changed_from_with_prompt() -> None:
    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate coverage", "--changed-from", "HEAD"],
    )

    assert result.exit_code == 2
    assert "--changed-from applies only to architect build --new" in result.output


def test_architect_build_rejects_changed_from_without_new() -> None:
    result = CliRunner().invoke(app, ["architect", "build", "--changed-from", "HEAD"])

    assert result.exit_code == 2
    assert "--changed-from requires architect build --new" in result.output


def test_architect_build_changed_from_rejects_remote_spec_before_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: https://example.test/openapi.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new", "--changed-from", "HEAD"])

    assert result.exit_code == 1
    assert "--changed-from requires a local OpenAPI sources.spec path" in result.output


def test_architect_build_prompt_writes_validated_architect_hurl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
    input_cost_per_1m_tokens_usd: 0.25
    output_cost_per_1m_tokens_usd: 1.25
    temperature: 0.1
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
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
                    "summary": "Add checkout smoke coverage",
                    "edits": [
                        {
                            "path": "tests/generated/ai_checkout.hurl",
                            "content": "POST {{base_url}}/checkout\nHTTP 201\n",
                            "rationale": "Covers generated checkout creation.",
                        }
                    ],
                    "warnings": ["Review generated assertions before committing."],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=42,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
            provider="openai",
            cost=LiteLLMCostEstimate(
                estimated_usd=0.000042,
                input_cost_per_1m_tokens_usd=0.25,
                output_cost_per_1m_tokens_usd=1.25,
            ),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage.", "--tag", "ai"],
    )

    assert result.exit_code == 0
    assert "Generated 1 Architect Hurl test" in result.output
    assert "Add checkout smoke coverage" in result.output
    assert "Review generated assertions before committing." in result.output
    assert "Provider: openai" in result.output
    assert "Estimated cost: $0.000042" in result.output
    assert packages
    _assert_builder_prompt_package(packages[0])
    _assert_ai_checkout_hurl_output()
    manifests = _agent_run_manifest_payloads()
    assert len(manifests) == 1
    _assert_builder_agent_manifest(manifests[0])


def test_architect_build_prompt_can_use_breaker_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("agents/breaker.md").write_text(
        "Generate hostile checkout Hurl tests.",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
    temperature: 0.1
  breaker:
    source: agents/breaker.md
    model: deepseek/deepseek-r1
    temperature: 0.3
gates: []
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
                    "summary": "Add hostile checkout coverage",
                    "edits": [
                        {
                            "path": "tests/generated/breaker_checkout.hurl",
                            "content": (
                                "POST {{base_url}}/checkout\n"
                                "Authorization: Bearer invalid\n"
                                "HTTP 401\n"
                            ),
                        }
                    ],
                },
            ),
            model="deepseek/deepseek-r1",
            latency_ms=42,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "build",
            "--agent",
            "breaker",
            "--prompt",
            "Generate auth bypass tests.",
            "--tag",
            "security",
        ],
    )

    assert result.exit_code == 0
    assert "Generated 1 Architect Hurl test" in result.output
    assert "Agent: breaker" in result.output
    assert packages
    assert packages[0].role == "breaker"
    assert packages[0].model == "deepseek/deepseek-r1"
    assert "Generate hostile checkout Hurl tests." in packages[0].messages[0].content
    assert "Breaker role" in packages[0].messages[1].content
    output_path = Path("tests/generated/breaker_checkout.hurl")
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: source=architect\n"
        "# entroping: tags=breaker,security\n"
        "POST {{base_url}}/checkout\n"
        "Authorization: Bearer invalid\n"
        "HTTP 401\n"
    )
    manifests = _agent_run_manifest_payloads()
    assert len(manifests) == 1
    assert manifests[0]["command"] == "architect build"
    assert manifests[0]["mode"] == "create"
    assert manifests[0]["agent"] == "breaker"
    assert manifests[0]["model"] == "deepseek/deepseek-r1"
    assert manifests[0]["tags"] == ["security"]


def test_architect_build_prompt_rejects_auditor_agent_until_audit_mode_exists() -> None:
    result = CliRunner().invoke(
        app,
        ["architect", "build", "--agent", "auditor", "--prompt", "Review generated tests."],
    )

    assert result.exit_code == 2
    assert "Unsupported architect build agent: auditor" in result.output
    assert "supported agents: builder, breaker" in result.output


def test_architect_build_rejects_agent_without_prompt() -> None:
    result = CliRunner().invoke(app, ["architect", "build", "--new", "--agent", "breaker"])

    assert result.exit_code == 2
    assert "--agent applies only to prompt-backed architect build" in result.output


def test_architect_build_prompt_merge_preserves_manual_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/manual/checkout.hurl")
    target.parent.mkdir(parents=True)
    target.write_text(
        (
            "# manual setup stays\n"
            "# entroping: managed-begin checkout-auth\n"
            "GET {{base_url}}/checkout\n"
            "HTTP 200\n"
            "# entroping: managed-end checkout-auth\n"
            "# manual footer stays\n"
        ),
        encoding="utf-8",
    )

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = self
        assert "Merge strategy" in package.messages[1].content
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "Merged checkout auth coverage",
                    "edits": [
                        {
                            "path": "tests/manual/checkout.hurl",
                            "content": (
                                "# entroping: managed-begin checkout-auth\n"
                                "GET {{base_url}}/checkout\n"
                                "Authorization: Bearer {{token}}\n"
                                "HTTP 200\n"
                                "# entroping: managed-end checkout-auth\n"
                            ),
                        }
                    ],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=42,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "build",
            "--strategy",
            "merge",
            "--prompt",
            "Merge Authorization into checkout coverage.",
        ],
    )

    assert result.exit_code == 0
    assert "Generated 1 Architect Hurl test" in result.output
    assert "Merged checkout auth coverage" in result.output
    assert target.read_text(encoding="utf-8") == (
        "# manual setup stays\n"
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "Authorization: Bearer {{token}}\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
        "# manual footer stays\n"
    )
    manifests = _agent_run_manifest_payloads()
    assert len(manifests) == 1
    assert manifests[0]["command"] == "architect build"
    assert manifests[0]["mode"] == "merge"
    assert manifests[0]["agent"] == "builder"
    assert manifests[0]["output_paths"] == ["tests/manual/checkout.hurl"]


def test_architect_build_prompt_rejects_missing_builder_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    provider_called = False

    def fake_complete(self: object, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
        nonlocal provider_called
        _ = (self, package)
        provider_called = True
        raise AssertionError("provider should not be called")

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 1
    assert "No agent config found for role builder" in result.output
    assert provider_called is False


def test_architect_build_prompt_rejects_missing_persona_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/missing.md
    model: openai/gpt-4.1-mini
gates: []
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

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 1
    assert "Agent persona file not found" in result.output
    assert provider_called is False


def test_architect_build_prompt_rejects_invalid_provider_output_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content="not-json",
            model="openai/gpt-4.1-mini",
            latency_ms=1,
            usage=LiteLLMUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 1
    assert "Architect output must be a valid JSON object" in result.output
    assert "Architect output validation failed before write." in result.output
    assert "Expected JSON object with summary, optional warnings, and edits[]." in result.output
    assert "Retry guidance: return only the Architect JSON object" in result.output
    assert "Do not wrap the response in Markdown fences" in result.output
    assert "No Architect files were written." in result.output
    assert not Path("tests/generated/ai_checkout.hurl").exists()


def test_architect_build_prompt_rejects_invalid_hurl_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
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
                    "summary": "Generated invalid Hurl",
                    "edits": [
                        {
                            "path": "tests/generated/bad.hurl",
                            "content": "GET {{base_url}}/bad\nBAD\n",
                        }
                    ],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=1,
            usage=LiteLLMUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        )

    def fail_validation(content: str, display_path: str) -> None:
        _ = content
        raise HurlValidationError(f"Generated Hurl failed parser validation: {display_path}")

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)
    monkeypatch.setattr("entroping.brain.architect_build.validate_hurl_content", fail_validation)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 1
    assert "Generated Hurl failed parser validation: tests/generated/bad.hurl" in result.output
    assert "Architect Hurl validation failed before write." in result.output
    assert "Retry guidance: return syntactically valid Hurl" in result.output
    assert "Keep generated content in the selected Hurl file only" in result.output
    assert "No Architect files were written." in result.output
    assert not Path("tests/generated/bad.hurl").exists()


def test_architect_build_prompt_does_not_echo_invalid_provider_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
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
                    "summary": "invalid output",
                    "edits": [
                        {
                            "path": "tests/generated/leak.hurl",
                            "content": (
                                "GET {{base_url}}/health\n# provider-private-context\n\u0000"
                            ),
                        }
                    ],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=1,
            usage=LiteLLMUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 1
    assert "contain control characters" in result.output
    assert "provider-private-context" not in result.output
    assert not Path("tests/generated/leak.hurl").exists()


def test_architect_build_prompt_redacts_untrusted_provider_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
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
                    "summary": "Generated with sk-proj-live-secret",
                    "edits": [
                        {
                            "path": "tests/generated/redacted.hurl",
                            "content": "GET {{base_url}}/health\nHTTP 200\n",
                        }
                    ],
                    "warnings": ["Provider warning mentioned sk-proj-live-secret"],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=1,
            usage=LiteLLMUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 0
    assert "sk-proj-live-secret" not in result.output
    assert "[REDACTED]" in result.output


def test_architect_build_prompt_redacts_provider_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Build minimal checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    def fake_complete(self: object, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
        _ = (self, package)
        raise BrainProviderError("provider rejected sk-proj-live-secret")

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--prompt", "Generate checkout smoke coverage."],
    )

    assert result.exit_code == 1
    assert "sk-proj-live-secret" not in result.output
    assert "[REDACTED]" in result.output
    assert not Path("tests").exists()


def test_architect_refactor_updates_architect_owned_hurl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_refactor_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/generated/checkout.hurl")
    target.parent.mkdir(parents=True)
    target.write_text(
        "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n",
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
                    "summary": "Added auth header",
                    "edits": [
                        {
                            "path": "tests/generated/checkout.hurl",
                            "content": (
                                "# entroping: source=architect\n"
                                "GET {{base_url}}/checkout\n"
                                "Authorization: Bearer {{token}}\n"
                                "HTTP 200\n"
                            ),
                        }
                    ],
                    "warnings": ["Review token fixture."],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=9,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "Add Authorization header.",
        ],
    )

    assert result.exit_code == 0
    assert "Refactored 1 Architect Hurl test" in result.output
    assert "Added auth header" in result.output
    assert "Review token fixture." in result.output
    assert "Wrote Hurl test: tests/generated/checkout.hurl" in result.output
    assert packages
    assert "Add Authorization header." in packages[0].messages[1].content
    assert "## tests/generated/checkout.hurl" in packages[0].messages[1].content
    assert "Authorization: Bearer {{token}}" in target.read_text(encoding="utf-8")


def test_architect_refactor_preview_prints_diff_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_refactor_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/generated/checkout.hurl")
    target.parent.mkdir(parents=True)
    original = "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n"
    target.write_text(original, encoding="utf-8")

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "Previewed auth header",
                    "edits": [
                        {
                            "path": "tests/generated/checkout.hurl",
                            "content": (
                                "# entroping: source=architect\n"
                                "GET {{base_url}}/checkout\n"
                                "Authorization: Bearer {{token}}\n"
                                "X-Debug-Key: sk-live-secret\n"
                                "HTTP 200\n"
                            ),
                        }
                    ],
                    "warnings": ["Review before applying."],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=9,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "Add Authorization header.",
            "--preview",
        ],
    )

    assert result.exit_code == 0
    assert "Previewed 1 Architect Hurl test" in result.output
    assert "Review before applying." in result.output
    assert "Preview diff:" in result.output
    assert "--- a/tests/generated/checkout.hurl" in result.output
    assert "+++ b/tests/generated/checkout.hurl" in result.output
    assert "+Authorization: Bearer {{token}}" in result.output
    assert "sk-live-secret" not in result.output
    assert "[REDACTED]" in result.output
    assert "Wrote Hurl test:" not in result.output
    assert target.read_text(encoding="utf-8") == original


def test_architect_refactor_preview_reports_no_textual_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_refactor_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/generated/checkout.hurl")
    target.parent.mkdir(parents=True)
    original = "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n"
    target.write_text(original, encoding="utf-8")

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "No changes needed",
                    "edits": [
                        {
                            "path": "tests/generated/checkout.hurl",
                            "content": original,
                        }
                    ],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=9,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "No-op.",
            "--preview",
        ],
    )

    assert result.exit_code == 0
    assert "Previewed 1 Architect Hurl test" in result.output
    assert "(no textual diff)" in result.output
    assert target.read_text(encoding="utf-8") == original


def test_architect_refactor_preserves_manual_content_outside_managed_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_architect_refactor_hurl_validation(monkeypatch)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/manual/checkout.hurl")
    target.parent.mkdir(parents=True)
    target.write_text(
        (
            "# manual setup stays\n"
            "GET {{base_url}}/health\n"
            "HTTP 200\n"
            "\n"
            "# entroping: managed-begin checkout-auth\n"
            "GET {{base_url}}/checkout\n"
            "HTTP 200\n"
            "# entroping: managed-end checkout-auth\n"
            "\n"
            "# manual footer stays\n"
        ),
        encoding="utf-8",
    )

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = self
        assert "Managed-block manual target" in package.messages[1].content
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "Added managed auth header",
                    "edits": [
                        {
                            "path": "tests/manual/checkout.hurl",
                            "content": (
                                "# entroping: managed-begin checkout-auth\n"
                                "GET {{base_url}}/checkout\n"
                                "Authorization: Bearer {{token}}\n"
                                "HTTP 200\n"
                                "# entroping: managed-end checkout-auth\n"
                            ),
                        }
                    ],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=9,
            usage=LiteLLMUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/manual/*.hurl",
            "--prompt",
            "Add Authorization header.",
        ],
    )

    assert result.exit_code == 0
    assert "Refactored 1 Architect Hurl test" in result.output
    assert "Added managed auth header" in result.output
    assert "Wrote Hurl test: tests/manual/checkout.hurl" in result.output
    assert target.read_text(encoding="utf-8") == (
        "# manual setup stays\n"
        "GET {{base_url}}/health\n"
        "HTTP 200\n"
        "\n"
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "Authorization: Bearer {{token}}\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
        "\n"
        "# manual footer stays\n"
    )


def test_architect_refactor_rejects_missing_targets_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
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

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "Add Authorization header.",
        ],
    )

    assert result.exit_code == 1
    assert "No Hurl targets matched" in result.output
    assert provider_called is False


def test_architect_refactor_redacts_provider_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/generated/checkout.hurl")
    target.parent.mkdir(parents=True)
    target.write_text(
        "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )

    def fake_complete(self: object, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
        _ = (self, package)
        raise BrainProviderError("provider rejected sk-proj-live-secret")

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "Add Authorization header.",
        ],
    )

    assert result.exit_code == 1
    assert "sk-proj-live-secret" not in result.output
    assert "[REDACTED]" in result.output
    assert "Authorization" not in target.read_text(encoding="utf-8")


def test_architect_refactor_preview_rejects_invalid_provider_json_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/generated/checkout.hurl")
    target.parent.mkdir(parents=True)
    original = "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n"
    target.write_text(original, encoding="utf-8")

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content="not-json sk-proj-live-secret",
            model="openai/gpt-4.1-mini",
            latency_ms=9,
            usage=LiteLLMUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "Add Authorization header.",
            "--preview",
        ],
    )

    assert result.exit_code == 1
    assert "Architect output validation failed before write." in result.output
    assert "sk-proj-live-secret" not in result.output
    assert target.read_text(encoding="utf-8") == original


def test_architect_refactor_preview_rejects_parser_invalid_hurl_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("agents").mkdir()
    Path("agents/builder.md").write_text("Refactor checkout Hurl tests.", encoding="utf-8")
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    target = Path("tests/generated/checkout.hurl")
    target.parent.mkdir(parents=True)
    original = "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n"
    target.write_text(original, encoding="utf-8")

    def reject_hurl(content: str, display_path: str) -> None:
        _ = content
        raise HurlValidationError(
            f"Generated Hurl failed parser validation: {display_path} sk-live-secret"
        )

    def fake_complete(
        self: object,
        package: ArchitectPromptPackage,
    ) -> LiteLLMCompletionResult:
        _ = (self, package)
        return LiteLLMCompletionResult(
            content=json.dumps(
                {
                    "summary": "Invalid preview",
                    "edits": [
                        {
                            "path": "tests/generated/checkout.hurl",
                            "content": "# entroping: source=architect\nNOT HURL\n",
                        }
                    ],
                },
            ),
            model="openai/gpt-4.1-mini",
            latency_ms=9,
            usage=LiteLLMUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

    monkeypatch.setattr("entroping.brain.architect_refactor.validate_hurl_content", reject_hurl)
    monkeypatch.setattr("entroping.brain.litellm_client.LiteLLMClient.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/generated/*.hurl",
            "--prompt",
            "Add Authorization header.",
            "--preview",
        ],
    )

    assert result.exit_code == 1
    assert "Architect Hurl validation failed before write." in result.output
    assert "sk-live-secret" not in result.output
    assert "[REDACTED]" in result.output
    assert target.read_text(encoding="utf-8") == original


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
        },
        {
            "operation_id": "createCheckout",
            "method": "POST",
            "path": "/checkout",
            "status": "uncovered",
            "tests": [],
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


def test_architect_build_merge_strategy_requires_prompt_for_now() -> None:
    result = CliRunner().invoke(app, ["architect", "build", "--new", "--strategy", "merge"])

    assert result.exit_code == 2
    assert "--strategy merge requires --prompt" in result.output


def test_cli_helper_normalizes_supported_audit_focus() -> None:
    assert architect_cli._normalize_architect_audit_focus(" LoGiC ") == "logic"


def test_cli_helper_normalizes_supported_architect_build_agent() -> None:
    assert architect_cli._normalize_architect_build_agent(" BUILDER ") == "builder"
    assert architect_cli._normalize_architect_build_agent(" BrEaKeR ") == "breaker"


def test_configured_spec_reference_preserves_remote_and_absolute_paths(tmp_path: Path) -> None:
    remote = architect_cli._configured_spec_reference("https://example.test/openapi.yaml")
    absolute = architect_cli._configured_spec_reference(str(tmp_path / "openapi.yaml"))

    assert remote == "https://example.test/openapi.yaml"
    assert absolute == tmp_path / "openapi.yaml"


def test_write_generated_hurl_file_writes_openapi_generated_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    output_path = architect_cli._write_generated_hurl_file(
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
        )
    )

    assert output_path == (tmp_path / "tests" / "generated" / "health.hurl")
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: source=openapi\nGET /health\nHTTP 200\n"
    )


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("../escape.hurl", "must stay inside the project"),
        ("tests/manual/checkout.hurl", "must stay under tests/generated"),
    ],
)
def test_write_generated_hurl_file_rejects_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=message):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path=relative_path,
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_write_generated_hurl_file_rejects_symlinked_output_after_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "tests" / "generated" / "health.hurl"

    def allow_symlink_components(path: Path, *, root: Path) -> None:
        _ = path, root

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self: Path) -> bool:
        if self == output_path:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(architect_cli, "_reject_symlink_path_components", allow_symlink_components)
    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="symlinked generated Hurl file"):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_write_generated_hurl_file_rejects_existing_non_openapi_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    target.write_text("# manual\nGET /health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(ValueError, match="non-OpenAPI Hurl file"):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )
