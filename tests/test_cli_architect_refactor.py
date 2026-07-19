from cli_test_support import (
    ArchitectPromptPackage,
    BrainProviderError,
    CliRunner,
    HurlValidationError,
    LiteLLMCompletionResult,
    LiteLLMUsage,
    Path,
    _accept_architect_refactor_hurl_validation,
    app,
    json,
    pytest,
)


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
