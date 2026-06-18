"""Tests for SARIF report generation from Entroping findings."""

import json
from pathlib import Path

import pytest

import entroping.core.sarif_report as sarif_report
from entroping.core.github_annotations import GitHubAnnotation, GitHubAnnotationError
from entroping.core.safe_write import SafeWriteError
from entroping.core.sarif_report import (
    SarifReportError,
    build_sarif_report,
    run_sarif_report,
    sarif_report_to_dict,
    write_sarif_report,
)


def test_sarif_report_maps_annotations_to_rules_results_and_locations(
    tmp_path: Path,
) -> None:
    annotations = (
        GitHubAnnotation(
            level="error",
            title="Entroping drift: response_status_changed",
            message="Response status changed.",
            file="tests/checkout.hurl",
            line=12,
        ),
        GitHubAnnotation(
            level="warning",
            title="Entroping traceability: duplicate_doc_url",
            message="Duplicate external document URL.",
            file=None,
            line=1,
        ),
    )

    report = build_sarif_report(annotations, project_root=tmp_path)
    payload = sarif_report_to_dict(report)
    run = payload["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    results = run["results"]

    assert payload["version"] == "2.1.0"
    assert payload["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert rules == [
        {
            "id": "entroping.drift.response_status_changed",
            "name": "Entroping drift: response_status_changed",
            "shortDescription": {"text": "Entroping drift: response_status_changed"},
        },
        {
            "id": "entroping.traceability.duplicate_doc_url",
            "name": "Entroping traceability: duplicate_doc_url",
            "shortDescription": {"text": "Entroping traceability: duplicate_doc_url"},
        },
    ]
    assert results[0] == {
        "ruleId": "entroping.drift.response_status_changed",
        "level": "error",
        "message": {"text": "Response status changed."},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "tests/checkout.hurl"},
                    "region": {"startLine": 12},
                }
            }
        ],
    }
    assert results[1] == {
        "ruleId": "entroping.traceability.duplicate_doc_url",
        "level": "warning",
        "message": {"text": "Duplicate external document URL."},
    }


def test_sarif_report_deduplicates_rules_and_sanitizes_secret_like_content(
    tmp_path: Path,
) -> None:
    annotations = (
        GitHubAnnotation(
            level="notice",
            title="Entroping drift: auth token=live-secret",
            message="Authorization leaked token=live-secret",
            file="tests/auth.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="notice",
            title="Entroping drift: auth token=live-secret",
            message="Again token=live-secret",
            file="tests/auth.hurl",
            line=2,
        ),
    )

    payload = sarif_report_to_dict(build_sarif_report(annotations, project_root=tmp_path))
    serialized = json.dumps(payload, sort_keys=True)

    assert "live-secret" not in serialized
    assert "token=[REDACTED]" in serialized
    assert [rule["id"] for rule in payload["runs"][0]["tool"]["driver"]["rules"]] == [
        "entroping.drift.auth-token-redacted",
    ]
    assert [
        result["ruleId"] for result in payload["runs"][0]["results"]
    ] == [
        "entroping.drift.auth-token-redacted",
        "entroping.drift.auth-token-redacted",
    ]


def test_sarif_report_drops_unsafe_or_invalid_locations(tmp_path: Path) -> None:
    annotations = (
        GitHubAnnotation(
            level="error",
            title="Entroping JUnit error",
            message="outside",
            file="../outside.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="warning",
            title="Entroping Hurl failure",
            message="bad line",
            file="tests/bad-line.hurl",
            line=0,
        ),
        GitHubAnnotation(
            level="warning",
            title="Entroping Hurl failure",
            message="scheme",
            file="https://evil.example/finding.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="warning",
            title="Entroping Hurl failure",
            message="windows drive",
            file="C:/outside/finding.hurl",
            line=1,
        ),
    )

    payload = sarif_report_to_dict(build_sarif_report(annotations, project_root=tmp_path))
    results = payload["runs"][0]["results"]

    assert "locations" not in results[0]
    assert results[1]["locations"] == [
        {
            "physicalLocation": {
                "artifactLocation": {"uri": "tests/bad-line.hurl"},
            }
        }
    ]
    assert "locations" not in results[2]
    assert "locations" not in results[3]


