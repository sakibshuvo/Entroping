"""Tests for provider-neutral artifact-backed review summaries."""

import json
from pathlib import Path

import pytest

from entroping.bridge.story_traceability import compile_story_traceability
from entroping.core.review_summary import (
    ReviewSummaryError,
    build_review_summary,
    render_review_summary_markdown,
    run_review_summary,
)
from entroping.models.hurl import HurlMetadata, HurlTest


def test_review_summary_reports_missing_artifacts_without_failing(tmp_path: Path) -> None:
    summary = build_review_summary(
        run_json_path=tmp_path / "reports" / "run-latest.json",
        junit_path=tmp_path / "reports" / "junit.xml",
        drift_path=tmp_path / "reports" / "drift.json",
        traceability_report=None,
    )

    markdown = render_review_summary_markdown(summary)

    assert summary.status == "attention"
    assert summary.findings == ()
    assert "- Run JSON: `missing`" in markdown
    assert "- JUnit XML: `missing`" in markdown
    assert "- Drift JSON: `missing`" in markdown
    assert "No review findings were found." in markdown


def test_review_summary_includes_failing_run_and_junit_evidence(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "generated_at": "2026-06-01T00:00:00+00:00",
                "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="checkout.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/checkout.hurl
token=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=reports_dir / "run-latest.json",
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )

    markdown = render_review_summary_markdown(summary)
    assert summary.status == "fail"
    assert "- Project: `checkout-api`" in markdown
    assert "- Environment: `ci`" in markdown
    assert "- Total: `2`" in markdown
    assert "- Failed: `1`" in markdown
    assert "| JUnit | error | tests/checkout.hurl |" in markdown
    assert "live-secret" not in markdown
    assert "token=[REDACTED]" in markdown


