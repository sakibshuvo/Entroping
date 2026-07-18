"""Launch-critical CLI report command tests."""

from collections.abc import Mapping

from cli_report_test_helpers import (
    _write_text,
)
from cli_test_support import (
    BinaryIO,
    CliRunner,
    Path,
    ReportWriterError,
    RunReport,
    RunReportSummary,
    RunTestReport,
    app,
    json,
    pytest,
    report_cli,
    subprocess,
    write_json_report,
)
from typer.core import TyperCommand, TyperGroup
from typer.main import get_command

from entroping.core.runtime_card import RuntimeCardError

_REPORT_COMMAND_NAMES = (
    "aha-artifact-index",
    "bug",
    "failure-bundle",
    "first-run-checklist",
    "runtime-card",
    "review-summary",
    "delta",
    "policy-diff",
    "redaction",
    "capture-summary",
    "policy",
    "gate-coverage",
    "github-annotations",
    "sarif",
    "traceability",
    "badges",
    "gate-injection",
    "test-quality",
    "test-pyramid",
    "artifact-manifest",
    "promote-drift-baseline",
    "evidence-bundle",
    "design-partner-feedback",
    "pilot-metrics",
    "pilot-outcome",
    "pilot-cohort",
    "handoff",
    "notification-packet",
    "team-evidence-readiness",
    "evidence-cloud-readiness",
    "evidence-cloud-export",
    "evidence-cloud-workspace",
    "evidence-cloud-dashboard",
    "evidence-links",
    "otlp-preview",
    "evidence-portal",
    "pr-evidence-card",
    "pr-evidence-card-summary",
    "evidence-action-plan",
    "work-item-draft",
    "work-item-import-bundle",
    "team-access-control-plan",
    "integration-readiness",
    "devex-readiness",
    "connector-intent",
    "external-test-evidence",
    "observability-packet",
    "otel-mapping",
    "observability-adapter-readiness",
    "api-inventory",
    "mutation-readiness",
    "evidence-index",
    "qa-brain-seed",
    "qa-brain-eval-plan",
    "qa-brain-retrieval-plan",
    "qa-brain-prompt-plan",
    "qa-brain-fine-tune-readiness",
    "qa-brain-model-packaging-plan",
    "qa-brain-routing-plan",
    "qa-brain-repair-plan",
    "agent-bundle",
    "mutation-readiness-replay",
)
_REPORT_COMMAND_PANEL_RANGES = (
    (0, 6, "Launch-Critical Reports"),
    (6, 15, "Stable Public Reports"),
    (15, 21, "Maintainer And Baseline Tools"),
    (21, 62, "Experimental Design-Partner Evidence"),
)
_APPROVED_DESCRIPTION_VERBS = {
    "Compare",
    "Emit",
    "Explain",
    "Generate",
    "Inspect",
    "Map",
    "Promote",
    "Summarize",
    "Validate",
    "Write",
}


def _resolved_report_group() -> TyperGroup:
    root_command = get_command(app)
    assert isinstance(root_command, TyperGroup)
    report_command = root_command.commands["report"]
    assert isinstance(report_command, TyperGroup)
    return report_command


def _report_description_errors(
    commands: Mapping[str, TyperCommand],
) -> tuple[str, ...]:
    errors: list[str] = []
    for command_name, command in commands.items():
        description = command.help
        if description is None or not description.strip():
            errors.append(f"{command_name}: description is blank")
            continue
        if len(description.splitlines()) != 1:
            errors.append(f"{command_name}: description must be one line")
        if len(description) > 80:
            errors.append(f"{command_name}: description exceeds 80 characters")
        if not description.endswith("."):
            errors.append(f"{command_name}: description must end with a period")
        if description.partition(" ")[0] not in _APPROVED_DESCRIPTION_VERBS:
            errors.append(f"{command_name}: description must start with an approved verb")
    return tuple(errors)


def _assert_report_description(command_name: str, expected: str) -> None:
    command = _resolved_report_group().commands[command_name]
    assert command.help == expected


def test_report_command_names_order_and_panel_ranges_are_stable() -> None:
    commands = _resolved_report_group().commands

    assert tuple(commands) == _REPORT_COMMAND_NAMES
    command_values = tuple(commands.values())
    for start, stop, panel in _REPORT_COMMAND_PANEL_RANGES:
        panel_commands = command_values[start:stop]
        for command in panel_commands:
            assert isinstance(command, TyperCommand)
            assert command.rich_help_panel == panel


