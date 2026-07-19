"""Stable public CLI report command tests."""

from cli_report_test_helpers import (
    _capture_summary_with_unredacted_records,
    _redaction_review_with_unsafe_records,
    _write_effective_policy_report,
)
from cli_test_support import (
    CliRunner,
    Path,
    RunReport,
    RunReportSummary,
    RunTestReport,
    _record_freeze_exchange,
    _record_mock_exchange,
    app,
    json,
    pytest,
    report_cli,
    write_json_report,
)

from entroping.bridge.capture_summary import (
    capture_summary_report_to_dict,
    render_capture_summary_markdown,
)
from entroping.bridge.redaction_review import (
    render_redaction_review_html,
    render_redaction_review_markdown,
)
from entroping.core.capture_summary_report import CaptureSummaryResult
from entroping.core.redaction_review_report import RedactionReviewResult


def test_report_delta_outputs_json_and_fails_on_added_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
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
                    stdout="Authorization: Bearer delta-secret",
                    stderr="token=delta-secret",
                ),
            ),
        ),
        base_path,
    )
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=20,
                    rule_ids=("global_latency",),
                    stdout="Authorization: Bearer delta-secret",
                    stderr="token=delta-secret",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            str(base_path),
            "--current",
            str(current_path),
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.run-delta-report.v1"
    assert payload["status"] == "fail"
    assert payload["added_failures"][0]["path"] == "tests/health.hurl"
    assert payload["latency_deltas"][0]["delta_ms"] == 10
    assert "delta-secret" not in result.output
    assert "token=" not in result.output


def test_report_delta_outputs_markdown_and_passes_when_failures_resolve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:00:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path="tests/refund.hurl",
                    execution_path=".entroping/run/refund.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=10,
                    rule_ids=("old_gate",),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        base_path,
    )
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
            tests=(
                RunTestReport(
                    path="tests/refund.hurl",
                    execution_path=".entroping/run/refund.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=(),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        ["report", "delta", "--base", str(base_path), "--current", str(current_path)],
    )

    assert result.exit_code == 0
    assert "# Entroping Run Delta" in result.output
    assert "Status: **pass**" in result.output
    assert "tests/refund.hurl" in result.output


def test_report_delta_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "delta", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported delta output" in result.output


def test_report_delta_wraps_report_load_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            "reports/missing-base.json",
            "--current",
            "reports/current.json",
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare run reports" in result.output


def test_report_delta_rejects_unsafe_test_paths_without_echoing_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
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
        ),
        base_path,
    )
    unsafe_path = "/private/tmp/customer-secret.hurl"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path=unsafe_path,
                    execution_path=".entroping/run/health.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=20,
                    rule_ids=("global_latency",),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            str(base_path),
            "--current",
            str(current_path),
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare run reports" in result.output
    assert "unsafe test path" in result.output
    assert unsafe_path not in result.output


