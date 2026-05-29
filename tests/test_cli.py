"""CLI smoke tests for the initial scaffold."""

import subprocess
from pathlib import Path
from typing import BinaryIO

import pytest
from typer.testing import CliRunner

from entroping.cli.main import app


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

    runner.invoke(app, ["init", "--minimal"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Python:" in result.output
    assert "Hurl:" in result.output
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

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)

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


def test_run_rejects_future_options_instead_of_silently_ignoring_them() -> None:
    result = CliRunner().invoke(app, ["run", "--report", "json"])

    assert result.exit_code == 2
    assert "not implemented yet for entroping run" in result.output
    assert "--report" in result.output


def test_run_rejects_empty_tag_filter() -> None:
    result = CliRunner().invoke(app, ["run", "--tag", ""])

    assert result.exit_code == 2
    assert "Tag filters must not be empty" in result.output