def test_report_command_descriptions_are_actionable() -> None:
    commands: dict[str, TyperCommand] = {}
    for command_name, command in _resolved_report_group().commands.items():
        assert isinstance(command, TyperCommand)
        commands[command_name] = command

    assert _report_description_errors(commands) == ()


def test_report_description_validator_names_blank_command() -> None:
    blank_command = TyperCommand("blank-fixture", help=" \t ")

    assert _report_description_errors({"blank-fixture": blank_command}) == (
        "blank-fixture: description is blank",
    )


@pytest.mark.parametrize(
    ("command_name", "description"),
    (
        (
            "aha-artifact-index",
            "Inspect local Aha artifacts and print readiness hints.",
        ),
        (
            "first-run-checklist",
            "Inspect local first-run prerequisites and print readiness hints.",
        ),
    ),
)
def test_launch_report_command_descriptions_are_actionable(
    command_name: str,
    description: str,
) -> None:
    _assert_report_description(command_name, description)


def test_report_help_classifies_launch_stable_experimental_and_maintainer_commands() -> None:
    result = CliRunner().invoke(app, ["report", "--help"])

    assert result.exit_code == 0
    panels = (
        "Launch-Critical Reports",
        "Stable Public Reports",
        "Maintainer And Baseline Tools",
        "Experimental Design-Partner Evidence",
    )
    for panel in panels:
        assert panel in result.output
    panel_offsets = [result.output.index(panel) for panel in panels]
    assert panel_offsets == sorted(panel_offsets)

    launch_panel = result.output.split("Launch-Critical Reports", maxsplit=1)[1].split(
        "Stable Public Reports",
        maxsplit=1,
    )[0]
    for command in (
        "aha-artifact-index",
        "bug",
        "failure-bundle",
        "first-run-checklist",
        "runtime-card",
        "review-summary",
    ):
        assert command in launch_panel

    stable_panel = result.output.split("Stable Public Reports", maxsplit=1)[1].split(
        "Maintainer And Baseline Tools",
        maxsplit=1,
    )[0]
    for command in (
        "delta",
        "policy",
        "policy-diff",
        "gate-coverage",
        "traceability",
        "github-annotations",
        "sarif",
    ):
        assert command in stable_panel

    maintainer_panel = result.output.split("Maintainer And Baseline Tools", maxsplit=1)[1].split(
        "Experimental Design-Partner Evidence",
        maxsplit=1,
    )[0]
    for command in (
        "badges",
        "gate-injection",
        "test-quality",
        "artifact-manifest",
        "promote-drift-baseline",
    ):
        assert command in maintainer_panel

    experimental_panel = result.output.split(
        "Experimental Design-Partner Evidence",
        maxsplit=1,
    )[1]
    for command in (
        "evidence-bundle",
        "design-partner-feedback",
        "handoff",
        "notification-packet",
        "integration-readiness",
        "devex-readiness",
        "evidence-cloud-readiness",
        "evidence-cloud-export",
        "evidence-cloud-workspace",
        "evidence-links",
        "evidence-portal",
        "connector-intent",
        "evidence-action-plan",
        "work-item-draft",
        "work-item-import-bundle",
        "external-test-evidence",
        "team-access-control-plan",
        "team-evidence-readiness",
        "observability-packet",
        "otel-mapping",
        "otlp-preview",
        "observability-adapter-readiness",
        "api-inventory",
        "mutation-readiness",
        "mutation-readiness-replay",
        "evidence-index",
        "qa-brain-seed",
        "qa-brain-eval-plan",
        "qa-brain-retrieval-plan",
        "qa-brain-prompt-plan",
        "qa-brain-fine-tune-readiness",
        "qa-brain-model-packaging-plan",
        "qa-brain-routing-plan",
        "qa-brain-repair-plan",
        "evidence-cloud-dashboard",
        "pilot-metrics",
        "pilot-outcome",
        "pilot-cohort",
        "agent-bundle",
    ):
        assert command in experimental_panel
