"""Tests for local shields-compatible coverage badge generation."""

import json
from pathlib import Path

import pytest

from entroping.core.coverage_badges import (
    BadgeReportError,
    build_coverage_badges,
    coverage_badge_payload,
    write_coverage_badges,
)


def test_coverage_badge_payload_uses_shields_endpoint_shape_and_thresholds() -> None:
    assert coverage_badge_payload(label="policy gates", covered=10, total=10) == {
        "schemaVersion": 1,
        "label": "policy gates",
        "message": "10/10 (100%)",
        "color": "brightgreen",
    }
    assert coverage_badge_payload(label="openapi ops", covered=8, total=10)["color"] == "green"
    assert coverage_badge_payload(label="story links", covered=6, total=10)["color"] == "yellow"
    assert coverage_badge_payload(label="story links", covered=2, total=10)["color"] == "orange"
    assert coverage_badge_payload(label="story links", covered=0, total=10)["color"] == "red"
    assert coverage_badge_payload(label="policy gates", covered=0, total=0) == {
        "schemaVersion": 1,
        "label": "policy gates",
        "message": "0/0 (n/a)",
        "color": "lightgrey",
    }


def test_coverage_badge_payload_rejects_invalid_counts() -> None:
    with pytest.raises(BadgeReportError, match="0 <= covered <= total"):
        coverage_badge_payload(label="policy gates", covered=2, total=1)


def test_build_coverage_badges_from_existing_reports() -> None:
    badges = build_coverage_badges(
        run_report={
            "schema_version": "entroping.run-report.v1",
            "tests": [
                {"path": "tests/health.hurl", "rule_ids": ["latency", "request_id"]},
                {"path": "tests/refund.hurl", "rule_ids": ["latency"]},
            ],
        },
        policy_report={
            "schema_version": "entroping.effective-policy-report.v1",
            "gates": [
                {"id": "latency"},
                {"id": "request_id"},
                {"id": "auth_required"},
            ],
        },
        openapi_report={
            "schema_version": "entroping.openapi-audit.v1",
            "summary": {"total_operations": 4, "covered_operations": 3},
        },
        traceability_report={
            "schema_version": "entroping.traceability-report.v1",
            "stories": [
                {"story_id": "CHK-001", "test_paths": ["tests/health.hurl"]},
                {"story_id": "CHK-002", "test_paths": ["tests/refund.hurl"]},
            ],
            "findings": [
                {"kind": "missing_story_id", "test_path": "tests/unlinked.hurl"},
                {"kind": "duplicate_doc_url", "test_path": "tests/refund.hurl"},
            ],
        },
    )

    assert [badge.filename for badge in badges] == [
        "policy-gates.json",
        "openapi-operations.json",
        "story-traceability.json",
    ]
    assert badges[0].payload == {
        "schemaVersion": 1,
        "label": "policy gates",
        "message": "2/3 (67%)",
        "color": "yellow",
    }
    assert badges[1].payload["message"] == "3/4 (75%)"
    assert badges[1].payload["color"] == "green"
    assert badges[2].payload["message"] == "2/4 (50%)"
    assert badges[2].payload["color"] == "yellow"


def test_traceability_badge_counts_non_missing_findings_as_uncovered_evidence() -> None:
    badges = build_coverage_badges(
        run_report={"schema_version": "entroping.run-report.v1", "tests": []},
        policy_report={
            "schema_version": "entroping.effective-policy-report.v1",
            "gates": [],
        },
        openapi_report={
            "schema_version": "entroping.openapi-audit.v1",
            "summary": {"total_operations": 0, "covered_operations": 0},
        },
        traceability_report={
            "schema_version": "entroping.traceability-report.v1",
            "stories": [{"story_id": "CHK-001", "test_paths": ["tests/checkout.hurl"]}],
            "findings": [
                {
                    "kind": "duplicate_doc_url",
                    "doc_url": "https://docs.example/checkout",
                    "story_ids": ["CHK-001", "CHK-002"],
                },
            ],
        },
    )

    traceability_badge = badges[2].payload
    assert traceability_badge["message"] == "1/2 (50%)"
    assert traceability_badge["color"] == "yellow"