def test_sarif_report_handles_generic_rules_notice_level_and_empty_paths(
    tmp_path: Path,
) -> None:
    annotations = (
        GitHubAnnotation(
            level="notice",
            title="Entroping annotations truncated",
            message=f"{tmp_path}/reports/extra finding omitted.",
            file=" ",
            line=1,
        ),
        GitHubAnnotation(
            level="notice",
            title="Outside finding",
            message="outside",
            file="/tmp/outside.hurl",
            line=1,
        ),
        GitHubAnnotation(
            level="warning",
            title=" . ",
            message="dot path",
            file=".",
            line=1,
        ),
    )

    payload = sarif_report_to_dict(build_sarif_report(annotations, project_root=tmp_path))
    results = payload["runs"][0]["results"]

    assert [rule["id"] for rule in payload["runs"][0]["tool"]["driver"]["rules"]] == [
        "entroping.annotations.truncated",
        "entroping.outside-finding",
        "entroping.finding",
    ]
    assert results[0] == {
        "ruleId": "entroping.annotations.truncated",
        "level": "note",
        "message": {"text": "reports/extra finding omitted."},
    }
    assert "locations" not in results[1]
    assert "locations" not in results[2]


def test_run_sarif_report_accepts_absolute_inputs_and_output(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    junit = reports_dir / "junit.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    output = reports_dir / "absolute.sarif"

    result = run_sarif_report(
        project_root=tmp_path,
        output_path=output,
        junit_path=junit,
        drift_path=reports_dir / "missing-drift.json",
        include_traceability=False,
    )

    assert result.output_path == output
    assert output.is_file()
    assert result.report.runs[0].results[0].rule_id == "entroping.hurl.failure"


@pytest.mark.security
@pytest.mark.regression
def test_run_sarif_report_rejects_outside_project_output(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    output = tmp_path / "outside.sarif"

    with pytest.raises(SarifReportError, match="SARIF report path must stay under"):
        run_sarif_report(
            project_root=project_root,
            output_path=output,
            junit_path=project_root / "reports" / "missing-junit.xml",
            drift_path=project_root / "reports" / "missing-drift.json",
            include_traceability=False,
        )

    assert not output.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"findings": []},
        {"schema_version": "entroping.run-report.v1", "findings": []},
    ],
)
def test_run_sarif_report_rejects_unsupported_drift_schema_versions(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    drift = reports_dir / "drift.json"
    drift.write_text(json.dumps(payload), encoding="utf-8")
    output = reports_dir / "entroping.sarif"

    with pytest.raises(GitHubAnnotationError, match="drift report schema_version"):
        run_sarif_report(
            project_root=tmp_path,
            output_path=output,
            junit_path=reports_dir / "missing-junit.xml",
            drift_path=drift,
            include_traceability=False,
        )

    assert not output.exists()


def test_write_sarif_report_writes_machine_readable_json(tmp_path: Path) -> None:
    report = build_sarif_report(
        (
            GitHubAnnotation(
                level="error",
                title="Entroping Hurl failure",
                message="failed",
                file="tests/health.hurl",
                line=1,
            ),
        ),
        project_root=tmp_path,
    )

    output = write_sarif_report(report, tmp_path / "reports" / "entroping.sarif")

    assert output == tmp_path / "reports" / "entroping.sarif"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["runs"][0]["results"][0]["ruleId"] == "entroping.hurl.failure"


def test_write_sarif_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = build_sarif_report((), project_root=tmp_path)

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("disk unavailable")

    monkeypatch.setattr(sarif_report, "safe_write_text", fail_safe_write)

    with pytest.raises(SarifReportError, match="disk unavailable"):
        write_sarif_report(report, tmp_path / "reports" / "entroping.sarif")
