"""CLI adapter tests for config commands."""

from cli_test_support import (
    CliRunner,
    Path,
    app,
    json,
    pytest,
    yaml,
)


def _write_cli_policy_pack(pack_path: Path) -> None:
    (pack_path / "rules").mkdir(parents=True)
    (pack_path / "examples").mkdir()
    (pack_path / "README.md").write_text("# Source Pack\n", encoding="utf-8")
    (pack_path / "entroping-policy-pack.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "acme.strict-api",
                "name": "Acme Strict API",
                "version": "0.2.0",
                "license": "Apache-2.0",
                "source": ".",
                "entrypoint": "qanstitution.yaml",
                "runtime_contract": "qanstitution-import",
                "entroping": ">=0.1.1-alpha,<1.0",
                "evidence_command": "entroping config test-policy-pack --pack .",
                "gate_prefixes": ["acme-security"],
                "final_gates": ["acme-security.request_id"],
                "gates": [
                    {
                        "id": "acme-security.request_id",
                        "file": "rules/security.yaml",
                        "final": True,
                    }
                ],
                "maintainers": ["Acme QA"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (pack_path / "qanstitution.yaml").write_text(
        "project: pack\nimports:\n  - ./rules/security.yaml\ngates: []\n",
        encoding="utf-8",
    )
    (pack_path / "rules" / "security.yaml").write_text(
        """
project: pack-rules
gates:
  - id: acme-security.request_id
    condition: "true"
    gate: 'header "X-Request-Id" exists'
    enforcement: warn
    final: true
""".lstrip(),
        encoding="utf-8",
    )
    (pack_path / "examples" / "consumer-qanstitution.yaml").write_text(
        (
            "project: consumer\n"
            "imports:\n"
            "  - ./policy-packs/source-pack/qanstitution.yaml\n"
            "gates: []\n"
        ),
        encoding="utf-8",
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


def test_config_vendor_policy_pack_copies_pack_and_updates_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("qanstitution.yaml")
    config_path.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    pack_path = tmp_path / "source-pack"
    (pack_path / "rules").mkdir(parents=True)
    (pack_path / "examples").mkdir()
    (pack_path / "README.md").write_text("# Source Pack\n", encoding="utf-8")
    (pack_path / "entroping-policy-pack.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "acme.strict-api",
                "name": "Acme Strict API",
                "version": "0.2.0",
                "license": "Apache-2.0",
                "source": ".",
                "entrypoint": "qanstitution.yaml",
                "runtime_contract": "qanstitution-import",
                "entroping": ">=0.1.1-alpha,<1.0",
                "evidence_command": "uv run python scripts/policy_pack_smoke.py --strict",
                "gate_prefixes": ["acme-security"],
                "final_gates": ["acme-security.request_id"],
                "gates": [
                    {
                        "id": "acme-security.request_id",
                        "file": "rules/security.yaml",
                        "final": True,
                    }
                ],
                "maintainers": ["Acme QA"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (pack_path / "qanstitution.yaml").write_text(
        "project: pack\nimports:\n  - ./rules/security.yaml\ngates: []\n",
        encoding="utf-8",
    )
    (pack_path / "rules" / "security.yaml").write_text(
        """
project: pack-rules
gates:
  - id: acme-security.request_id
    condition: "true"
    gate: 'header "X-Request-Id" exists'
    enforcement: warn
    final: true
""".lstrip(),
        encoding="utf-8",
    )
    (pack_path / "examples" / "consumer-qanstitution.yaml").write_text(
        (
            "project: consumer\n"
            "imports:\n"
            "  - ./policy-packs/acme/qanstitution.yaml\n"
            "gates: []\n"
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["config", "vendor-policy-pack", "--pack", str(pack_path), "--name", "acme"],
    )

    assert result.exit_code == 0
    assert "Vendored policy pack acme.strict-api" in result.output
    assert "policy-packs/acme/qanstitution.yaml" in result.output
    assert "Final gates: acme-security.request_id" in result.output
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert document["imports"] == ["./policy-packs/acme/qanstitution.yaml"]
    assert Path("policy-packs/acme/rules/security.yaml").is_file()


def test_config_test_policy_pack_json_reports_pass_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pack_path = tmp_path / "source-pack"
    _write_cli_policy_pack(pack_path)

    result = CliRunner().invoke(
        app,
        ["config", "test-policy-pack", "--pack", str(pack_path), "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.policy-pack-self-test.v1"
    assert payload["artifact_type"] == "policy-pack-verification"
    assert payload["status"] == "pass"
    assert payload["pack_id"] == "acme.strict-api"
    assert payload["gate_ids"] == ["acme-security.request_id"]
    assert [check["status"] for check in payload["checks"]] == ["pass", "pass", "pass", "pass"]
    assert not Path("policy-packs").exists()
    assert not Path("qanstitution.yaml").exists()


def test_config_test_policy_pack_text_reports_pass_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pack_path = tmp_path / "source-pack"
    _write_cli_policy_pack(pack_path)

    result = CliRunner().invoke(app, ["config", "test-policy-pack", "--pack", str(pack_path)])

    assert result.exit_code == 0
    assert "Policy pack self-test passed" in result.output
    assert "Pack: acme.strict-api" in result.output
    assert "Gates: 1 gate" in result.output
    assert "Final gates: acme-security.request_id" in result.output
    assert "PASS local-only" in result.output
    assert not Path("policy-packs").exists()
    assert not Path("qanstitution.yaml").exists()


def test_config_test_policy_pack_rejects_unknown_output_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pack_path = tmp_path / "source-pack"
    _write_cli_policy_pack(pack_path)

    result = CliRunner().invoke(
        app,
        ["config", "test-policy-pack", "--pack", str(pack_path), "--output", "xml"],
    )

    assert result.exit_code == 1
    assert "Unsupported policy-pack self-test output: xml" in result.output
    assert not Path("policy-packs").exists()
    assert not Path("qanstitution.yaml").exists()


def test_config_test_policy_pack_text_reports_fail_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pack_path = tmp_path / "broken-pack"
    pack_path.mkdir()

    result = CliRunner().invoke(app, ["config", "test-policy-pack", "--pack", str(pack_path)])

    assert result.exit_code == 1
    assert "Policy pack self-test failed" in result.output
    assert "PASS source-boundary" in result.output
    assert "FAIL manifest-entrypoint-gates" in result.output
    assert "manifest file missing" in result.output
    assert not Path("policy-packs").exists()
    assert not Path("qanstitution.yaml").exists()


def test_config_vendor_policy_pack_wraps_validation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    pack_path = tmp_path / "broken-pack"
    pack_path.mkdir()

    result = CliRunner().invoke(app, ["config", "vendor-policy-pack", "--pack", str(pack_path)])

    assert result.exit_code == 1
    assert "manifest file missing" in result.output
    assert not Path("policy-packs").exists()


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
