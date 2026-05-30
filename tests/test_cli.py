"""CLI smoke tests for the initial scaffold."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO
from xml.etree import ElementTree

import pytest
import yaml
from typer.testing import CliRunner

import entroping.cli.main as cli_main
from entroping.brain.litellm_client import BrainProviderError, LiteLLMCompletionResult, LiteLLMUsage
from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.bridge.openapi_to_hurl import GeneratedHurlFile
from entroping.cli.main import app
from entroping.core.hurl_runner import HurlFileResult, HurlRunOptions, HurlSuiteResult
from entroping.core.hurl_validator import HurlValidationError
from entroping.core.report_writer import ReportWriterError, write_json_report
from entroping.core.run_workflow import NoHurlTestsMatchedError
from entroping.core.traffic_proxy import MitmproxyUnavailableError, WatchConfig
from entroping.models.report import RunReport, RunReportSummary, RunTestReport
from entroping.studio.status import StudioDependencyError


def _accept_architect_hurl_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "entroping.brain.architect_build.validate_hurl_content",
        lambda content, display_path: None,
    )


def _accept_architect_refactor_hurl_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "entroping.brain.architect_refactor.validate_hurl_content",
        lambda content, display_path: None,
    )


def _record_freeze_exchange(tmp_path: Path, *, secret: str = "freeze-secret") -> None:
    from datetime import UTC, datetime

    from entroping.core.traffic_redactor import redact_traffic_exchange
    from entroping.core.traffic_store import TrafficStore
    from entroping.models.traffic import (
        TrafficBody,
        TrafficExchange,
        TrafficRequest,
        TrafficResponse,
    )

    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=44,
                text=f'{{"cart_id":"cart-1","password":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=43,
                text='{"id":"ord_123","status":"accepted"}',
            ),
        ),
    )
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(exchange))


def _record_mock_exchange(tmp_path: Path, *, secret: str = "mock-secret") -> None:
    from datetime import UTC, datetime

    from entroping.core.traffic_redactor import redact_traffic_exchange
    from entroping.core.traffic_store import TrafficStore
    from entroping.models.traffic import (
        TrafficBody,
        TrafficExchange,
        TrafficRequest,
        TrafficResponse,
    )

    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 1, tzinfo=UTC),
        duration_ms=40,
        request=TrafficRequest(
            method="POST",
            url=f"https://payments.example.test/charge?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=34,
                text=f'{{"card_token":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": f"session={secret}",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=43,
                text=f'{{"approved":true,"token":"{secret}"}}',
            ),
        ),
    )
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(exchange))


def test_root_help_includes_locked_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "architect" in result.output
    assert "doctor" in result.output
    assert "run" in result.output


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "entroping 0.1.0" in result.output


def test_init_minimal_creates_safe_runtime_skeleton(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--minimal"])

    assert result.exit_code == 0
    assert Path("qanstitution.yaml").is_file()
    assert Path("tests").is_dir()
    assert Path("envs").is_dir()
    assert Path(".entroping").is_dir()
    assert not Path("agents").exists()
    assert not Path("reports").exists()
    assert "global_latency" in Path("qanstitution.yaml").read_text(encoding="utf-8")


def test_init_creates_standard_runtime_skeleton(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert Path("qanstitution.yaml").is_file()
    assert Path("tests").is_dir()
    assert Path("envs").is_dir()
    assert Path("rules").is_dir()
    assert Path("agents").is_dir()
    assert Path("reports").is_dir()
    assert Path(".entroping").is_dir()


def test_init_preserves_existing_qanstitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    existing = Path("qanstitution.yaml")
    existing.write_text("project: existing\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--minimal"])

    assert result.exit_code == 0
    assert existing.read_text(encoding="utf-8") == "project: existing\n"
    assert "already exists" in result.output


def test_doctor_reports_valid_config_health(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_main,
        "discover_hurl",
        lambda: SimpleNamespace(available=True, path="/usr/local/bin/hurl"),
    )

    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Python:" in result.output
    assert "Hurl:" in result.output
    assert "found" in result.output
    assert "QAnstitution: valid" in result.output


def test_doctor_fails_with_actionable_invalid_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
gates:
  - id: bad_condition
    condition: tags includes 'smoke'
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "QAnstitution: invalid" in result.output
    assert "Unsupported QAnstitution condition syntax" in result.output


def test_doctor_reports_missing_hurl_and_missing_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli_main,
        "discover_hurl",
        lambda: SimpleNamespace(available=False, path=None),
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Hurl:" in result.output
    assert "not found" in result.output
    assert "QAnstitution:" in result.output
    assert "run entroping init --minimal" in result.output


def test_config_list_prints_resolved_non_secret_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("rules").mkdir()
    Path("rules/platform.yaml").write_text(
        """
