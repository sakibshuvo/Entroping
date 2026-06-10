"""CLI adapter tests for root, init, and doctor commands."""

from cli_test_support import (
    CliRunner,
    Path,
    SimpleNamespace,
    _record_freeze_exchange,
    app,
    cli_main,
    json,
    project_cli,
    pytest,
    yaml,
)


def _fake_hurl_status(
    *,
    available: bool = True,
    path: str | None = "/usr/local/bin/hurl",
    version: str | None = "8.0.1",
    version_parts: tuple[int, int, int] | None = (8, 0, 1),
    version_checked: bool = True,
    version_output: str | None = "hurl 8.0.1",
    version_error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        available=available,
        path=path,
        version=version,
        version_parts=version_parts,
        version_checked=version_checked,
        version_output=version_output,
        version_error=version_error,
    )


def test_root_help_includes_locked_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "architect" in result.output
    assert "doctor" in result.output
    assert "run" in result.output


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "entroping 0.1.1" in result.output


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


def test_init_minimal_policy_starts_with_first_hour_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--minimal"])

    assert result.exit_code == 0
    policy = yaml.safe_load(Path("qanstitution.yaml").read_text(encoding="utf-8"))
    gates = policy["gates"]
    assert [gate["id"] for gate in gates] == [
        "no_server_errors",
        "global_latency",
        "request_id_header",
    ]
    assert [gate["gate"] for gate in gates] == [
        "status < 500",
        "duration < 2000",
        'header "X-Request-Id" exists',
    ]
    assert gates[0]["enforcement"] == "block"
    assert gates[1]["enforcement"] == "block"
    assert gates[2]["enforcement"] == "warn"


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


def test_init_minimal_can_install_github_actions_starter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--minimal", "--github-actions"])

    assert result.exit_code == 0
    assert Path("qanstitution.yaml").is_file()
    assert Path("tests").is_dir()
    assert Path("envs").is_dir()
    assert Path(".entroping").is_dir()
    assert not Path("reports").exists()
    workflow = Path(".github/workflows/entroping.yml")
    assert workflow.is_file()
    assert "HURL_SHA256" in workflow.read_text(encoding="utf-8")
    assert "Installed GitHub Actions starter workflow" in result.output


def test_init_full_can_install_github_actions_starter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--github-actions"])

    assert result.exit_code == 0
    assert Path("reports").is_dir()
    assert Path(".github/workflows/entroping.yml").is_file()


def test_init_github_actions_refuses_existing_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    workflow = Path(".github/workflows/entroping.yml")
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: existing\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--github-actions"])

    assert result.exit_code == 1
    assert "already exists" in result.output
    assert workflow.read_text(encoding="utf-8") == "name: existing\n"


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

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        path = f"/usr/local/bin/{binary}"
        return SimpleNamespace(available=True, path=path)

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)

    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Python:" in result.output
    assert "Hurl: found at /usr/local/bin/hurl" in result.output
    assert "Hurl parser: found at /usr/local/bin/hurlfmt" in result.output
    assert "found" in result.output
    assert "QAnstitution: valid" in result.output


def test_doctor_reports_compatible_hurl_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return _fake_hurl_status(version="8.0.1", version_parts=(8, 0, 1))
        return _fake_hurl_status(
            path="/usr/local/bin/hurlfmt",
            version_checked=False,
            version=None,
            version_parts=None,
            version_output=None,
        )

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Hurl: found at /usr/local/bin/hurl" in result.output
    assert "version 8.0.1" in result.output
    assert "compatible with >= 4.3.0" in result.output


def test_doctor_json_reports_unsupported_hurl_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return _fake_hurl_status(
                version="4.2.0",
                version_parts=(4, 2, 0),
                version_output="hurl 4.2.0",
            )
        return _fake_hurl_status(
            path="/usr/local/bin/hurlfmt",
            version_checked=False,
            version=None,
            version_parts=None,
            version_output=None,
        )

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "warn"
    assert payload["hurl_compatibility"] == {
        "status": "warn",
        "compatibility": "unsupported",
        "version": "4.2.0",
        "minimum_version": "4.3.0",
        "path": "/usr/local/bin/hurl",
        "message": "hurl 4.2.0 is older than the minimum supported version 4.3.0",
    }