def test_report_delta_rejects_project_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
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
        ),
        base_path,
    )
    write_json_report(
        RunReport(
            project="billing-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=20,
                    rule_ids=("global_latency",),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            str(base_path),
            "--current",
            str(current_path),
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare run reports" in result.output
    assert "project mismatch" in result.output
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


def test_report_redaction_fail_on_unsafe_passes_for_redacted_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="redaction-safe-secret")

    result = CliRunner().invoke(app, ["report", "redaction", "--fail-on-unsafe"])

    assert result.exit_code == 0
    content = Path("reports/redaction-review.md").read_text(encoding="utf-8")
    assert "- Unredacted records: 0" in content
    assert "- Low-confidence records: 0" in content
    assert "redaction-safe-secret" not in content


def test_report_redaction_without_fail_on_unsafe_preserves_default_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def write_unsafe_redaction_review(
        *,
        project_root: Path,
        output: str,
    ) -> RedactionReviewResult:
        report = _redaction_review_with_unsafe_records(
            unredacted_records=1,
            low_confidence_records=1,
        )
        output_path = project_root / "reports" / f"redaction-review.{output}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_redaction_review_markdown(report), encoding="utf-8")
        return RedactionReviewResult(output_path=output_path, report=report)

    monkeypatch.setattr(report_cli, "run_redaction_review", write_unsafe_redaction_review)

    result = CliRunner().invoke(app, ["report", "redaction"])

    assert result.exit_code == 0
    assert Path("reports/redaction-review.md").exists()
    assert "unsafe records" not in result.output


@pytest.mark.parametrize(
    ("output", "unredacted_records", "low_confidence_records"),
    [
        ("md", 1, 0),
        ("html", 0, 2),
    ],
)
def test_report_redaction_fail_on_unsafe_fails_after_writing_report(
    output: str,
    unredacted_records: int,
    low_confidence_records: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def write_unsafe_redaction_review(
        *,
        project_root: Path,
        output: str,
    ) -> RedactionReviewResult:
        report = _redaction_review_with_unsafe_records(
            unredacted_records=unredacted_records,
            low_confidence_records=low_confidence_records,
        )
        output_path = project_root / "reports" / f"redaction-review.{output}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output == "html":
            output_path.write_text(render_redaction_review_html(report), encoding="utf-8")
        else:
            output_path.write_text(render_redaction_review_markdown(report), encoding="utf-8")
        return RedactionReviewResult(output_path=output_path, report=report)

    monkeypatch.setattr(report_cli, "run_redaction_review", write_unsafe_redaction_review)

    result = CliRunner().invoke(
        app,
        ["report", "redaction", "--output", output, "--fail-on-unsafe"],
    )

    assert result.exit_code == 1
    assert (
        "Redaction review found unsafe records: "
        f"unredacted={unredacted_records}, "
        f"low_confidence={low_confidence_records}."
    ) in result.output
    assert Path("reports", f"redaction-review.{output}").exists()


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


def test_report_redaction_fail_on_unsafe_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "redaction", "--output", "json", "--fail-on-unsafe"],
    )

    assert result.exit_code == 2
    assert "Unsupported redaction output" in result.output
def test_report_capture_summary_writes_json_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="capture-cli-secret")
    _record_mock_exchange(tmp_path, secret="capture-dependency-secret")

    result = runner.invoke(app, ["report", "capture-summary", "--output", "json"])

    assert result.exit_code == 0
    assert "reports/capture-summary.json" in result.output
    payload = json.loads(Path("reports/capture-summary.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.capture-summary.v1"
    assert payload["summary"]["total_records"] == 2
    assert payload["dependency_targets"][0] == {
        "label": "payments.example.test",
        "count": 1,
    }
    assert "capture-cli-secret" not in result.output
    assert "capture-dependency-secret" not in json.dumps(payload)
    assert "[REDACTED]" not in json.dumps(payload)


def test_report_capture_summary_fail_on_unredacted_passes_for_redacted_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="capture-cli-secret")

    result = CliRunner().invoke(
        app,
        ["report", "capture-summary", "--output", "json", "--fail-on-unredacted"],
    )

    assert result.exit_code == 0
    payload = json.loads(Path("reports/capture-summary.json").read_text(encoding="utf-8"))
    assert payload["summary"]["unredacted_records"] == 0
    assert "capture-cli-secret" not in json.dumps(payload)


def test_report_capture_summary_fail_on_unredacted_passes_for_default_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="capture-cli-secret")

    result = CliRunner().invoke(app, ["report", "capture-summary", "--fail-on-unredacted"])

    assert result.exit_code == 0
    markdown = Path("reports/capture-summary.md").read_text(encoding="utf-8")
    assert "| Unredacted records | 0 |" in markdown
    assert "capture-cli-secret" not in markdown


