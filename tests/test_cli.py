"""CLI smoke tests for the initial scaffold."""

import json
import subprocess
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree

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


def test_architect_build_new_requires_configured_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text("project: checkout-api\ngates: []\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["architect", "build", "--new"])

    assert result.exit_code == 1
    assert "sources.spec is required" in result.output


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


def test_architect_build_rejects_merge_strategy_until_supported() -> None:
    result = CliRunner().invoke(app, ["architect", "build", "--new", "--strategy", "merge"])

    assert result.exit_code == 2
    assert "--strategy merge is not implemented yet" in result.output


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


def test_run_rejects_unsupported_report_format() -> None:
    result = CliRunner().invoke(app, ["run", "--report", "drift"])

    assert result.exit_code == 2
    assert "Unsupported report format" in result.output


def test_run_rejects_future_options_instead_of_silently_ignoring_them() -> None:
    result = CliRunner().invoke(app, ["run", "--parallel"])

    assert result.exit_code == 2
    assert "not implemented yet for entroping run" in result.output
    assert "--parallel" in result.output


def test_run_rejects_empty_tag_filter() -> None:
    result = CliRunner().invoke(app, ["run", "--tag", ""])

    assert result.exit_code == 2
    assert "Tag filters must not be empty" in result.output