def test_doctor_reports_unsupported_hurl_version_human_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return _fake_hurl_status(
                version="4.2.0",
                version_parts=(4, 2, 0),
                version_output="hurl 4.2.0",
            )
        return _fake_hurl_status(
            path="/usr/local/bin/hurlfmt",
            version_checked=False,
            version=None,
            version_parts=None,
            version_output=None,
        )

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Hurl: unsupported version" in result.output
    assert "4.2.0" in result.output
    assert "minimum supported 4.3.0" in result.output


def test_doctor_ci_fails_for_unsupported_hurl_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return _fake_hurl_status(version="4.2.0", version_parts=(4, 2, 0))
        return _fake_hurl_status(
            path="/usr/local/bin/hurlfmt",
            version_checked=False,
            version=None,
            version_parts=None,
            version_output=None,
        )

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor", "--ci", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    checks = {check["id"]: check for check in payload["ci_readiness"]["checks"]}
    assert checks["hurl_available"]["status"] == "error"
    assert "minimum supported version 4.3.0" in checks["hurl_available"]["message"]


def test_doctor_reports_unparsable_hurl_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return _fake_hurl_status(
                version=None,
                version_parts=None,
                version_output="hurl dev-build",
            )
        return _fake_hurl_status(
            path="/usr/local/bin/hurlfmt",
            version_checked=False,
            version=None,
            version_parts=None,
            version_output=None,
        )

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Hurl: version unparsable" in result.output
    assert "hurl dev-build" in result.output


def test_doctor_reports_invalid_hurl_version_parts_as_unparsable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return SimpleNamespace(
                available=True,
                path="/usr/local/bin/hurl",
                version="8.0.1",
                version_parts=("8", "0", "1"),
                version_checked=True,
                version_output="hurl 8.0.1",
                version_error=None,
            )
        return _fake_hurl_status(
            path="/usr/local/bin/hurlfmt",
            version_checked=False,
            version=None,
            version_parts=None,
            version_output=None,
        )

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["hurl_compatibility"]["compatibility"] == "unparsable"


