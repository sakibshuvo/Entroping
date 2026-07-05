import hashlib
import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence.otel_mapping as otel_mapping
import entroping.core.readiness.observability_adapter_readiness as adapter_readiness
from entroping.bridge.test_pyramid import TEST_PYRAMID_REPORT_SCHEMA_VERSION
from entroping.core.evidence.external_test_evidence import EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
from entroping.core.evidence.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError

OTEL_MAPPING_SCHEMA_VERSION = (
    otel_mapping.OTEL_MAPPING_SCHEMA_VERSION
)
OtelMappingError = (
    otel_mapping.OtelMappingError
)
build_otel_mapping_packet = (
    otel_mapping.build_otel_mapping_packet
)
render_otel_mapping_markdown = (
    otel_mapping.render_otel_mapping_markdown
)
run_otel_mapping_report = (
    otel_mapping.run_otel_mapping_report
)


def test_run_otel_mapping_writes_value_free_json_from_local_evidence(
    tmp_path: Path,
) -> None:
    observability_path = _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "severity": "attention",
                "events_total": 3,
                "error_events": 1,
                "warning_events": 1,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {"status": "attention", "findings": 2, "evidence_links": 4},
        },
    )
    _write_json(
        tmp_path / "reports" / "test-pyramid.json",
        {
            "schema_version": TEST_PYRAMID_REPORT_SCHEMA_VERSION,
            "summary": {"status": "partial", "layers_total": 6, "layers_covered": 4},
        },
    )
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        {
            "schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
            "summary": {
                "status": "partial",
                "total_tests": 87,
                "total_failures": 1,
                "line_coverage_percent": 91.5,
            },
        },
    )

    result = run_otel_mapping_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "otel-mapping.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == OTEL_MAPPING_SCHEMA_VERSION
    assert payload["summary"] == {
        "status": "ready",
        "severity": "attention",
        "sources_total": 4,
        "sources_present": 4,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "mappings_total": 10,
        "resource_mappings": 2,
        "log_mappings": 3,
        "metric_mappings": 3,
        "trace_mappings": 2,
        "boundary_controls": 5,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["observability_packet"] == {
        "id": "observability_packet",
        "label": "Observability packet",
        "path": "reports/observability-packet.json",
        "state": "present",
        "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
        "sha256": hashlib.sha256(observability_path.read_bytes()).hexdigest(),
        "summary": "ready observability, attention severity, 3 events",
    }
    assert sources["runtime_card"]["summary"] == "attention runtime, 2 findings, 4 links"
    assert {mapping["signal"] for mapping in payload["mappings"]} == {
        "resource",
        "log",
        "metric",
        "trace",
    }
    attributes = {mapping["attribute"] for mapping in payload["mappings"]}
    assert {
        "service.name",
        "entroping.project",
        "entroping.diagnostic.events",
        "entroping.diagnostic.errors",
        "entroping.test.total",
        "entroping.coverage.line_percent",
        "entroping.runtime.status",
        "entroping.runtime_governance.status",
        "entroping.runtime_governance.findings",
        "entroping.runtime_governance.evidence_links",
    } <= attributes
    assert payload["next_actions"] == [
        {
            "priority": "low",
            "action": "Use this packet as the value-free contract for a future OTLP adapter.",
            "source_ids": [
                "observability_packet",
                "runtime_card",
                "test_pyramid",
                "external_test_evidence",
            ],
        }
    ]
    serialized = json.dumps(payload)
    assert "sk-proj" not in serialized
    assert "raw.example.internal" not in serialized


def test_otel_mapping_marks_missing_invalid_and_unsafe_sources_without_raw_values(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "observability-packet.json").write_text("{bad json}\n", encoding="utf-8")
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "summary": {"status": "pass"},
            "leaked": "sk-proj-" + ("a" * 24),
        },
    )
    outside = tmp_path.parent / "outside-test-pyramid.json"
    outside.write_text(
        json.dumps(
            {
                "schema_version": TEST_PYRAMID_REPORT_SCHEMA_VERSION,
                "summary": {"status": "ready"},
                "raw_url": "https://raw.example.internal/path",
            }
        ),
        encoding="utf-8",
    )
    (reports / "test-pyramid.json").symlink_to(outside)

    packet = build_otel_mapping_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["observability_packet"].state == "invalid"
    assert sources["runtime_card"].state == "unsafe"
    assert sources["test_pyramid"].state == "unsafe"
    assert sources["external_test_evidence"].state == "missing"
    assert packet.summary.status == "insufficient"
    assert packet.summary.severity == "blocker"
    serialized = packet.model_dump_json()
    assert "sk-proj" not in serialized
    assert "raw.example.internal" not in serialized
    assert str(tmp_path) not in serialized