@pytest.mark.parametrize(
    ("output", "unredacted_records", "record_word"),
    [
        ("md", 1, "record"),
        ("json", 2, "records"),
    ],
)
def test_report_capture_summary_fail_on_unredacted_fails_after_writing_report(
    output: str,
    unredacted_records: int,
    record_word: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def write_unredacted_summary(*, project_root: Path, output: str) -> CaptureSummaryResult:
        report = _capture_summary_with_unredacted_records(unredacted_records)
        output_path = project_root / "reports" / f"capture-summary.{output}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output == "json":
            output_path.write_text(
                json.dumps(capture_summary_report_to_dict(report), indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            output_path.write_text(render_capture_summary_markdown(report), encoding="utf-8")
        return CaptureSummaryResult(output_path=output_path, report=report)

    monkeypatch.setattr(report_cli, "run_capture_summary_report", write_unredacted_summary)

    result = CliRunner().invoke(
        app,
        ["report", "capture-summary", "--output", output, "--fail-on-unredacted"],
    )

    assert result.exit_code == 1
    assert (
        f"Capture summary found {unredacted_records} unredacted traffic {record_word}."
        in result.output
    )
    assert Path("reports", f"capture-summary.{output}").exists()


def test_report_capture_summary_writes_empty_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.core.traffic_store import TrafficStore

    monkeypatch.chdir(tmp_path)
    TrafficStore.open_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "capture-summary"])

    assert result.exit_code == 0
    assert "0 traffic records" in result.output
    content = Path("reports/capture-summary.md").read_text(encoding="utf-8")
    assert "No captured traffic records found." in content


def test_report_capture_summary_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "capture-summary"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output
    assert not (tmp_path / "reports" / "capture-summary.md").exists()
    assert not (tmp_path / ".entroping").exists()


def test_report_capture_summary_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "capture-summary", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported capture-summary output" in result.output


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


def test_report_traceability_outputs_json_for_badge_sources(
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
                "",
                "GET {{base_url}}/checkout",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.traceability-report.v1"
    assert payload["summary"] == {"stories": 1, "findings": 0, "passed": True}
    assert payload["stories"][0]["story_id"] == "CHK-001"


def test_report_traceability_links_markdown_story_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "# entroping: story_id=CHK-001\n\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    stories_dir = Path("docs") / "stories"
    stories_dir.mkdir(parents=True)
    (stories_dir / "checkout.md").write_text(
        "---\nstory_id: CHK-001\ntitle: Checkout accepts payment\n---\n",
        encoding="utf-8",
    )

    md_result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])
    json_result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert md_result.exit_code == 0
    assert "docs/stories/checkout.md" in md_result.output
    assert "Checkout accepts payment" in md_result.output
    assert json_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["stories"][0]["story_paths"] == ["docs/stories/checkout.md"]
    assert payload["stories"][0]["titles"] == ["Checkout accepts payment"]


