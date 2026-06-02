"""CLI adapter tests for config commands."""

from cli_test_support import (
    CliRunner,
    Path,
    app,
    pytest,
    yaml,
)


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
    api_base: http://127.0.0.1:8000/v1
    api_key_env: ENTROPING_OMLX_API_KEY
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
    assert "api_base: http://127.0.0.1:8000/v1" in result.output
    assert "api_key_env: ENTROPING_OMLX_API_KEY" in result.output
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
