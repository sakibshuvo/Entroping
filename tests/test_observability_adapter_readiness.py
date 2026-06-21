import hashlib
import json
import os
from pathlib import Path

import pytest

import entroping.core.observability_adapter_readiness as adapter_readiness
from entroping.core.evidence_index_report import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.observability_adapter_readiness import (
    OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION,
    ObservabilityAdapterReadinessError,
    build_observability_adapter_readiness_packet,
    render_observability_adapter_readiness_markdown,
    run_observability_adapter_readiness_report,
)
from entroping.core.observability_packet import OBSERVABILITY_PACKET_SCHEMA_VERSION
from entroping.core.otel_mapping import OTEL_MAPPING_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError


def test_run_observability_adapter_readiness_writes_value_free_json(
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
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "otel-mapping.json",
        {
            "schema_version": OTEL_MAPPING_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "severity": "attention",
                "mappings_total": 7,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "evidence-index.json",
        {
            "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "artifacts_total": 12,
                "artifacts_present": 12,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 4},
        },
    )

    result = run_observability_adapter_readiness_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "observability-adapter-readiness.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION
    assert payload["summary"] == {
        "status": "ready",
        "severity": "attention",
        "sources_total": 4,
        "sources_present": 4,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "adapters_total": 5,
        "adapters_ready": 5,
        "adapters_attention": 0,
        "adapters_blocked": 0,
        "boundary_controls": 6,
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
    assert {adapter["id"] for adapter in payload["adapters"]} == {
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic",
    }
    assert {adapter["status"] for adapter in payload["adapters"]} == {"ready"}
    serialized = json.dumps(payload)
    assert "sk-proj" not in serialized
    assert "raw.example.internal" not in serialized


def test_observability_adapter_readiness_marks_bad_sources_without_raw_values(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "observability-packet.json").write_text("{bad json}\n", encoding="utf-8")
    _write_json(
        reports / "otel-mapping.json",
        {
            "schema_version": OTEL_MAPPING_SCHEMA_VERSION,
            "summary": {"status": "ready"},
            "leaked": "sk-proj-" + ("a" * 24),
        },
    )
    outside = tmp_path.parent / "outside-evidence-index.json"
    outside.write_text(
        json.dumps(
            {
                "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
                "summary": {"status": "ready"},
                "raw_url": "https://raw.example.internal/path",
            }
        ),
        encoding="utf-8",
    )
    (reports / "evidence-index.json").symlink_to(outside)

    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["observability_packet"].state == "invalid"
    assert sources["otel_mapping"].state == "unsafe"
    assert sources["evidence_index"].state == "unsafe"
    assert sources["runtime_card"].state == "missing"
    assert packet.summary.status == "insufficient"
    assert packet.summary.severity == "blocker"
    assert {adapter.status for adapter in packet.adapters} == {"blocked"}
    serialized = packet.model_dump_json()
    assert "sk-proj" not in serialized
    assert "raw.example.internal" not in serialized
    assert str(tmp_path) not in serialized


def test_observability_adapter_readiness_writes_markdown_and_partial_state(
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

    result = run_observability_adapter_readiness_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "observability-adapter-readiness.md"
    assert result.packet.summary.status == "partial"
    assert result.packet.summary.severity == "attention"
    assert result.packet.next_actions[0].priority == "medium"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Observability Adapter Readiness" in markdown
    assert "| datadog | Datadog | attention |" in markdown

    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "project": "checkout-api",
            "summary": {"status": "blocked", "severity": "blocker", "events_total": 0},
        },
    )

    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.severity == "blocker"


def test_observability_adapter_readiness_missing_only_action_requests_generation(
    tmp_path: Path,
) -> None:
    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_present == 0
    assert packet.next_actions[0].priority == "high"
    assert packet.next_actions[0].action == (
        "Generate missing sanitized evidence before adapter design."
    )


def test_observability_adapter_readiness_keeps_unknown_counts_value_free(
    tmp_path: Path,
) -> None:
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
        tmp_path / "reports" / "otel-mapping.json",
        {
            "schema_version": OTEL_MAPPING_SCHEMA_VERSION,
            "summary": {
                "status": "ready",
                "severity": "info",
                "mappings_total": True,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "evidence-index.json",
        {
            "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
            "summary": {
                "status": "ready",
                "artifacts_total": "many",
                "artifacts_present": True,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "summary": {"status": "pass", "findings": True, "evidence_links": -1},
        },
    )

    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    assert packet.summary.severity == "info"
    sources = {source.id: source for source in packet.sources}
    assert sources["observability_packet"].summary.endswith("unknown events")
    assert sources["otel_mapping"].summary.endswith("unknown mappings")
    assert sources["evidence_index"].summary.endswith("unknown/unknown artifacts")
    assert sources["runtime_card"].summary == "pass runtime, unknown findings, unknown links"
    assert adapter_readiness._document_severity(None) is None

    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": "ready", "severity": "blocker", "events_total": 0},
        },
    )

    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    assert packet.summary.severity == "blocker"