def test_report_traceability_reports_malformed_story_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    stories_dir = Path("docs") / "stories"
    stories_dir.mkdir(parents=True)
    (stories_dir / "broken.md").write_text("# Broken story\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["findings"][0]["kind"] == "malformed_story_metadata"
    assert payload["findings"][0]["story_path"] == "docs/stories/broken.md"


def test_report_traceability_reports_missing_story_when_story_directory_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "# entroping: story_id=CHK-001\n\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    (Path("docs") / "stories").mkdir(parents=True)

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["findings"][0]["kind"] == "missing_story"
    assert payload["findings"][0]["story_ids"] == ["CHK-001"]


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
    result = CliRunner().invoke(app, ["report", "traceability", "--output", "html"])

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


def test_report_policy_diff_emits_json_from_effective_policy_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    (reports / "base-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": ["rules/base.yaml"],
                "gates": [
                    {
                        "id": "latency",
                        "source_path": "qanstitution.yaml",
                        "condition": "true",
                        "gate": "duration < 2000",
                        "enforcement": "block",
                        "final": False,
                        "group": None,
                        "description": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (reports / "effective-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": ["rules/current.yaml"],
                "gates": [
                    {
                        "id": "latency",
                        "source_path": "qanstitution.yaml",
                        "condition": "true",
                        "gate": "duration < 1000",
                        "enforcement": "block",
                        "final": False,
                        "group": None,
                        "description": None,
                    },
                    {
                        "id": "auth",
                        "source_path": "rules/current.yaml",
                        "condition": "true",
                        "gate": 'header "Authorization" exists',
                        "enforcement": "warn",
                        "final": True,
                        "group": None,
                        "description": "Auth evidence",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.effective-policy-diff.v1"
    assert payload["status"] == "changed"
    assert payload["summary"]["added_imports"] == 1
    assert payload["summary"]["removed_imports"] == 1
    assert payload["summary"]["added_gates"] == 1
    assert payload["summary"]["changed_gates"] == 1


def test_report_policy_diff_emits_markdown_no_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    policy = {
        "schema_version": "entroping.effective-policy-report.v1",
        "project": "checkout-api",
        "config_path": "qanstitution.yaml",
        "imports": [],
        "gates": [],
    }
    (reports / "base-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    (reports / "effective-policy.json").write_text(json.dumps(policy), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
        ],
    )

    assert result.exit_code == 0
    assert "# Entroping Effective Policy Diff" in result.stdout
    assert "No effective policy differences found." in result.stdout


def test_report_policy_diff_fail_on_change_exits_nonzero_for_changed_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    _write_effective_policy_report(
        reports / "base-policy.json",
        gates=(
            {
                "id": "latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 1000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
            },
        ),
    )
    _write_effective_policy_report(
        reports / "effective-policy.json",
        gates=(
            {
                "id": "latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 1000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
            },
            {
                "id": "auth",
                "source_path": "rules/current.yaml",
                "condition": "true",
                "gate": 'header "Authorization" exists',
                "enforcement": "warn",
                "final": False,
                "group": None,
                "description": None,
            },
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
            "--output",
            "json",
            "--fail-on-change",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "changed"
    assert payload["summary"]["added_gates"] == 1


def test_report_policy_diff_fail_on_change_allows_unchanged_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    policy = {
        "id": "latency",
        "source_path": "qanstitution.yaml",
        "condition": "true",
        "gate": "duration < 1000",
        "enforcement": "block",
        "final": False,
        "group": None,
        "description": None,
    }
    _write_effective_policy_report(reports / "base-policy.json", gates=(policy,))
    _write_effective_policy_report(reports / "effective-policy.json", gates=(policy,))

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
            "--fail-on-change",
        ],
    )

    assert result.exit_code == 0
    assert "Status: **unchanged**" in result.stdout


def test_report_policy_diff_rejects_bad_output() -> None:
    result = CliRunner().invoke(app, ["report", "policy-diff", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported policy-diff output" in result.output


def test_report_policy_diff_wraps_malformed_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    (reports / "base-policy.json").write_text("{not json}\n", encoding="utf-8")
    (reports / "effective-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": [],
                "gates": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare effective policy reports" in result.output


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


@pytest.mark.security
@pytest.mark.regression
def test_report_github_annotations_drops_unsafe_file_properties(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping unsafe paths" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="unsafe.hurl" time="0.001">
    <failure message="failed" type="entroping.hurl">path: ../outside.hurl
status: failed</failure>
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
                        "kind": "unsafe_annotation_path",
                        "severity": "error",
                        "path": "https://evil.example/finding.hurl",
                        "message": "Unsafe annotation path.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "github-annotations"])

    assert result.exit_code == 0
    assert "::error title=Entroping Hurl failure::" in result.output
    assert "::error title=Entroping drift%3A unsafe_annotation_path::" in result.output
    assert "file=../outside.hurl" not in result.output
    assert "file=https%3A//evil.example/finding.hurl" not in result.output
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
            "message": {"text": "tests/missing.hurl has no # entroping: story_id metadata."},
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


@pytest.mark.security
@pytest.mark.regression
def test_report_sarif_rejects_outside_project_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)
    output = tmp_path / "outside.sarif"

    result = CliRunner().invoke(
        app,
        ["report", "sarif", "--output", str(output)],
    )

    assert result.exit_code == 1
    assert "SARIF report path must stay under" in result.output
    assert not output.exists()


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