def test_report_runtime_card_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
  "tests": []
}
""",
    )
    _write_text(
        Path("reports") / "capture-summary.json",
        """
{
  "schema_version": "entroping.capture-summary.v1",
  "summary": {
    "total_records": 1,
    "total_sessions": 1,
    "redacted_records": 1,
    "unredacted_records": 0
  },
  "redaction_categories": []
}
""",
    )
    _write_text(
        Path("reports") / "artifact-manifest.json",
        """
{
  "schema_version": "entroping.report-artifact-manifest.v1",
  "audit": {"verification": {"status": "verified"}}
}
""",
    )
    _write_text(
        Path("reports") / "evidence-bundle.json",
        """
{
  "schema_version": "entroping.evidence-bundle.v1",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "purpose": "design-partner-upload-readiness",
  "project": "checkout-api",
  "summary": {
    "status": "ready",
    "required_total": 2,
    "required_present": 2,
    "required_missing": 0,
    "required_invalid": 0,
    "artifacts_total": 2,
    "diagnostics_total": 0
  },
  "artifacts": [],
  "missing_artifacts": [],
  "diagnostics": [],
  "manifest_audit": {
    "path": "reports/artifact-manifest.json",
    "status": "verified",
    "chain_path": ".entroping/report-audit-chain.jsonl",
    "checked_events": 1,
    "latest_event_hash": "0",
    "diagnostics": []
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "runtime-card"])

    assert result.exit_code == 0
    assert "Wrote runtime evidence card: reports/runtime-card.md" in result.output
    card = Path("reports/runtime-card.md").read_text(encoding="utf-8")
    assert "# Entroping Runtime Evidence Card" in card
    assert "- Status: `pass`" in card


def test_report_runtime_card_exits_nonzero_without_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
  "tests": []
}
""",
    )
    _write_text(
        Path("reports") / "capture-summary.json",
        """
{
  "schema_version": "entroping.capture-summary.v1",
  "summary": {
    "total_records": 1,
    "total_sessions": 1,
    "redacted_records": 1,
    "unredacted_records": 0
  },
  "redaction_categories": []
}
""",
    )

    result = CliRunner().invoke(app, ["report", "runtime-card", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(Path("reports/runtime-card.json").read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "attention"
    assert {
        ("missing_artifact_manifest", "reports/artifact-manifest.json"),
        ("missing_evidence_bundle", "reports/evidence-bundle.json"),
    } <= {(finding["code"], finding["path"]) for finding in payload["findings"]}


def test_report_runtime_card_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
  "tests": []
}
""",
    )

    result = CliRunner().invoke(app, ["report", "runtime-card", "--output", "json"])

    assert result.exit_code == 1
    assert "Wrote runtime evidence card: reports/runtime-card.json" in result.output
    payload = json.loads(Path("reports/runtime-card.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.runtime-card.v1"
    assert payload["summary"]["status"] == "fail"


def test_report_runtime_card_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "runtime-card", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported runtime card output" in result.output


def test_report_runtime_card_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_runtime_card(*args: object, **kwargs: object) -> object:
        raise RuntimeCardError("runtime card source evidence is unsafe")

    monkeypatch.setattr(report_cli, "run_runtime_card_report", fail_runtime_card)

    result = CliRunner().invoke(app, ["report", "runtime-card"])

    assert result.exit_code == 1
    assert "runtime card source evidence is unsafe" in result.output
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
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")

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


def test_report_bug_rejects_unsupported_latest_run_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    latest_state.parent.mkdir()
    latest_state.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v999",
                "project": "checkout-api",
                "environment": "default",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "Could not load latest run report" in normalized_output
    assert "must use schema_version entroping.run-report.v1" in normalized_output
    assert "entroping.run-report.v999" not in result.output


def test_report_bug_rejects_versioned_latest_run_missing_required_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    latest_state.parent.mkdir()
    latest_state.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "default",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "Could not load latest run report" in normalized_output
    assert "required field summary.total" in normalized_output
    assert "private-runtime-value" not in result.output


def test_report_failure_bundle_writes_sanitized_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="failed",
                exit_code=1,
                duration_ms=10,
                rule_ids=("global_latency",),
                stdout="Authorization: Bearer bundle-secret\n",
                stderr="token=bundle-secret\nassert failed",
            ),
        ),
    )
    write_json_report(report, latest_state)

    result = CliRunner().invoke(app, ["report", "failure-bundle"])

    assert result.exit_code == 0
    assert "reports/failure-bundle/manifest.json" in result.output
    manifest = json.loads(Path("reports/failure-bundle/manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "entroping.failure-bundle.v1"
    assert "bundle-secret" not in (Path("reports/failure-bundle") / "run-latest.json").read_text(
        encoding="utf-8"
    )


def test_report_failure_bundle_returns_actionable_message_without_latest_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "failure-bundle"])

    assert result.exit_code == 1
    assert "Run entroping run before report failure-bundle" in result.output
    assert not (tmp_path / "reports" / "failure-bundle").exists()