project: platform
gates:
  - id: platform_status
    condition: "true"
    gate: status == 200
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
version: "4.1"
description: Checkout governance
sources:
  spec: ./openapi.yaml
  stories: ./stories
  traffic: .entroping/state.db
  graph: reports/dependency-map.md
  types: ./types
imports:
  - rules/platform.yaml
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
    temperature: 0.2
    max_tokens: 2048
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
settings:
  timeout: 45000
  parallel_workers: 3
  follow_redirects: false
  retry: 1
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["config", "list"])

    assert result.exit_code == 0
    assert "Project: checkout-api" in result.output
    assert "Version: 4.1" in result.output
    assert "Description: Checkout governance" in result.output
    assert "Spec: ./openapi.yaml" in result.output
    assert "Stories: ./stories" in result.output
    assert "Traffic: .entroping/state.db" in result.output
    assert "Graph: reports/dependency-map.md" in result.output
    assert "Types: ./types" in result.output
    assert "Imports: 1" in result.output
    assert "Gates: 2" in result.output
    assert "builder" in result.output
    assert "openai/gpt-4.1-mini" in result.output
    assert "agents/builder.md" in result.output
    assert "max_tokens: 2048" in result.output
    assert "timeout: 45000" in result.output
    assert "parallel_workers: 3" in result.output
    assert "API key" not in result.output


def test_config_list_reports_no_sources_or_agents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["config", "list"])

    assert result.exit_code == 0
    assert "Sources: none" in result.output
    assert "Agents: none" in result.output


def test_config_list_reports_invalid_qanstitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
gates:
  - id: bad_condition
    condition: tags includes 'smoke'
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["config", "list"])

    assert result.exit_code == 1
    assert "Unsupported QAnstitution condition syntax" in result.output


