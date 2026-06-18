"""Unit tests for GitHub Actions annotation rendering from reports."""

import json
from pathlib import Path

import pytest

from entroping.bridge.story_traceability import compile_story_traceability
from entroping.core.github_annotations import (
    GitHubAnnotation,
    GitHubAnnotationError,
    annotations_from_drift_report,
    annotations_from_junit_report,
    annotations_from_traceability_report,
    render_github_annotation,
)
from entroping.core.github_annotations import (
    main as github_annotations_main,
)
from entroping.models.hurl import HurlMetadata, HurlTest


def test_render_github_annotation_escapes_properties_and_message() -> None:
    rendered = render_github_annotation(
        GitHubAnnotation(
            level="error",
            title="drift: status, changed",
            message="line 1\nsecret=live-secret",
            file="tests/api:checkout,smoke.hurl",
            line=1,
        )
    )

    assert rendered == (
        "::error file=tests/api%3Acheckout%2Csmoke.hurl,line=1,"
        "title=drift%3A status%2C changed::line 1%0Asecret=[REDACTED]"
    )


def test_annotations_from_junit_report_maps_failures_to_hurl_files(tmp_path: Path) -> None:
    junit = tmp_path / "reports" / "junit.xml"
    junit.parent.mkdir()
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests/checkout" name="health.hurl" time="0.123">
    <failure message="failed" type="entroping.hurl">path: tests/checkout/health.hurl
status: failed
token=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    annotations = annotations_from_junit_report(junit)

    assert annotations == (
        GitHubAnnotation(
            level="error",
            title="Entroping Hurl failure",
            message="path: tests/checkout/health.hurl\nstatus: failed\ntoken=[REDACTED]",
            file="tests/checkout/health.hurl",
            line=1,
        ),
    )


def test_annotations_from_junit_report_handles_missing_and_malformed_reports(
    tmp_path: Path,
) -> None:
    assert annotations_from_junit_report(tmp_path / "missing.xml") == ()

    malformed = tmp_path / "junit.xml"
    malformed.write_text("<testsuite><testcase>", encoding="utf-8")

    with pytest.raises(GitHubAnnotationError, match="Could not parse JUnit report"):
        annotations_from_junit_report(malformed)

    unreadable = tmp_path / "unreadable-junit.xml"
    unreadable.mkdir()
    with pytest.raises(GitHubAnnotationError, match="Could not read JUnit report"):
        annotations_from_junit_report(unreadable)


@pytest.mark.security
@pytest.mark.regression
def test_annotations_from_junit_report_rejects_entity_bearing_xml(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
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

    with pytest.raises(GitHubAnnotationError, match="unsafe XML"):
        annotations_from_junit_report(junit)


def test_annotations_from_junit_report_uses_fallback_paths(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping fallback paths" tests="3" failures="2" errors="1">
  <testcase classname="." name="plain.hurl" time="0.001">
    <failure message="message-only" type="entroping.hurl" />
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

    annotations = annotations_from_junit_report(junit)

    assert annotations == (
        GitHubAnnotation(
            level="error",
            title="Entroping Hurl failure",
            message="message-only",
            file="plain.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="error",
            title="Entroping JUnit error",
            message="nested.hurl",
            file="tests/checkout flow/nested.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="error",
            title="Entroping Hurl failure",
            message="unmapped",
            file=None,
            line=1,
        ),
    )


def test_annotations_from_drift_report_maps_severities(tmp_path: Path) -> None:
    drift = tmp_path / "reports" / "drift.json"
    drift.parent.mkdir()
    drift.write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "response_status_changed",
                        "severity": "error",
                        "path": "tests/checkout.hurl",
                        "message": "Response status changed.",
                        "baseline": {"response_status_code": 200},
                        "current": {"response_status_code": 500},
                    },
                    {
                        "kind": "new_current_test",
                        "severity": "info",
                        "path": "tests/new.hurl",
                        "message": "New test.",
                        "baseline": {},
                        "current": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    annotations = annotations_from_drift_report(drift)

    assert annotations == (
        GitHubAnnotation(
            level="error",
            title="Entroping drift: response_status_changed",
            message="Response status changed.",
            file="tests/checkout.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="notice",
            title="Entroping drift: new_current_test",
            message="New test.",
            file="tests/new.hurl",
            line=1,
        ),
    )


def test_annotations_from_drift_report_handles_missing_and_malformed_reports(
    tmp_path: Path,
) -> None:
    assert annotations_from_drift_report(tmp_path / "missing.json") == ()

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(GitHubAnnotationError, match="Could not parse drift report"):
        annotations_from_drift_report(malformed)

    array_report = tmp_path / "array.json"
    array_report.write_text("[]", encoding="utf-8")
    with pytest.raises(GitHubAnnotationError, match="must be a JSON object"):
        annotations_from_drift_report(array_report)

    invalid_findings = tmp_path / "invalid-findings.json"
    invalid_findings.write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GitHubAnnotationError, match="must contain a findings list"):
        annotations_from_drift_report(invalid_findings)

    unreadable = tmp_path / "unreadable-drift.json"
    unreadable.mkdir()
    with pytest.raises(GitHubAnnotationError, match="Could not read drift report"):
        annotations_from_drift_report(unreadable)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"findings": []},
            "must declare schema_version entroping.drift-report.v1",
        ),
        (
            {"schema_version": "entroping.run-report.v1", "findings": []},
            "Unsupported drift report schema_version",
        ),
    ],
)
def test_annotations_from_drift_report_rejects_unsupported_schema_versions(
    tmp_path: Path,
    payload: dict[str, object],
    message: str,
) -> None:
    drift = tmp_path / "drift.json"
    drift.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GitHubAnnotationError, match=message) as exc_info:
        annotations_from_drift_report(drift)

    assert "entroping.run-report.v1" not in str(exc_info.value)


