import hashlib

from cli_architect_test_helpers import (
    _agent_run_manifest_payloads,
)
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
    _accept_openapi_hurl_validation,
    app,
    architect_cli,
    json,
    pytest,
    subprocess,
)


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
    assert manifest["source_evidence"] == [
        {
            "kind": "explicit_prompt",
            "reference": "prompt_intent",
            "sha256": hashlib.sha256(
                b"Generate checkout smoke coverage."
            ).hexdigest(),
        }
    ]
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


def test_architect_build_new_writes_validated_schema_negative_corpus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    validated_paths: list[str] = []
    monkeypatch.setattr(
        architect_cli,
        "validate_hurl_content",
        lambda content, display_path: validated_paths.append(display_path),
        raising=False,
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
  /checkouts:
    post:
      operationId: createCheckout
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - email
              properties:
                email:
                  type: string
                  minLength: 3
                coupon:
                  type: string
      responses:
        "201":
          description: created
        "422":
          description: validation failed
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new", "--tag", "checkout"])

    assert result.exit_code == 0
    assert "Generated 5 Hurl tests" in result.output
    assert validated_paths == [
        "tests/generated/create_checkout.hurl",
        "tests/generated/negative/create_checkout_malformed_json.hurl",
        "tests/generated/negative/create_checkout_schema_violations.hurl",
        "tests/generated/negative/create_checkout_boundary_values.hurl",
        "tests/generated/negative/create_checkout_sqli_like_strings.hurl",
    ]
    boundary = Path("tests/generated/negative/create_checkout_boundary_values.hurl")
    sqli = Path("tests/generated/negative/create_checkout_sqli_like_strings.hurl")
    assert boundary.is_file()
    assert sqli.is_file()
    boundary_content = boundary.read_text(encoding="utf-8")
    assert "# entroping: negative_category=boundary-values" in boundary_content
    assert "# entroping: safety=destructive" in boundary_content
    assert "HTTP 422" in boundary_content
    assert "# entroping: severity=high" in sqli.read_text(encoding="utf-8")


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
components:
  parameters:
    OrderId:
      name: order_id
      in: path
      required: true
      schema:
        type: string
    Include:
      name: include
      in: query
      schema:
        type: string
        enum:
          - events
    Labels:
      name: labels
      in: query
      schema:
        type: array
        items:
          type: string
        default:
          - rush
          - vip
paths:
  /orders/{order_id}:
    get:
      operationId: getOrder
      parameters:
        - $ref: "#/components/parameters/OrderId"
        - $ref: "#/components/parameters/Include"
        - $ref: "#/components/parameters/Labels"
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new", "--tag", "orders"])

    assert result.exit_code == 0
    content = Path("tests/generated/get_order.hurl").read_text(encoding="utf-8")
    assert "GET {{base_url}}/orders/{{order_id}}?include=events&labels=rush&labels=vip" in content


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
        lambda path, root=None: {"openapi": "3.1.0", "paths": {}},
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
    assert "architect build --target-url <url>" in result.output
    assert 'architect build --prompt "<intent>"' in result.output
    assert 'architect build --strategy merge --prompt "<intent>"' in result.output
    assert "not built yet" not in result.output
    assert "not implemented" not in result.output


def test_architect_build_target_url_generates_single_smoke_scaffold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _accept_openapi_hurl_validation(monkeypatch)

    result = CliRunner().invoke(
        app,
        ["architect", "build", "--target-url", "https://api.example.test/health?ready=true"],
    )

    assert result.exit_code == 0
    assert "Generated 1 Hurl test" in result.output
    generated = Path("tests/generated/target-api-example-test-health.hurl")
    assert generated.is_file()
    assert generated.read_text(encoding="utf-8") == (
        "# entroping: tags=target,smoke\n"
        "# entroping: source=target-url\n"
        "# entroping: target_origin=https://api.example.test\n"
        "\n"
        "GET https://api.example.test/health?ready=true\n"
        "HTTP 200\n"
    )


def test_architect_build_target_url_rejects_unsafe_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        ["architect", "build", "--target-url", "ftp://api.example.test/health"],
    )

    assert result.exit_code == 1
    assert "target URL scheme must be http or https" in result.output
    assert not (tmp_path / "tests" / "generated").exists()


def test_architect_build_target_url_rejects_other_mode_flags() -> None:
    result = CliRunner().invoke(
        app,
        [
            "architect",
            "build",
            "--target-url",
            "https://api.example.test/health",
            "--prompt",
            "Generate coverage",
        ],
    )

    assert result.exit_code == 2
    assert "incompatible with other architect build mode flags" in result.output


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


def test_architect_build_new_rejects_sources_spec_root_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    (tmp_path / "outside.yaml").write_text(
        "openapi: '3.1.0'\npaths: {}\n",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: ../outside.yaml
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 1
    assert "OpenAPI spec must be inside project root" in result.output


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
    assert manifests[0]["source_evidence"] == [
        {
            "kind": "explicit_prompt",
            "reference": "prompt_intent",
            "sha256": hashlib.sha256(
                b"Merge Authorization into checkout coverage."
            ).hexdigest(),
        }
    ]


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