def test_config_set_updates_existing_agent_model_preserving_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    config_path.write_text(
        """
project: checkout-api
agents:
  auditor:
    source: personas/auditor.md
    model: old/auditor
    temperature: 0.4
    max_tokens: 4096
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["config", "set", "--agent", "auditor", "--model", "anthropic/claude-audit"],
    )

    assert result.exit_code == 0
    assert "Configured auditor model" in result.output
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert document["agents"]["auditor"] == {
        "source": "personas/auditor.md",
        "model": "anthropic/claude-audit",
        "temperature": 0.4,
        "max_tokens": 4096,
    }


def test_config_set_creates_missing_agent_with_default_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["config", "set", "--agent", "breaker", "--model", "deepseek/deepseek-r1"],
    )

    assert result.exit_code == 0
    assert "Created persona template: agents/breaker.md" in result.output
    assert Path("agents/breaker.md").is_file()
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert document["agents"]["breaker"] == {
        "source": "agents/breaker.md",
        "model": "deepseek/deepseek-r1",
        "temperature": 0.0,
    }


def test_config_set_rejects_secret_like_model_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    original = "project: checkout-api\ngates: []\n"
    config_path.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["config", "set", "--agent", "builder", "--model", "sk-proj-live-secret"],
    )

    assert result.exit_code != 0
    assert "model identifier must not look like a secret" in result.output
    assert config_path.read_text(encoding="utf-8") == original


def test_config_set_does_not_write_when_existing_config_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    original = "project: checkout-api\nsettings:\n  timeout: -1\ngates: []\n"
    config_path.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["config", "set", "--agent", "builder", "--model", "openai/gpt-4.1-mini"],
    )

    assert result.exit_code == 1
    assert "Invalid QAnstitution config" in result.output
    assert config_path.read_text(encoding="utf-8") == original


def test_config_set_does_not_write_when_effective_imports_are_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    original = "project: checkout-api\nimports:\n  - missing.yaml\ngates: []\n"
    config_path.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["config", "set", "--agent", "builder", "--model", "openai/gpt-4.1-mini"],
    )

    assert result.exit_code == 1
    assert "Import not found" in result.output
    assert config_path.read_text(encoding="utf-8") == original


def test_config_set_does_not_follow_predictable_temp_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    victim_path = Path("victim.txt")
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    victim_path.write_text("do not overwrite\n", encoding="utf-8")
    Path(".qanstitution.yaml.tmp").symlink_to(victim_path)

    result = CliRunner().invoke(
        app,
        ["config", "set", "--agent", "builder", "--model", "openai/gpt-4.1-mini"],
    )

    assert result.exit_code == 0
    assert victim_path.read_text(encoding="utf-8") == "do not overwrite\n"
    assert not config_path.is_symlink()
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert document["agents"]["builder"]["model"] == "openai/gpt-4.1-mini"


def test_architect_build_new_generates_hurl_from_configured_openapi(
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


def test_architect_build_new_writes_parameterized_generated_hurl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
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
    assert packages
    assert packages[0].role == "builder"
    assert packages[0].model == "openai/gpt-4.1-mini"
    assert packages[0].temperature == 0.1
    assert "Build minimal checkout Hurl tests." in packages[0].messages[0].content
    assert "global_latency" in packages[0].messages[0].content
    assert "Generate checkout smoke coverage." in packages[0].messages[1].content
    assert "Requested Entroping tags: ai" in packages[0].messages[1].content
    output_path = Path("tests/generated/ai_checkout.hurl")
    assert output_path.is_file()
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: source=architect\n"
        "# entroping: tags=ai\n"
        "POST {{base_url}}/checkout\n"
        "HTTP 201\n"
    )


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

    result = CliRunner().invoke(app, ["architect", "audit", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "fail"
    assert payload["summary"]["missing_operations"] == 1
    assert payload["findings"][0]["operation_id"] == "createCheckout"


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
    assert "No OpenAPI coverage gaps found." in result.output


def test_architect_audit_rejects_unsupported_focus() -> None:
    result = CliRunner().invoke(app, ["architect", "audit", "--focus", "security"])

    assert result.exit_code == 1
    assert "Unsupported architect audit focus" in result.output


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


def test_watch_invokes_capture_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[WatchConfig] = []

    async def fake_run_watch(config: WatchConfig) -> None:
        calls.append(config)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.main.run_watch", fake_run_watch)

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


def test_watch_prints_actionable_missing_proxy_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_run_watch(config: WatchConfig) -> None:
        _ = config
        raise MitmproxyUnavailableError("mitmproxy is required; run uv sync --extra proxy")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.main.run_watch", fail_run_watch)

    result = CliRunner().invoke(app, ["watch"])

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
    monkeypatch.setattr("entroping.cli.main.run_watch", interrupt_run_watch)

    result = CliRunner().invoke(app, ["watch"])

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
    assert result.exit_code == 0
    assert "Wrote Hurl test: tests/generated/checkout_flow.hurl" in result.output
    assert output.is_file()
    content = output.read_text(encoding="utf-8")
    assert "# entroping: source=traffic" in content
    assert "POST https://api.example.test/checkout?token=%5BREDACTED%5D" in content
    assert "Authorization: [REDACTED]" in content
    assert "live-secret" not in content
    assert 'jsonpath "$.status" == "accepted"' in content


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
    assert result.exit_code == 0
    assert "Wrote WireMock mapping: mocks/payments/refund_flow-001.json" in result.output
    assert output.is_file()
    content = output.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["request"] == {"method": "POST", "urlPath": "/charge"}
    assert payload["response"]["status"] == 201
    assert payload["response"]["headers"] == {"Content-Type": "application/json"}
    assert payload["response"]["jsonBody"]["token"] == "[REDACTED]"
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


def test_studio_missing_optional_dependency_returns_setup_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_dependency_check() -> None:
        raise StudioDependencyError("Install Studio dependencies with: uv sync --extra studio")

    monkeypatch.setattr("entroping.cli.main.ensure_studio_available", fail_dependency_check)

    result = CliRunner().invoke(app, ["studio", "--env", "local"])

    assert result.exit_code == 1
    assert "uv sync --extra studio" in result.output
    assert "not built yet" not in result.output


def test_studio_read_only_status_without_latest_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("entroping.cli.main.ensure_studio_available", lambda: None)
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
    monkeypatch.setattr("entroping.cli.main.ensure_studio_available", lambda: None)
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
    drift = json.loads(Path("reports/drift.json").read_text(encoding="utf-8"))
    assert drift["summary"]["missing_baseline"] is True
    assert drift["findings"][0]["kind"] == "missing_baseline"


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

    monkeypatch.setattr(cli_main, "execute_run_workflow", fake_execute_run_workflow)

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

    monkeypatch.setattr(cli_main, "execute_run_workflow", fake_execute_run_workflow)

    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code == 1
    assert "health.hurl: failed" in result.output
    assert "assertion failed on stdout" in result.output


def test_report_bug_generates_markdown_from_latest_failing_run(
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
        _ = (args, stdout, timeout, check, shell)
        stderr.write(b"token=live-secret\nassert failed\n")
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    run_result = runner.invoke(app, ["run", "--tag", "smoke"])
    assert run_result.exit_code == 1

    bug_result = runner.invoke(app, ["report", "bug"])

    assert bug_result.exit_code == 0
    assert "reports/bug.md" in bug_result.output
    bug = Path("reports/bug.md").read_text(encoding="utf-8")
    assert "tests/health.hurl" in bug
    assert "global_latency" in bug
    assert "live-secret" not in bug
    assert "token=[REDACTED]" in bug


def test_report_bug_returns_actionable_message_without_latest_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "Run entroping run before report bug" in result.output
    assert not (tmp_path / "reports" / "bug.md").exists()


def test_report_bug_returns_actionable_message_without_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-05-30T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="passed",
                exit_code=0,
                duration_ms=10,
                rule_ids=(),
                stdout="",
                stderr="",
            ),
        ),
    )
    write_json_report(report, latest_state)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "no failures to report" in result.output


def test_report_bug_wraps_writer_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-05-30T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="failed",
                exit_code=1,
                duration_ms=10,
                rule_ids=("global_latency",),
                stdout="",
                stderr="assert failed",
            ),
        ),
    )
    write_json_report(report, latest_state)

    def fail_write_bug_report(report: RunReport, path: Path) -> Path:
        _ = report, path
        raise ReportWriterError("could not write bug")

    monkeypatch.setattr(cli_main, "write_bug_report", fail_write_bug_report)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "could not write bug" in result.output


def test_run_rejects_unsupported_report_format() -> None:
    result = CliRunner().invoke(app, ["run", "--report", "xml"])

    assert result.exit_code == 2
    assert "Unsupported report format" in result.output


def test_run_rejects_empty_tag_filter() -> None:
    result = CliRunner().invoke(app, ["run", "--tag", ""])

    assert result.exit_code == 2
    assert "Tag filters must not be empty" in result.output


def test_cli_helper_normalizes_supported_audit_focus() -> None:
    assert cli_main._normalize_architect_audit_focus(" LoGiC ") == "logic"


def test_configured_spec_reference_preserves_remote_and_absolute_paths(tmp_path: Path) -> None:
    remote = cli_main._configured_spec_reference("https://example.test/openapi.yaml")
    absolute = cli_main._configured_spec_reference(str(tmp_path / "openapi.yaml"))

    assert remote == "https://example.test/openapi.yaml"
    assert absolute == tmp_path / "openapi.yaml"


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
        cli_main._write_generated_hurl_file(
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

    monkeypatch.setattr(cli_main, "_reject_symlink_path_components", allow_symlink_components)
    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="symlinked generated Hurl file"):
        cli_main._write_generated_hurl_file(
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
        cli_main._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_display_cli_path_returns_absolute_path_outside_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"

    assert cli_main._display_cli_path(outside) == str(outside)
