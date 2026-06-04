"""CLI adapter tests for report commands."""

from cli_test_support import (
    BinaryIO,
    CliRunner,
    Path,
    ReportWriterError,
    RunReport,
    RunReportSummary,
    RunTestReport,
    _record_freeze_exchange,
    app,
    json,
    pytest,
    report_cli,
    subprocess,
    write_json_report,
)


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


def test_report_redaction_writes_markdown_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="redaction-secret")

    result = runner.invoke(app, ["report", "redaction"])

    assert result.exit_code == 0
    assert "reports/redaction-review.md" in result.output
    content = Path("reports/redaction-review.md").read_text(encoding="utf-8")
    assert "# Entroping Redaction Review" in content
    assert "request authorization header" in content
    assert "request password body field" in content
    assert "redaction-secret" not in content
    assert "[REDACTED]" not in content


def test_report_redaction_writes_html_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="redaction-html-secret")

    result = runner.invoke(app, ["report", "redaction", "--output", "html"])

    assert result.exit_code == 0
    assert "reports/redaction-review.html" in result.output
    content = Path("reports/redaction-review.html").read_text(encoding="utf-8")
    assert "<h1>Entroping Redaction Review</h1>" in content
    assert "request authorization header" in content
    assert "redaction-html-secret" not in content
    assert "[REDACTED]" not in content


def test_report_redaction_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "redaction"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output
    assert not (tmp_path / "reports" / "redaction-review.md").exists()


def test_report_redaction_reports_empty_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.core.traffic_store import TrafficStore

    monkeypatch.chdir(tmp_path)
    TrafficStore.open_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "redaction"])

    assert result.exit_code == 1
    assert "contains no traffic records" in result.output
    assert not (tmp_path / "reports" / "redaction-review.md").exists()


def test_report_redaction_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "redaction", "--output", "json"])

    assert result.exit_code == 2
    assert "Unsupported redaction output" in result.output


def test_report_traceability_outputs_empty_suite_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 0
    assert "# Story Traceability" in result.output
    assert "No story-linked tests found." in result.output
    assert "No traceability findings." in result.output


def test_report_traceability_renders_story_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke,checkout",
                "# entroping: story_id=CHK-001",
                "# entroping: owner=payments",
                "# entroping: doc_url=https://jira.example.test/browse/CHK-001",
                "",
                "GET {{base_url}}/checkout",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 0
    assert "CHK-001" in result.output
    assert "payments" in result.output
    assert "https://jira.example.test/browse/CHK-001" in result.output
    assert "tests/checkout.hurl" in result.output
    assert "checkout, smoke" in result.output


def test_report_traceability_reports_missing_story_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "missing.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 1
    assert "missing_story_id" in result.output
    assert "tests/missing.hurl" in result.output


def test_report_traceability_reports_duplicate_doc_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    for file_name, story_id in (("checkout.hurl", "CHK-001"), ("refund.hurl", "PAY-002")):
        (tests_dir / file_name).write_text(
            "\n".join(
                [
                    f"# entroping: story_id={story_id}",
                    "# entroping: doc_url=https://jira.example.test/browse/shared",
                    "",
                    "GET {{base_url}}/health",
                    "HTTP 200",
                ],
            ),
            encoding="utf-8",
        )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 1
    assert "duplicate_doc_url" in result.output
    assert "CHK-001" in result.output
    assert "PAY-002" in result.output
    assert "https://jira.example.test/browse/shared" in result.output


def test_report_traceability_wraps_metadata_syntax_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "broken.hurl").write_text(
        "# entroping: story_id\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 1
    assert "tests/broken.hurl" in result.output
    assert "line 1" in result.output
    assert "expected" in result.output
    assert "'key=value'" in result.output


def test_report_traceability_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 2
    assert "Unsupported traceability output" in result.output


def test_report_policy_writes_effective_policy_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "policy", "--output", "md"])

    assert result.exit_code == 0
    assert "Wrote effective policy report: reports/effective-policy.md" in result.output
    assert "global_latency" in Path("reports/effective-policy.md").read_text(encoding="utf-8")


def test_report_policy_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "policy", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported policy output" in result.output


def test_report_policy_wraps_effective_policy_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "policy"])

    assert result.exit_code == 1
    assert "QAnstitution file not found" in result.output


def test_report_github_annotations_emits_report_and_traceability_annotations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl
status: failed
token=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    (reports_dir / "drift.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "response_status_changed",
                        "severity": "error",
                        "path": "tests/health.hurl",
                        "message": "Response status changed.",
                        "baseline": {},
                        "current": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "missing.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "github-annotations", "--traceability"])

    assert result.exit_code == 0
    assert "::error file=tests/health.hurl" in result.output
    assert "Entroping Hurl failure" in result.output
    assert "Entroping drift%3A response_status_changed" in result.output
    assert "Entroping traceability%3A missing_story_id" in result.output
    assert "live-secret" not in result.output
    assert "token=[REDACTED]" in result.output


def test_report_github_annotations_truncates_annotations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="2" failures="2" errors="0">
  <testcase classname="tests" name="one.hurl" time="0.001">
    <failure message="first" type="entroping.hurl" />
  </testcase>
  <testcase classname="tests" name="two.hurl" time="0.001">
    <failure message="second" type="entroping.hurl" />
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["report", "github-annotations", "--max-annotations", "1"],
    )

    assert result.exit_code == 0
    assert "Entroping Hurl failure" in result.output
    assert "first" in result.output
    assert "second" not in result.output
    assert "Entroping annotations truncated" in result.output
    assert "1 annotation(s) omitted" in result.output


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


def test_report_github_annotations_rejects_malformed_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "github-annotations"])

    assert result.exit_code == 1
    assert "Could not parse drift report" in result.output


def test_report_sarif_writes_code_scanning_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl
status: failed
token=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    (reports_dir / "drift.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "response_status_changed",
                        "severity": "error",
                        "path": "tests/health.hurl",
                        "message": "Response status changed.",
                        "baseline": {},
                        "current": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "sarif"])

    assert result.exit_code == 0
    assert "Wrote SARIF report: reports/entroping.sarif" in result.output
    sarif = json.loads((reports_dir / "entroping.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 2
    assert "live-secret" not in json.dumps(sarif)
    assert "token=[REDACTED]" in json.dumps(sarif)


def test_report_sarif_accepts_custom_output_and_traceability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "missing.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["report", "sarif", "--traceability", "--output", "reports/security.sarif"],
    )

    assert result.exit_code == 0
    assert "reports/security.sarif" in result.output
    sarif = json.loads(Path("reports/security.sarif").read_text(encoding="utf-8"))
    assert sarif["runs"][0]["results"] == [
        {
            "ruleId": "entroping.traceability.missing_story_id",
            "level": "error",
            "message": {
                "text": "tests/missing.hurl has no # entroping: story_id metadata."
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "tests/missing.hurl"},
                        "region": {"startLine": 1},
                    }
                }
            ],
        }
    ]


def test_report_sarif_wraps_report_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "sarif"])

    assert result.exit_code == 1
    assert "Could not parse drift report" in result.output