def test_build_coverage_badges_rejects_malformed_source_reports() -> None:
    valid_run = {
        "schema_version": "entroping.run-report.v1",
        "tests": [{"path": "tests/health.hurl", "rule_ids": ["latency"]}],
    }
    valid_policy = {
        "schema_version": "entroping.effective-policy-report.v1",
        "gates": [{"id": "latency"}],
    }
    valid_openapi = {
        "schema_version": "entroping.openapi-audit.v1",
        "summary": {"total_operations": 1, "covered_operations": 1},
    }
    valid_traceability = {
        "schema_version": "entroping.traceability-report.v1",
        "stories": [{"story_id": "CHK-001", "test_paths": ["tests/health.hurl"]}],
        "findings": [{"kind": "duplicate_doc_url", "test_path": "tests/health.hurl"}],
    }

    with pytest.raises(BadgeReportError, match="schema_version entroping.run-report.v1"):
        build_coverage_badges(
            run_report={"schema_version": "wrong", "tests": []},
            policy_report=valid_policy,
            openapi_report=valid_openapi,
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'gates' must be an array"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report={
                "schema_version": "entroping.effective-policy-report.v1",
                "gates": "latency",
            },
            openapi_report=valid_openapi,
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'gates' must contain JSON objects"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report={
                "schema_version": "entroping.effective-policy-report.v1",
                "gates": ["latency"],
            },
            openapi_report=valid_openapi,
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'id' must be a non-empty string"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report={
                "schema_version": "entroping.effective-policy-report.v1",
                "gates": [{"id": ""}],
            },
            openapi_report=valid_openapi,
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'rule_ids' must be an array"):
        build_coverage_badges(
            run_report={
                "schema_version": "entroping.run-report.v1",
                "tests": [{"path": "tests/health.hurl", "rule_ids": "latency"}],
            },
            policy_report=valid_policy,
            openapi_report=valid_openapi,
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'rule_ids' must contain non-empty strings"):
        build_coverage_badges(
            run_report={
                "schema_version": "entroping.run-report.v1",
                "tests": [{"path": "tests/health.hurl", "rule_ids": [""]}],
            },
            policy_report=valid_policy,
            openapi_report=valid_openapi,
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'summary' must be a JSON object"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report=valid_policy,
            openapi_report={"schema_version": "entroping.openapi-audit.v1", "summary": []},
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'covered_operations'"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report=valid_policy,
            openapi_report={
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 1, "covered_operations": -1},
            },
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="greater than total_operations"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report=valid_policy,
            openapi_report={
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 1, "covered_operations": 2},
            },
            traceability_report=valid_traceability,
        )
    with pytest.raises(BadgeReportError, match="field 'test_path' must be"):
        build_coverage_badges(
            run_report=valid_run,
            policy_report=valid_policy,
            openapi_report=valid_openapi,
            traceability_report={
                "schema_version": "entroping.traceability-report.v1",
                "stories": [],
                "findings": [{"kind": "missing_story_id", "test_path": ""}],
            },
        )