def test_review_summary_includes_retry_and_unstable_run_evidence(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "generated_at": "2026-06-03T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [
                    {
                        "path": "tests/eventual.hurl",
                        "execution_path": ".entroping/run/eventual.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 50,
                        "rule_ids": [],
                        "stdout": "token=live-secret",
                        "stderr": "",
                        "retry": {
                            "retry_count": 1,
                            "unstable": True,
                            "attempts": [
                                {
                                    "attempt": 1,
                                    "status": "failed",
                                    "exit_code": 42,
                                    "duration_ms": 20,
                                    "stdout_truncated": False,
                                    "stderr_truncated": False,
                                },
                                {
                                    "attempt": 2,
                                    "status": "passed",
                                    "exit_code": 0,
                                    "duration_ms": 30,
                                    "stdout_truncated": False,
                                    "stderr_truncated": False,
                                },
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=reports_dir / "run-latest.json",
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )

    markdown = render_review_summary_markdown(summary)
    assert summary.status == "attention"
    assert "| Run JSON | warning | tests/eventual.hurl |" in markdown
    assert "unstable after 1 retry" in markdown
    assert "token=live-secret" not in markdown


def test_review_summary_ignores_malformed_retry_entries_and_reports_stable_retries(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    run_json = reports_dir / "run-latest.json"
    run_json.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "generated_at": "2026-06-03T00:00:00+00:00",
                "summary": {"total": 4, "passed": 4, "failed": 0, "exit_code": 0},
                "tests": [
                    "skip-me",
                    {"path": "tests/no-retry.hurl", "retry": "not-a-dict"},
                    {
                        "path": "tests/zero-retry.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "retry": {"retry_count": 0, "unstable": False, "attempts": []},
                    },
                    {
                        "path": "tests/stable-retry.hurl",
                        "status": "",
                        "exit_code": "unknown",
                        "retry": {"retry_count": 2, "unstable": False, "attempts": []},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=run_json,
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )

    assert summary.status == "pass"
    assert [
        (finding.severity, finding.path, finding.message) for finding in summary.findings
    ] == [
        (
            "notice",
            "tests/stable-retry.hurl",
            "retried 2 retries; final status unknown exit=unknown",
        )
    ]

    run_json.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "generated_at": "2026-06-03T00:00:00+00:00",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": {},
            }
        ),
        encoding="utf-8",
    )
    summary_without_tests = build_review_summary(
        run_json_path=run_json,
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )
    assert summary_without_tests.findings == ()


def test_review_summary_includes_drift_and_traceability_findings(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "response_status_changed",
                        "severity": "error",
                        "path": "tests/checkout.hurl",
                        "message": "Response status changed.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "missing-story.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = run_review_summary(
        project_root=tmp_path,
        run_json_path=reports_dir / "run-latest.json",
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        include_traceability=True,
    )

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.summary.status == "fail"
    assert result.output_path == reports_dir / "review-summary.md"
    assert "| Drift | error | tests/checkout.hurl | Response status changed. |" in markdown
    assert (
        "| Traceability | error | tests/missing-story.hurl | "
        "tests/missing-story.hurl has no # entroping: story_id metadata. |"
        in markdown
    )


def test_review_summary_escapes_markdown_table_cells(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="unsafe.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/unsafe.hurl
value: &lt;script&gt;|break</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=reports_dir / "run-latest.json",
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )

    markdown = render_review_summary_markdown(summary)
    assert "&lt;script&gt;\\|break" in markdown
    assert "<script>|break" not in markdown


def test_review_summary_rejects_malformed_artifacts(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    with pytest.raises(ReviewSummaryError, match="Could not parse drift report"):
        build_review_summary(
            run_json_path=reports_dir / "run-latest.json",
            junit_path=reports_dir / "junit.xml",
            drift_path=reports_dir / "drift.json",
            traceability_report=None,
        )


def test_review_summary_rejects_malformed_run_json(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    run_json = reports_dir / "run-latest.json"
    run_json.write_text("[]", encoding="utf-8")

    with pytest.raises(ReviewSummaryError, match="Run report .* must be a JSON object"):
        build_review_summary(
            run_json_path=run_json,
            junit_path=reports_dir / "junit.xml",
            drift_path=reports_dir / "drift.json",
            traceability_report=None,
        )

    run_json.write_text(json.dumps({"summary": []}), encoding="utf-8")
    with pytest.raises(ReviewSummaryError, match="must contain a summary object"):
        build_review_summary(
            run_json_path=run_json,
            junit_path=reports_dir / "junit.xml",
            drift_path=reports_dir / "drift.json",
            traceability_report=None,
        )

    run_json.write_text(
        json.dumps(
            {
                "summary": {
                    "total": "1",
                    "passed": 0,
                    "failed": 0,
                    "exit_code": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReviewSummaryError, match="summary.total"):
        build_review_summary(
            run_json_path=run_json,
            junit_path=reports_dir / "junit.xml",
            drift_path=reports_dir / "drift.json",
            traceability_report=None,
        )


def test_review_summary_handles_junit_fallback_paths_and_parse_errors(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    junit = reports_dir / "junit.xml"
    junit.write_text("<testsuite><testcase>", encoding="utf-8")
    with pytest.raises(ReviewSummaryError, match="Could not parse JUnit report"):
        build_review_summary(
            run_json_path=reports_dir / "run-latest.json",
            junit_path=junit,
            drift_path=reports_dir / "drift.json",
            traceability_report=None,
        )

    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE testsuite [
  <!ENTITY leaked "secret-from-entity">
]>
<testsuite name="Entroping unsafe xml" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="unsafe.hurl" time="0.001">
    <failure message="failed" type="entroping.hurl">&leaked;</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    with pytest.raises(ReviewSummaryError, match="unsafe XML"):
        build_review_summary(
            run_json_path=reports_dir / "run-latest.json",
            junit_path=junit,
            drift_path=reports_dir / "drift.json",
            traceability_report=None,
        )

    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping fallback paths" tests="3" failures="2" errors="1">
  <testcase classname="." name="plain.hurl" time="0.001">
    <failure message="plain failure" type="entroping.hurl" />
  </testcase>
  <testcase classname="tests\\checkout flow" name="nested.hurl" time="0.001">
    <error type="entroping.junit" />
  </testcase>
  <testcase classname="tests" time="0.001">
    <failure message="unmapped" type="entroping.hurl" />
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=reports_dir / "run-latest.json",
        junit_path=junit,
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )

    assert [finding.path for finding in summary.findings] == [
        "plain.hurl",
        "tests/checkout flow/nested.hurl",
        None,
    ]


def test_review_summary_handles_drift_edge_shapes_and_warning_status(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    drift = reports_dir / "drift.json"
    drift.write_text(json.dumps({"findings": {}}), encoding="utf-8")
    with pytest.raises(ReviewSummaryError, match="must contain a findings list"):
        build_review_summary(
            run_json_path=reports_dir / "run-latest.json",
            junit_path=reports_dir / "junit.xml",
            drift_path=drift,
            traceability_report=None,
        )

    drift.write_text(
        json.dumps(
            {
                "findings": [
                    "skip-me",
                    {
                        "kind": "dependency_updated",
                        "severity": "warning",
                        "path": "dependency:payments",
                        "message": "Dependency changed.",
                    },
                    {
                        "kind": 42,
                        "severity": "info",
                        "path": 42,
                        "message": 42,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=reports_dir / "run-latest.json",
        junit_path=reports_dir / "junit.xml",
        drift_path=drift,
        traceability_report=None,
    )

    assert summary.status == "attention"
    assert summary.findings[0].severity == "warning"
    assert summary.findings[0].path is None
    assert summary.findings[1].severity == "notice"
    assert summary.findings[1].message == "unknown"


def test_review_summary_uses_run_fallback_fields_and_pass_status(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "project": 42,
                "environment": [],
            }
        ),
        encoding="utf-8",
    )

    summary = build_review_summary(
        run_json_path=reports_dir / "run-latest.json",
        junit_path=reports_dir / "junit.xml",
        drift_path=reports_dir / "drift.json",
        traceability_report=None,
    )

    markdown = render_review_summary_markdown(summary)
    assert summary.status == "pass"
    assert "- Project: `unknown`" in markdown
    assert "- Environment: `default`" in markdown


def test_review_summary_reports_traceability_warnings(tmp_path: Path) -> None:
    report = compile_story_traceability(
        [
            HurlTest(
                path=Path("tests/checkout.hurl"),
                metadata=HurlMetadata(
                    meta={
                        "story_id": "CHK-001",
                        "doc_url": "https://jira.example.test/browse/shared",
                    }
                ),
            ),
            HurlTest(
                path=Path("tests/refund.hurl"),
                metadata=HurlMetadata(
                    meta={
                        "story_id": "PAY-002",
                        "doc_url": "https://jira.example.test/browse/shared",
                    }
                ),
            ),
        ]
    )

    summary = build_review_summary(
        run_json_path=tmp_path / "reports" / "run-latest.json",
        junit_path=tmp_path / "reports" / "junit.xml",
        drift_path=tmp_path / "reports" / "drift.json",
        traceability_report=report,
    )

    assert summary.status == "attention"
    assert len(summary.findings) == 1
    assert summary.findings[0].severity == "warning"
    assert summary.findings[0].path is None


def test_review_summary_wraps_safe_write_errors(tmp_path: Path) -> None:
    outside = tmp_path.parent / "review-summary.md"

    with pytest.raises(ReviewSummaryError, match="path must stay under"):
        run_review_summary(
            project_root=tmp_path,
            run_json_path=tmp_path / "reports" / "run-latest.json",
            junit_path=tmp_path / "reports" / "junit.xml",
            drift_path=tmp_path / "reports" / "drift.json",
            include_traceability=False,
            output_path=outside,
        )