def test_run_otel_mapping_writes_markdown_and_partial_state(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {"status": "ready", "severity": "info", "events_total": 0},
        },
    )

    result = run_otel_mapping_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "otel-mapping.md"
    assert result.packet.summary.status == "partial"
    assert result.packet.summary.severity == "attention"
    assert result.packet.next_actions[0].priority == "medium"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping OpenTelemetry Mapping" in markdown
    assert "| log | entroping.diagnostic.events | required | count |" in markdown


def test_otel_mapping_surfaces_runtime_governance_semantic_preview(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {"status": "ready", "severity": "info", "events_total": 0},
        },
    )
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "summary": {"status": "attention", "findings": 2, "evidence_links": 4},
        },
    )
    _write_json(
        tmp_path / "reports" / "test-pyramid.json",
        {
            "schema_version": TEST_PYRAMID_REPORT_SCHEMA_VERSION,
            "summary": {"status": "partial", "layers_total": 6, "layers_covered": 4},
        },
    )

    packet = build_otel_mapping_packet(project_root=tmp_path)
    markdown = render_otel_mapping_markdown(packet)

    mappings = {mapping.attribute: mapping for mapping in packet.mappings}
    assert {
        "entroping.runtime_governance.status",
        "entroping.runtime_governance.findings",
        "entroping.runtime_governance.evidence_links",
    } <= set(mappings)
    assert mappings["entroping.runtime_governance.status"].source_ids == (
        "runtime_card",
        "test_pyramid",
    )
    assert mappings["entroping.runtime_governance.status"].value_kind == "status"
    assert "Runtime-governance semantic preview" in (
        mappings["entroping.runtime_governance.status"].summary
    )
    serialized = packet.model_dump_json()
    assert "sk-proj" not in serialized
    assert "raw.example.internal" not in serialized
    assert "## Semantic Preview" in markdown
    assert (
        "| trace | entroping.runtime&#95;governance.evidence&#95;links | optional | count |"
        in markdown
    )


def test_otel_mapping_missing_only_action_requests_generation(tmp_path: Path) -> None:
    packet = build_otel_mapping_packet(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_present == 0
    assert packet.next_actions[0].priority == "high"
    assert packet.next_actions[0].action == (
        "Generate missing sanitized evidence before enabling an OTLP adapter."
    )


def test_otel_mapping_marks_additional_bad_source_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "observability-packet.json").mkdir()
    (reports / "runtime-card.json").write_bytes(b"\xff")
    (reports / "test-pyramid.json").write_text("[]\n", encoding="utf-8")
    _write_json(
        reports / "external-test-evidence.json",
        {"schema_version": "wrong", "summary": {"status": "partial"}},
    )

    packet = build_otel_mapping_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["observability_packet"].state == "unsafe"
    assert sources["observability_packet"].summary == "not a file"
    assert sources["runtime_card"].state == "invalid"
    assert "invalid UTF-8" in sources["runtime_card"].summary
    assert sources["test_pyramid"].state == "invalid"
    assert "JSON artifact must be an object" in sources["test_pyramid"].summary
    assert sources["external_test_evidence"].state == "invalid"
    assert "schema mismatch" in sources["external_test_evidence"].summary

    (reports / "observability-packet.json").rmdir()
    _write_json(
        reports / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": "ready", "severity": "info", "events_total": 0},
        },
    )

    def unreadable(*_args: object, **_kwargs: object) -> tuple[None, str]:
        return None, "unreadable"

    monkeypatch.setattr(otel_mapping, "read_local_evidence_json_artifact_bytes", unreadable)
    packet = build_otel_mapping_packet(project_root=tmp_path)
    assert {source.state for source in packet.sources} == {"invalid"}

    def outside(*_args: object, **_kwargs: object) -> tuple[None, str]:
        return None, "path outside project"

    monkeypatch.setattr(otel_mapping, "read_local_evidence_json_artifact_bytes", outside)
    packet = build_otel_mapping_packet(project_root=tmp_path)
    assert {source.state for source in packet.sources} == {"unsafe"}