def test_write_coverage_badges_fails_before_writing_when_source_report_is_missing(
    tmp_path: Path,
) -> None:
    run_path = tmp_path / "reports" / "run-latest.json"
    policy_path = tmp_path / "reports" / "effective-policy.json"
    openapi_path = tmp_path / "reports" / "openapi-audit.json"
    traceability_path = tmp_path / "reports" / "traceability.json"
    run_path.parent.mkdir()
    run_path.write_text('{"schema_version":"entroping.run-report.v1","tests":[]}', encoding="utf-8")
    policy_path.write_text(
        '{"schema_version":"entroping.effective-policy-report.v1","gates":[]}',
        encoding="utf-8",
    )
    openapi_path.write_text(
        (
            '{"schema_version":"entroping.openapi-audit.v1",'
            '"summary":{"total_operations":0,"covered_operations":0}}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(BadgeReportError, match="Missing traceability report"):
        write_coverage_badges(
            run_json_path=run_path,
            policy_json_path=policy_path,
            openapi_json_path=openapi_path,
            traceability_json_path=traceability_path,
            output_dir=tmp_path / "reports" / "badges",
            project_root=tmp_path,
        )

    assert not (tmp_path / "reports" / "badges").exists()


def test_write_coverage_badges_rejects_unreadable_or_malformed_source_json(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    policy_path = reports_dir / "effective-policy.json"
    openapi_path = reports_dir / "openapi-audit.json"
    traceability_path = reports_dir / "traceability.json"
    policy_path.write_text(
        '{"schema_version":"entroping.effective-policy-report.v1","gates":[]}',
        encoding="utf-8",
    )
    openapi_path.write_text(
        (
            '{"schema_version":"entroping.openapi-audit.v1",'
            '"summary":{"total_operations":0,"covered_operations":0}}'
        ),
        encoding="utf-8",
    )
    traceability_path.write_text(
        '{"schema_version":"entroping.traceability-report.v1","stories":[],"findings":[]}',
        encoding="utf-8",
    )

    malformed_run = reports_dir / "malformed-run.json"
    malformed_run.write_text("{", encoding="utf-8")
    with pytest.raises(BadgeReportError, match="Could not parse run report"):
        write_coverage_badges(
            run_json_path=malformed_run,
            policy_json_path=policy_path,
            openapi_json_path=openapi_path,
            traceability_json_path=traceability_path,
            output_dir=reports_dir / "badges",
            project_root=tmp_path,
        )

    array_run = reports_dir / "array-run.json"
    array_run.write_text("[]", encoding="utf-8")
    with pytest.raises(BadgeReportError, match="run report must be a JSON object"):
        write_coverage_badges(
            run_json_path=array_run,
            policy_json_path=policy_path,
            openapi_json_path=openapi_path,
            traceability_json_path=traceability_path,
            output_dir=reports_dir / "badges",
            project_root=tmp_path,
        )

    directory_run = reports_dir / "directory-run.json"
    directory_run.mkdir()
    with pytest.raises(BadgeReportError, match="Could not read run report"):
        write_coverage_badges(
            run_json_path=directory_run,
            policy_json_path=policy_path,
            openapi_json_path=openapi_path,
            traceability_json_path=traceability_path,
            output_dir=reports_dir / "badges",
            project_root=tmp_path,
        )


def test_write_coverage_badges_writes_deterministic_json_files(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps({"schema_version": "entroping.run-report.v1", "tests": []}),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps({"schema_version": "entroping.effective-policy-report.v1", "gates": []}),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 1, "covered_operations": 1},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )

    result = write_coverage_badges(
        run_json_path=reports_dir / "run-latest.json",
        policy_json_path=reports_dir / "effective-policy.json",
        openapi_json_path=reports_dir / "openapi-audit.json",
        traceability_json_path=reports_dir / "traceability.json",
        output_dir=reports_dir / "badges",
        project_root=tmp_path,
    )

    assert [path.name for path in result.artifacts] == [
        "policy-gates.json",
        "openapi-operations.json",
        "story-traceability.json",
    ]
    assert json.loads((reports_dir / "badges" / "openapi-operations.json").read_text()) == {
        "color": "brightgreen",
        "label": "openapi ops",
        "message": "1/1 (100%)",
        "schemaVersion": 1,
    }


@pytest.mark.security
@pytest.mark.regression
def test_write_coverage_badges_rejects_outside_project_output(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "run-latest.json").write_text(
        json.dumps({"schema_version": "entroping.run-report.v1", "tests": []}),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps({"schema_version": "entroping.effective-policy-report.v1", "gates": []}),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 0, "covered_operations": 0},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "outside-badges"

    with pytest.raises(BadgeReportError, match="coverage badge path must stay under"):
        write_coverage_badges(
            run_json_path=reports_dir / "run-latest.json",
            policy_json_path=reports_dir / "effective-policy.json",
            openapi_json_path=reports_dir / "openapi-audit.json",
            traceability_json_path=reports_dir / "traceability.json",
            output_dir=output_dir,
            project_root=project_root,
        )

    assert not output_dir.exists()


def test_write_coverage_badges_wraps_safe_write_errors(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps({"schema_version": "entroping.run-report.v1", "tests": []}),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps({"schema_version": "entroping.effective-policy-report.v1", "gates": []}),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 0, "covered_operations": 0},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BadgeReportError, match="Could not create parent directory"):
        write_coverage_badges(
            run_json_path=reports_dir / "run-latest.json",
            policy_json_path=reports_dir / "effective-policy.json",
            openapi_json_path=reports_dir / "openapi-audit.json",
            traceability_json_path=reports_dir / "traceability.json",
            output_dir=reports_dir / "run-latest.json",
            project_root=tmp_path,
        )