def test_report_failure_bundle_returns_actionable_message_without_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-06-04T00:00:00+00:00",
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

    result = CliRunner().invoke(app, ["report", "failure-bundle"])

    assert result.exit_code == 1
    assert "no failures to bundle" in result.output


def test_report_first_run_checklist_prints_local_artifact_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "GET https://example.internal/health\nHTTP 200\n",
        encoding="utf-8",
    )
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text("{}", encoding="utf-8")
    (reports_dir / "run-latest.html").write_text("{}", encoding="utf-8")
    (reports_dir / "junit.xml").write_text("<testsuite></testsuite>", encoding="utf-8")
    (reports_dir / "drift-baseline.candidate.json").write_text("{}", encoding="utf-8")
    (reports_dir / "delta.json").write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "first-run-checklist"])

    assert result.exit_code == 0
    assert "Hurl tests: " in result.output
    assert "Latest run JSON: " in result.output
    assert "run-latest.html" in result.output
    assert "JUnit XML" in result.output
    assert "Drift baseline candidate" in result.output
    assert "Delta output: " in result.output
    assert "present" in result.output
    assert "optional" not in result.output.lower()


def test_report_aha_artifact_index_prints_local_paths_schema_and_hints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        '{"schema_version":"entroping.run-report.v1","project":"private-demo"}\n',
        encoding="utf-8",
    )
    (reports_dir / "run-latest.html").write_text("<!doctype html>\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "aha-artifact-index"])

    assert result.exit_code == 0
    assert "Run JSON: present" in result.output
    assert "path: reports/run-latest.json" in result.output
    assert "schema: entroping.run-report.v1" in result.output
    assert "Run HTML: present" in result.output
    assert "Runtime card JSON: missing" in result.output
    assert "hint: Run entroping report runtime-card --output json" in result.output
    assert "private-demo" not in result.output


def test_report_aha_artifact_index_exits_nonzero_for_invalid_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "aha-artifact-index"])

    assert result.exit_code == 1
    assert "Run JSON: invalid" in result.output
    assert "hint: Artifact JSON is invalid." in result.output


def test_report_first_run_checklist_reports_missing_hint_and_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=\nGET https://example.internal/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "first-run-checklist"])

    assert result.exit_code == 1
    assert "Could not discover Hurl tests" in result.output
    assert "No discoverable .hurl files are available" not in result.output


def test_report_first_run_checklist_marks_missing_non_errors_without_fail_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "first-run-checklist"])

    assert result.exit_code == 0
    assert "Hurl tests: missing" in result.output
    assert "Latest run JSON: missing" in result.output
    assert "Latest run HTML: missing" in result.output
    assert "JUnit XML: missing" in result.output
    assert "Drift baseline candidate: missing" in result.output
    assert "Delta output: optional-missing" in result.output
    assert "Optional" in result.output


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

    monkeypatch.setattr(report_cli, "write_bug_report", fail_write_bug_report)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "could not write bug" in result.output
def test_report_review_summary_writes_provider_neutral_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "generated_at": "2026-06-01T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl
secret=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "review-summary"])

    assert result.exit_code == 0
    assert "Wrote review summary: reports/review-summary.md" in result.output
    summary = (reports_dir / "review-summary.md").read_text(encoding="utf-8")
    assert "# Entroping Review Summary" in summary
    assert "| JUnit | error | tests/health.hurl |" in summary
    assert "live-secret" not in summary
    assert "secret=[REDACTED]" in summary


def test_report_review_summary_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "review-summary", "--output", "json"])

    assert result.exit_code == 2
    assert "Unsupported review summary output" in result.output


def test_report_review_summary_wraps_report_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "review-summary"])

    assert result.exit_code == 1
    assert "Could not parse drift report" in result.output


def test_report_review_summary_rejects_malformed_tests_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": {},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "review-summary"])

    assert result.exit_code == 1
    assert "must contain a tests list" in result.output
    assert not (reports_dir / "review-summary.md").exists()