def test_otel_mapping_source_path_resolution_failures_are_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_path(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("outside")

    monkeypatch.setattr(otel_mapping, "first_symlink_path_component", reject_path)

    packet = build_otel_mapping_packet(project_root=tmp_path)

    assert {source.state for source in packet.sources} == {"unsafe"}
    assert "path outside project" in {source.summary for source in packet.sources}
    assert otel_mapping._relative_display(tmp_path.parent / "outside", root=tmp_path) == "outside"

    monkeypatch.setattr(
        otel_mapping,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    assert (
        otel_mapping._source_path_error(tmp_path.parent / "outside.json", root=tmp_path)
        == "path outside project"
    )


def test_otel_mapping_source_summaries_keep_unknown_counts_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": "ready", "severity": "blocker", "events_total": "many"},
        },
    )
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "summary": {"status": "pass", "findings": True, "evidence_links": "four"},
        },
    )
    _write_json(
        tmp_path / "reports" / "test-pyramid.json",
        {
            "schema_version": TEST_PYRAMID_REPORT_SCHEMA_VERSION,
            "summary": {"status": "ready", "layers_total": "six", "layers_covered": True},
        },
    )
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        {
            "schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
            "summary": {
                "status": "ready",
                "total_tests": "eighty",
                "total_failures": True,
                "line_coverage_percent": True,
            },
        },
    )

    packet = build_otel_mapping_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert packet.summary.severity == "blocker"
    assert sources["observability_packet"].summary.endswith("unknown events")
    assert sources["runtime_card"].summary == "pass runtime, unknown findings, unknown links"
    assert sources["test_pyramid"].summary == "ready test pyramid, unknown/unknown layers"
    assert sources["external_test_evidence"].summary.endswith("unknown line coverage")

    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {
                "status": "ready",
                "severity": "nonblocker",
                "events_total": -1,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        {
            "schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
            "summary": {
                "status": "ready",
                "total_tests": 0,
                "total_failures": 0,
                "line_coverage_percent": "n/a",
            },
        },
    )

    packet = build_otel_mapping_packet(project_root=tmp_path)

    assert packet.summary.severity == "info"
    sources = {source.id: source for source in packet.sources}
    assert sources["observability_packet"].summary.endswith("unknown events")
    assert otel_mapping._observability_packet_severity(None) is None
    assert (
        otel_mapping._observability_packet_severity({"summary": {"severity": "info"}})
        == "info"
    )


def test_otel_mapping_rejects_unsupported_and_unsafe_outputs(tmp_path: Path) -> None:
    with pytest.raises(OtelMappingError, match="Unsupported otel-mapping output"):
        run_otel_mapping_report(project_root=tmp_path, output="html")
    with pytest.raises(OtelMappingError, match="must stay under"):
        run_otel_mapping_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "otel-mapping.json",
        )
    with pytest.raises(OtelMappingError, match="must not be written into"):
        run_otel_mapping_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "otel-mapping.json",
        )
    with pytest.raises(OtelMappingError, match="must not be written into"):
        run_otel_mapping_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "otel-mapping.json",
        )


def test_otel_mapping_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(OtelMappingError, match="symlinked component"):
        run_otel_mapping_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "otel-mapping.json",
        )


def test_otel_mapping_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_otel_mapping_packet(project_root=tmp_path)
    monkeypatch.setattr(
        otel_mapping,
        "build_otel_mapping_packet",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(OtelMappingError, match="contains secret-like content"):
        run_otel_mapping_report(project_root=tmp_path, output="json")


def test_otel_mapping_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(otel_mapping, "safe_write_text", fail_safe_write)

    with pytest.raises(OtelMappingError, match="disk full"):
        run_otel_mapping_report(project_root=tmp_path, output="json")


def test_otel_mapping_markdown_escapes_backslash_pipe_cells(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": r"ready\|split", "severity": "attention"},
        },
    )

    markdown = render_otel_mapping_markdown(build_otel_mapping_packet(project_root=tmp_path))

    assert "ready&#92;\\|split" in markdown

    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": "*bold*_under_`code`", "severity": "attention"},
        },
    )

    markdown = render_otel_mapping_markdown(build_otel_mapping_packet(project_root=tmp_path))

    assert "&#42;bold&#42;&#95;under&#95;&#96;code&#96;" in markdown


def test_otel_mapping_forbidden_fields_match_observability_adapter_readiness() -> None:
    assert otel_mapping._FORBIDDEN_VALUE_FIELDS == adapter_readiness._FORBIDDEN_VALUE_FIELDS
    assert "ticket_mutation_payloads" in otel_mapping._FORBIDDEN_VALUE_FIELDS
    assert "dashboard_payloads" in otel_mapping._FORBIDDEN_VALUE_FIELDS
    assert "monitor_payloads" in otel_mapping._FORBIDDEN_VALUE_FIELDS


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