def test_doctor_reports_configured_agent_readiness_without_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENTROPING_BUILDER_KEY", "sk-proj-live-secret")
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "builder.md").write_text("Build focused Hurl tests.", encoding="utf-8")
    (tmp_path / "agents" / "auditor.md").write_text(
        "Review Hurl coverage and policy risk.",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/builder-model
    api_key_env: ENTROPING_BUILDER_KEY
  auditor:
    source: agents/auditor.md
    model: openai/auditor-model
    api_key_env: ENTROPING_MISSING_AUDITOR_KEY
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Agents: 2 configured" in result.output
    assert "Agent builder: ready" in result.output
    assert "model openai/builder-model" in result.output
    assert "api_key_env ENTROPING_BUILDER_KEY: set" in result.output
    assert "sk-proj-live-secret" not in result.output
    assert "Agent auditor: ready" in result.output
    assert "api_key_env ENTROPING_MISSING_AUDITOR_KEY: not set" in result.output
    assert "Agent breaker:" not in result.output


def test_doctor_reports_no_configured_agents_as_optional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Agents: none configured" in result.output


def test_doctor_reports_agent_without_api_key_env_as_local_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "breaker.md").write_text(
        "Draft hostile local checks.",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  breaker:
    source: agents/breaker.md
    model: ollama/qwen-local
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Agents: 1 configured agent" in result.output
    assert "Agent breaker: ready" in result.output
    assert "api_key_env: not configured" in result.output


def test_doctor_fails_for_configured_missing_agent_persona(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/missing.md
    model: openai/builder-model
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Agent builder: invalid" in result.output
    assert "Agent persona file not found" in result.output


def test_doctor_fails_for_secret_like_agent_persona_without_printing_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "builder.md").write_text(
        "Use sk-proj-live-secret while testing.",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/builder-model
gates: []
""".lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Agent builder: invalid" in result.output
    assert "must not contain secret-like values" in result.output
    assert "sk-proj-live-secret" not in result.output


def test_doctor_reports_missing_traffic_state_without_creating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    runner.invoke(app, ["init", "--minimal"])
    state_path = tmp_path / ".entroping" / "state.db"

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Traffic state: not found" in result.output
    assert "capture traffic with entroping watch" in result.output
    assert not state_path.exists()


def test_doctor_reports_valid_traffic_state_exchange_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    runner.invoke(app, ["init", "--minimal"])
    _record_freeze_exchange(tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Traffic state: valid (.entroping/state.db, 1 exchange)" in result.output


def test_doctor_fails_on_unsupported_traffic_state_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlmodel import Session, SQLModel, create_engine

    from entroping.core.traffic_store import (
        TRAFFIC_STORE_SCHEMA_VERSION,
        TrafficStoreMetadataRow,
    )

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    runner.invoke(app, ["init", "--minimal"])
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{state_dir / 'state.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            TrafficStoreMetadataRow(
                key="schema_version",
                value=str(TRAFFIC_STORE_SCHEMA_VERSION + 1),
            )
        )
        session.commit()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Traffic state: invalid" in result.output
    assert "newer than supported" in result.output


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
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=False, path=None),
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Hurl:" in result.output
    assert "not found" in result.output
    assert "Hurl parser:" in result.output
    assert "hurlfmt" in result.output
    assert "QAnstitution:" in result.output
    assert "run entroping init --minimal" in result.output


def test_doctor_reports_missing_hurlfmt_for_architect_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_discover_hurl(binary: str = "hurl") -> SimpleNamespace:
        if binary == "hurl":
            return SimpleNamespace(available=True, path="/usr/local/bin/hurl")
        return SimpleNamespace(available=False, path=None)

    monkeypatch.setattr(project_cli, "discover_hurl", fake_discover_hurl)
    CliRunner().invoke(app, ["init", "--minimal"])

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Hurl: found at /usr/local/bin/hurl" in result.output
    assert "Hurl parser: not found" in result.output
    assert "hurlfmt" in result.output
    assert "Architect generated-Hurl validation" in " ".join(result.output.split())


def test_doctor_json_reports_versioned_machine_readable_health(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENTROPING_BREAKER_KEY", "sk-proj-live-secret")
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    CliRunner().invoke(app, ["init", "--minimal"])
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "breaker.md").write_text(
        "Draft hostile local checks.",
        encoding="utf-8",
    )
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
agents:
  breaker:
    source: agents/breaker.md
    model: openai/breaker-model
    api_key_env: ENTROPING_BREAKER_KEY
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    _record_freeze_exchange(tmp_path)

    result = CliRunner().invoke(app, ["doctor", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.doctor.v1"
    assert payload["status"] == "ok"
    assert payload["python_version"]
    assert payload["tools"]["hurl"] == {
        "status": "ok",
        "available": True,
        "path": "/usr/local/bin/hurl",
        "message": "hurl found",
    }
    assert payload["tools"]["hurl_parser"] == {
        "status": "ok",
        "available": True,
        "path": "/usr/local/bin/hurlfmt",
        "message": "hurlfmt found",
    }
    assert payload["traffic_state"]["status"] == "ok"
    assert payload["traffic_state"]["exchange_count"] == 1
    assert payload["qanstitution"]["status"] == "ok"
    assert payload["qanstitution"]["project"] == "checkout-api"
    assert payload["agents"] == [
        {
            "role": "breaker",
            "status": "ok",
            "model": "openai/breaker-model",
            "source": "agents/breaker.md",
            "api_key_env": "ENTROPING_BREAKER_KEY",
            "api_key_env_present": True,
            "message": "agent ready",
        }
    ]
    assert "Python:" not in result.output
    assert "sk-proj-live-secret" not in result.output


def test_doctor_ci_json_reports_ready_suite_env_and_report_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    CliRunner().invoke(app, ["init"])
    (tmp_path / "tests" / "checkout.hurl").write_text(
        "GET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tmp_path / "envs" / "ci.env").write_text(
        "base_url=http://localhost:18080\n",
        encoding="utf-8",
    )
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "ci.yaml").write_text(
        """
version: entroping.suite.v1
name: ci
env: ci
paths:
  - tests/*.hurl
reports:
  - json
  - junit
  - html
parallel: true
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["doctor", "--ci", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.doctor.v1"
    assert payload["ci_readiness"]["status"] == "ok"
    assert payload["ci_readiness"]["provider_free_run"] is True
    checks = {check["id"]: check for check in payload["ci_readiness"]["checks"]}
    assert checks["hurl_available"]["status"] == "ok"
    assert checks["report_paths"]["status"] == "ok"
    assert checks["suite_manifests"]["suites"] == ["ci"]
    assert checks["env_variables"]["required_env_names"] == []
    assert "http://localhost:18080" not in result.output


def test_doctor_ci_reports_ready_human_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    CliRunner().invoke(app, ["init"])
    (tmp_path / "tests" / "health.hurl").write_text(
        "GET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "ci.yaml").write_text(
        "version: entroping.suite.v1\nname: ci\npaths:\n  - tests/*.hurl\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["doctor", "--ci"])

    assert result.exit_code == 0
    assert "CI readiness: ready" in result.output
    assert "Suite manifests: ok" in result.output
    assert "Provider free run: ok" in result.output


def test_doctor_ci_reports_warning_human_output_without_suite_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    CliRunner().invoke(app, ["init", "--minimal"])
    (tmp_path / "tests" / "health.hurl").write_text(
        "GET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["doctor", "--ci"])

    assert result.exit_code == 0
    assert "CI readiness: warnings" in result.output
    assert "Suite manifests: warning" in result.output
    assert "No suite manifests found" in result.output


def test_doctor_ci_json_fails_for_missing_hurl_missing_suite_files_and_variables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=False, path=None),
    )
    CliRunner().invoke(app, ["init", "--minimal"])
    (tmp_path / "tests" / "checkout.hurl").write_text(
        "GET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "ci.yaml").write_text(
        """
version: entroping.suite.v1
name: ci
paths:
  - tests/*.hurl
reports:
  - json
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "suites" / "missing.yaml").write_text(
        """
version: entroping.suite.v1
name: missing
paths:
  - tests/missing/*.hurl
reports:
  - junit
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["doctor", "--ci", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ci_readiness"]["status"] == "error"
    checks = {check["id"]: check for check in payload["ci_readiness"]["checks"]}
    assert checks["hurl_available"]["status"] == "error"
    assert checks["suite_manifests"]["status"] == "error"
    assert checks["suite_manifests"]["suites"] == ["ci", "missing"]
    assert "No Hurl tests matched suite 'missing'" in checks["suite_manifests"]["message"]
    assert checks["env_variables"]["status"] == "error"
    assert checks["env_variables"]["required_env_names"] == ["base_url"]
    assert "HURL_VARIABLE_base_url" not in result.output


def test_doctor_ci_json_fails_for_malformed_known_failure_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    CliRunner().invoke(app, ["init", "--minimal"])
    (tmp_path / "qanstitution.yaml").write_text(
        """
project: checkout-api
ignore_failures:
  - test: tests/health.hurl
    rule_id: global_latency
    issue_id: GH-491
    expires: tomorrow
    reason: Malformed expiry.
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["doctor", "--ci", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["qanstitution"]["status"] == "error"
    assert "expires must use YYYY-MM-DD" in payload["qanstitution"]["message"]
    assert "QAnstitution: invalid" not in result.output


def test_doctor_ci_fails_for_unsafe_report_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
    CliRunner().invoke(app, ["init", "--minimal"])
    (tmp_path / "tests" / "health.hurl").write_text(
        "GET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    outside_reports = tmp_path / "outside-reports"
    outside_reports.mkdir()
    reports = tmp_path / "reports"
    if reports.exists():
        reports.rmdir()
    reports.symlink_to(outside_reports, target_is_directory=True)

    result = CliRunner().invoke(app, ["doctor", "--ci"])

    assert result.exit_code == 1
    assert "CI readiness: invalid" in result.output
    assert "Report paths: invalid" in result.output
    assert "must not use symlinks" in result.output


def test_doctor_json_keeps_warning_exit_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=False, path=None),
    )

    result = CliRunner().invoke(app, ["doctor", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "warn"
    assert payload["tools"]["hurl"]["status"] == "warn"
    assert payload["tools"]["hurl_parser"]["status"] == "warn"
    assert payload["hurl_compatibility"] == {
        "status": "warn",
        "compatibility": "missing",
        "version": None,
        "minimum_version": "4.3.0",
        "path": None,
        "message": "hurl not found; install hurl 4.3.0 or newer",
    }
    assert payload["qanstitution"]["status"] == "warn"
    assert payload["qanstitution"]["message"] == "qanstitution.yaml not found"


def test_doctor_json_reports_invalid_config_without_human_markup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cli,
        "discover_hurl",
        lambda binary="hurl": SimpleNamespace(available=True, path=f"/usr/local/bin/{binary}"),
    )
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

    result = CliRunner().invoke(app, ["doctor", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["qanstitution"]["status"] == "error"
    assert "Unsupported QAnstitution condition syntax" in payload["qanstitution"]["message"]
    assert "QAnstitution: invalid" not in result.output


def test_doctor_rejects_unsupported_output_format() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--output", "xml"])

    assert result.exit_code == 2
    assert "Unsupported doctor output: xml" in result.output


def test_display_cli_path_returns_absolute_path_outside_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"

    assert cli_main._display_cli_path(outside) == str(outside)
