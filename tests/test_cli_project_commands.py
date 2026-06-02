"""CLI adapter tests for root, init, and doctor commands."""

from cli_test_support import (
    CliRunner,
    Path,
    SimpleNamespace,
    _record_freeze_exchange,
    app,
    cli_main,
    project_cli,
    pytest,
    yaml,
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


def test_display_cli_path_returns_absolute_path_outside_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"

    assert cli_main._display_cli_path(outside) == str(outside)