def test_annotations_from_drift_report_handles_partial_findings(tmp_path: Path) -> None:
    drift = tmp_path / "drift.json"
    drift.write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    "skip-me",
                    {
                        "kind": "dependency_updated",
                        "severity": "warning",
                        "path": "dependency:requests",
                        "message": "Dependency changed.",
                    },
                    {
                        "kind": "suite_changed",
                        "severity": "warning",
                        "path": "*",
                        "message": "Suite changed.",
                    },
                    {
                        "kind": 42,
                        "severity": "info",
                        "path": 42,
                        "message": 42,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    annotations = annotations_from_drift_report(drift)

    assert annotations == (
        GitHubAnnotation(
            level="warning",
            title="Entroping drift: dependency_updated",
            message="Dependency changed.",
            file=None,
            line=1,
        ),
        GitHubAnnotation(
            level="warning",
            title="Entroping drift: suite_changed",
            message="Suite changed.",
            file=None,
            line=1,
        ),
        GitHubAnnotation(
            level="notice",
            title="Entroping drift: unknown",
            message="unknown",
            file=None,
            line=1,
        ),
    )


def test_annotations_from_traceability_report_maps_findings() -> None:
    report = compile_story_traceability(
        [
            HurlTest(
                path=Path("tests/missing.hurl"),
                metadata=HurlMetadata(),
            ),
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

    annotations = annotations_from_traceability_report(report)

    assert annotations == (
        GitHubAnnotation(
            level="error",
            title="Entroping traceability: missing_story_id",
            message="tests/missing.hurl has no # entroping: story_id metadata.",
            file="tests/missing.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="warning",
            title="Entroping traceability: duplicate_doc_url",
            message=(
                "External doc URL https://jira.example.test/browse/shared is linked "
                "to multiple story IDs: CHK-001, PAY-002."
            ),
            file=None,
            line=1,
        ),
    )


def test_github_annotations_main_truncates_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text(
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

    exit_code = github_annotations_main(
        [
            "--junit",
            str(junit),
            "--drift",
            str(tmp_path / "missing-drift.json"),
            "--max-annotations",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Entroping Hurl failure" in output
    assert "first" in output
    assert "second" not in output
    assert "Entroping annotations truncated" in output
    assert "1 annotation(s) omitted" in output


def test_github_annotations_main_returns_controlled_drift_schema_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    drift = tmp_path / "drift.json"
    drift.write_text(
        json.dumps({"schema_version": "entroping.run-report.v1", "findings": []}),
        encoding="utf-8",
    )

    exit_code = github_annotations_main(
        [
            "--junit",
            str(tmp_path / "missing-junit.xml"),
            "--drift",
            str(drift),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Unsupported drift report schema_version" in captured.err
    assert "entroping.run-report.v1" not in captured.err
    assert "Traceback" not in captured.err