def test_observability_adapter_readiness_marks_additional_bad_source_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "observability-packet.json").mkdir()
    (reports / "otel-mapping.json").write_bytes(b"\xff")
    (reports / "evidence-index.json").write_text("[]\n", encoding="utf-8")
    _write_json(
        reports / "runtime-card.json",
        {"schema_version": "wrong", "summary": {"status": "pass"}},
    )

    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["observability_packet"].state == "unsafe"
    assert sources["observability_packet"].summary == "not a file"
    assert sources["otel_mapping"].state == "invalid"
    assert "invalid UTF-8" in sources["otel_mapping"].summary
    assert sources["evidence_index"].state == "invalid"
    assert "JSON artifact must be an object" in sources["evidence_index"].summary
    assert sources["runtime_card"].state == "invalid"
    assert "schema mismatch" in sources["runtime_card"].summary

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

    monkeypatch.setattr(
        adapter_readiness,
        "read_local_evidence_json_artifact_bytes",
        unreadable,
    )
    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)
    assert {source.state for source in packet.sources} == {"invalid"}

    def outside(*_args: object, **_kwargs: object) -> tuple[None, str]:
        return None, "path outside project"

    monkeypatch.setattr(
        adapter_readiness,
        "read_local_evidence_json_artifact_bytes",
        outside,
    )
    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)
    assert {source.state for source in packet.sources} == {"unsafe"}


def test_observability_adapter_readiness_source_path_resolution_failures_are_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_path(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("outside")

    monkeypatch.setattr(adapter_readiness, "first_symlink_path_component", reject_path)

    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)

    assert {source.state for source in packet.sources} == {"unsafe"}
    assert "path outside project" in {source.summary for source in packet.sources}
    assert (
        adapter_readiness._relative_display(tmp_path.parent / "outside", root=tmp_path)
        == "outside"
    )

    monkeypatch.setattr(
        adapter_readiness,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    assert (
        adapter_readiness._source_path_error(tmp_path.parent / "outside.json", root=tmp_path)
        == "path outside project"
    )


def test_observability_adapter_readiness_adapter_definitions_reference_known_sources() -> None:
    source_ids = {definition.id for definition in adapter_readiness._sources()}

    for definition in adapter_readiness._adapter_definitions():
        assert set(definition.required_source_ids) <= source_ids
        assert set(definition.optional_source_ids) <= source_ids


def test_observability_adapter_readiness_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
) -> None:
    with pytest.raises(ObservabilityAdapterReadinessError, match="Unsupported"):
        run_observability_adapter_readiness_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )
    with pytest.raises(ObservabilityAdapterReadinessError, match="must stay under"):
        run_observability_adapter_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "observability-adapter-readiness.json",
        )
    with pytest.raises(ObservabilityAdapterReadinessError, match="must not be written into"):
        run_observability_adapter_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "observability-adapter-readiness.json",
        )
    with pytest.raises(ObservabilityAdapterReadinessError, match="must not be written into"):
        run_observability_adapter_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "observability-adapter-readiness.json",
        )


def test_observability_adapter_readiness_rejects_symlinked_output_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(ObservabilityAdapterReadinessError, match="symlinked component"):
        run_observability_adapter_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "observability-adapter-readiness.json",
        )


def test_observability_adapter_readiness_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_observability_adapter_readiness_packet(project_root=tmp_path)
    monkeypatch.setattr(
        adapter_readiness,
        "build_observability_adapter_readiness_packet",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(ObservabilityAdapterReadinessError, match="contains secret-like"):
        run_observability_adapter_readiness_report(project_root=tmp_path, output="json")


def test_observability_adapter_readiness_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(adapter_readiness, "safe_write_text", fail_safe_write)

    with pytest.raises(ObservabilityAdapterReadinessError, match="disk full"):
        run_observability_adapter_readiness_report(project_root=tmp_path, output="json")


def test_observability_adapter_readiness_markdown_escapes_pipe_cells(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": r"ready\|split", "severity": "attention"},
        },
    )

    markdown = render_observability_adapter_readiness_markdown(
        build_observability_adapter_readiness_packet(project_root=tmp_path)
    )

    assert "ready&#92;\\|split" in markdown

    _write_json(
        tmp_path / "reports" / "observability-packet.json",
        {
            "schema_version": OBSERVABILITY_PACKET_SCHEMA_VERSION,
            "summary": {"status": "*bold*_under_`code`", "severity": "attention"},
        },
    )

    markdown = render_observability_adapter_readiness_markdown(
        build_observability_adapter_readiness_packet(project_root=tmp_path)
    )

    assert "&#42;bold&#42;&#95;under&#95;&#96;code&#96;" in markdown


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
