import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

import entroping.core.evidence.observability_packet as observability_packet
from entroping.core.evidence.observability_packet import (
    ObservabilityPacket,
    ObservabilityPacketError,
    build_observability_packet,
    render_observability_packet_markdown,
    run_observability_packet_report,
)
from entroping.core.evidence_packet_base import EvidencePacketResult
from entroping.core.report_schema_versions import EVIDENCE_INDEX_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError
from entroping.core.structured_diagnostics import (
    STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
    DiagnosticSeverity,
    build_diagnostic_event,
    diagnostic_event_to_dict,
)


def test_run_observability_packet_writes_value_free_json_from_local_evidence(
    tmp_path: Path,
) -> None:
    diagnostics_path = _write_diagnostics(
        tmp_path,
        [
            _event(
                component="run",
                operation="execute",
                severity="error",
                code="hurl.timeout",
                summary="Hurl timeout recorded.",
                attributes={"failed_gates": 1, "artifact_path": "reports/run-latest.json"},
            ),
            _event(
                component="report",
                operation="runtime_card",
                severity="warning",
                code="evidence.partial",
                summary="Runtime evidence needs review.",
                attributes={"findings": 2},
            ),
            _event(
                component="report",
                operation="runtime_card",
                severity="info",
                code="evidence.ready",
                summary="Runtime card created.",
            ),
        ],
    )
    _write_runtime_card(tmp_path, status="attention", failed_gate_ids=("latency-budget",))
    _write_evidence_index(tmp_path)

    result = run_observability_packet_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "observability-packet.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.observability-packet.v1"
    assert payload["summary"] == {
        "status": "ready",
        "severity": "blocker",
        "sources_total": 3,
        "sources_present": 3,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "events_total": 3,
        "debug_events": 0,
        "info_events": 1,
        "warning_events": 1,
        "error_events": 1,
    }
    assert payload["project"] == "checkout-api"
    assert payload["runtime"] == {
        "status": "attention",
        "findings": 2,
        "evidence_links": 3,
        "failed_gate_ids": 1,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["diagnostics"] == {
        "id": "diagnostics",
        "label": "Structured diagnostics",
        "path": ".entroping/latest-diagnostics.jsonl",
        "state": "present",
        "schema_version": STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
        "sha256": hashlib.sha256(diagnostics_path.read_bytes()).hexdigest(),
        "summary": "3 diagnostic events.",
    }
    assert sources["runtime_card"]["state"] == "present"
    assert sources["evidence_index"]["state"] == "present"
    components = {component["component"]: component for component in payload["components"]}
    assert components["run"] == {
        "component": "run",
        "events_total": 1,
        "debug_events": 0,
        "info_events": 0,
        "warning_events": 0,
        "error_events": 1,
        "operations": ["execute"],
        "codes": ["hurl.timeout"],
    }
    assert {message["surface"] for message in payload["messages"]} == {
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic",
    }
    opentelemetry = next(
        message for message in payload["messages"] if message["surface"] == "opentelemetry"
    )
    assert opentelemetry["severity"] == "blocker"
    assert opentelemetry["artifact_paths"] == [
        "reports/observability-packet.json",
        ".entroping/latest-diagnostics.jsonl",
        "reports/runtime-card.json",
        "reports/evidence-index.json",
    ]
    serialized = json.dumps(payload)
    assert "sk-proj" not in serialized
    assert "latency-budget" not in serialized


def test_observability_packet_links_runtime_governance_anchor_metadata(
    tmp_path: Path,
) -> None:
    diagnostics_path = _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    _write_runtime_card(tmp_path)
    evidence_index_path = _write_evidence_index(tmp_path, status="partial")

    result = run_observability_packet_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["evidence_index"] == {
        "id": "evidence_index",
        "label": "Evidence index",
        "path": "reports/evidence-index.json",
        "state": "present",
        "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
        "sha256": hashlib.sha256(evidence_index_path.read_bytes()).hexdigest(),
        "summary": "partial evidence index",
    }
    opentelemetry = next(
        message for message in payload["messages"] if message["surface"] == "opentelemetry"
    )
    assert opentelemetry["artifact_paths"] == [
        "reports/observability-packet.json",
        ".entroping/latest-diagnostics.jsonl",
        "reports/runtime-card.json",
        "reports/evidence-index.json",
    ]
    serialized = json.dumps(payload)
    assert hashlib.sha256(diagnostics_path.read_bytes()).hexdigest() in serialized
    assert "raw-artifact-marker" not in serialized


def test_observability_packet_marks_missing_evidence_index_as_nonfatal_gap(
    tmp_path: Path,
) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    _write_runtime_card(tmp_path, status="pass")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "missing"
    assert sources["evidence_index"].summary == "Evidence index is missing."
    assert packet.summary.status == "partial"
    assert packet.summary.severity == "attention"
    opentelemetry = next(
        message for message in packet.messages if message.surface == "opentelemetry"
    )
    assert opentelemetry.artifact_paths == (
        "reports/observability-packet.json",
        ".entroping/latest-diagnostics.jsonl",
        "reports/runtime-card.json",
    )


def test_observability_packet_falls_back_to_diagnostics_when_runtime_missing(
    tmp_path: Path,
) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )

    result = run_observability_packet_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "observability-packet.md"
    assert result.packet.summary.status == "partial"
    assert result.packet.summary.severity == "attention"
    sources = {source.id: source for source in result.packet.sources}
    assert sources["diagnostics"].state == "present"
    assert sources["runtime_card"].state == "missing"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Observability Packet" in markdown
    assert "| opentelemetry | attention |" in markdown


def test_observability_packet_marks_invalid_and_unsafe_sources(tmp_path: Path) -> None:
    diagnostics_dir = tmp_path / ".entroping"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "latest-diagnostics.jsonl").write_text("{bad json}\n", encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
            "secret": "sk-proj-" + ("a" * 24),
        },
    )

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "invalid"
    assert sources["runtime_card"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.severity == "attention"
    assert "sk-proj" not in packet.model_dump_json()


def test_observability_packet_marks_unsafe_source_paths(tmp_path: Path) -> None:
    real_state = tmp_path / "real-entroping"
    real_state.mkdir()
    os.symlink(real_state, tmp_path / ".entroping")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "unsafe"
    assert "symlinked component" in sources["diagnostics"].summary

    entroping_link = tmp_path / ".entroping"
    entroping_link.unlink()
    diagnostics_dir = tmp_path / ".entroping"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "latest-diagnostics.jsonl").mkdir()

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "unsafe"
    assert "not a file" in sources["diagnostics"].summary


def test_observability_packet_marks_source_resolution_failures_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_path(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("outside")

    monkeypatch.setattr(observability_packet, "first_symlink_path_component", reject_path)

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "unsafe"
    assert sources["runtime_card"].state == "unsafe"
    assert "must stay under" in sources["diagnostics"].summary


def test_observability_packet_marks_bad_diagnostics_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_dir = tmp_path / ".entroping"
    diagnostics_dir.mkdir()
    diagnostics_path = diagnostics_dir / "latest-diagnostics.jsonl"
    diagnostics_path.write_bytes(b"\xff")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "invalid"
    assert "UTF-8" in sources["diagnostics"].summary

    diagnostics_path.write_text("sk-proj-" + ("a" * 24), encoding="utf-8")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "unsafe"
    assert "secret-like content" in sources["diagnostics"].summary

    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    monkeypatch.setattr(observability_packet, "_MAX_OBSERVABILITY_ARTIFACT_BYTES", 1)

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "invalid"
    assert "exceeds 1 bytes" in sources["diagnostics"].summary


def test_observability_packet_marks_unreadable_diagnostics_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )

    def unreadable(self: Path) -> bytes:
        if self.name == "latest-diagnostics.jsonl":
            raise OSError("permission denied")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", unreadable)

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["diagnostics"].state == "invalid"
    assert "Could not read structured diagnostics log" in sources["diagnostics"].summary


def test_observability_packet_marks_bad_runtime_card_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    runtime_path = reports / "runtime-card.json"
    runtime_path.write_bytes(b"\xff")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["runtime_card"].state == "invalid"
    assert "UTF-8" in sources["runtime_card"].summary

    runtime_path.write_text("[]\n", encoding="utf-8")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["runtime_card"].state == "invalid"
    assert "JSON object" in sources["runtime_card"].summary

    _write_json(runtime_path, {"schema_version": "wrong"})

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["runtime_card"].state == "invalid"
    assert "unsupported schema" in sources["runtime_card"].summary

    runtime_path.write_text("{bad json}\n", encoding="utf-8")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["runtime_card"].state == "invalid"
    assert "Invalid runtime card" in sources["runtime_card"].summary

    _write_runtime_card(tmp_path)
    monkeypatch.setattr(observability_packet, "_MAX_OBSERVABILITY_ARTIFACT_BYTES", 1)

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["runtime_card"].state == "invalid"
    assert "exceeds 1 bytes" in sources["runtime_card"].summary


def test_observability_packet_marks_unreadable_runtime_card_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    _write_runtime_card(tmp_path)

    def unreadable(self: Path) -> bytes:
        if self.name == "runtime-card.json":
            raise OSError("permission denied")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", unreadable)

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["runtime_card"].state == "invalid"
    assert "Could not read runtime card" in sources["runtime_card"].summary


def test_observability_packet_marks_bad_evidence_index_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    _write_runtime_card(tmp_path)
    evidence_path = tmp_path / "reports" / "evidence-index.json"
    evidence_path.write_bytes(b"\xff")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "invalid"
    assert "UTF-8" in sources["evidence_index"].summary

    evidence_path.write_text("sk-proj-" + ("a" * 24), encoding="utf-8")

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "unsafe"
    assert "secret-like content" in sources["evidence_index"].summary

    _write_json(evidence_path, {"schema_version": "wrong"})

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "invalid"
    assert "unsupported schema" in sources["evidence_index"].summary

    _write_json(
        evidence_path,
        {"schema_version": EVIDENCE_INDEX_SCHEMA_VERSION, "summary": "ready"},
    )

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "invalid"
    assert "summary must be a JSON object" in sources["evidence_index"].summary

    _write_json(
        evidence_path,
        {
            "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
            "summary": {"status": "unknown"},
        },
    )

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "invalid"
    assert "summary status is missing or unsupported" in sources["evidence_index"].summary

    _write_evidence_index(tmp_path)
    monkeypatch.setattr(observability_packet, "_MAX_OBSERVABILITY_ARTIFACT_BYTES", 1)

    packet = build_observability_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_index"].state == "invalid"
    assert "exceeds 1 bytes" in sources["evidence_index"].summary


def test_observability_packet_uses_runtime_status_for_severity(tmp_path: Path) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="doctor",
                operation="ci",
                severity="info",
                code="doctor.ready",
                summary="Doctor readiness is available.",
            )
        ],
    )
    _write_runtime_card(tmp_path, status="pass", failed_gate_ids=("latency-budget",))
    _write_evidence_index(tmp_path)

    packet = build_observability_packet(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "blocker"

    _write_runtime_card(tmp_path, status="fail", failed_gate_ids=())

    packet = build_observability_packet(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "blocker"

    _write_runtime_card(tmp_path, status="attention", failed_gate_ids=())

    packet = build_observability_packet(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "attention"

    _write_runtime_card(tmp_path, status="pass", failed_gate_ids=())

    packet = build_observability_packet(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "info"
    markdown = render_observability_packet_markdown(packet)
    assert "- Runtime status: `pass`" in markdown
    assert "Entroping observability evidence is ready" in markdown


def test_observability_packet_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ObservabilityPacketError, match="Unsupported observability output"):
        run_observability_packet_report(project_root=tmp_path, output="html")
    with pytest.raises(ObservabilityPacketError, match="must stay under"):
        run_observability_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "observability-packet.json",
        )
    with pytest.raises(ObservabilityPacketError, match="must not be written into"):
        run_observability_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "observability-packet.json",
        )
    monkeypatch.setattr(
        observability_packet,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(ObservabilityPacketError, match="must stay under"):
        run_observability_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-observability-packet.json",
        )


def test_observability_packet_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(ObservabilityPacketError, match="symlinked component"):
        run_observability_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "observability-packet.json",
        )


def test_observability_packet_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_observability_packet(project_root=tmp_path)
    monkeypatch.setattr(
        observability_packet,
        "build_observability_packet",
        lambda **_: packet.model_copy(
            update={"project": "sk-proj-" + ("a" * 24)}
        ),
    )

    with pytest.raises(ObservabilityPacketError, match="contains secret-like content"):
        run_observability_packet_report(project_root=tmp_path, output="json")


def test_observability_packet_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(observability_packet, "safe_write_text", fail_safe_write)

    with pytest.raises(ObservabilityPacketError, match="disk full"):
        run_observability_packet_report(project_root=tmp_path, output="json")


def test_observability_packet_report_uses_shared_evidence_packet_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[ObservabilityPacket] = []

    def fake_safe_write_text(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("shared writer should receive but not call this sentinel")

    def fake_write_evidence_packet_report(
        *,
        project_root: Path,
        output: str,
        output_path: Path,
        packet: ObservabilityPacket,
        render_markdown: Callable[[ObservabilityPacket], str],
        has_secret_content: Callable[[str], bool],
        unsafe_content_message: str,
        artifact: str,
        error_type: type[Exception],
        safe_write: Callable[..., Path],
    ) -> EvidencePacketResult[ObservabilityPacket]:
        assert project_root == tmp_path.resolve()
        assert output == "md"
        assert output_path == tmp_path / "reports" / "observability-packet.md"
        assert render_markdown is render_observability_packet_markdown
        assert has_secret_content("sk-proj-" + ("a" * 24)) is True
        assert has_secret_content("safe evidence") is False
        assert unsafe_content_message == "observability packet contains secret-like content"
        assert artifact == "observability packet"
        assert error_type is ObservabilityPacketError
        assert safe_write is fake_safe_write_text
        calls.append(packet)
        return EvidencePacketResult(output_path=output_path, packet=packet)

    monkeypatch.setattr(
        observability_packet,
        "safe_write_text",
        fake_safe_write_text,
    )
    monkeypatch.setattr(
        observability_packet,
        "write_evidence_packet_report",
        fake_write_evidence_packet_report,
        raising=False,
    )

    result = run_observability_packet_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "observability-packet.md"
    assert result.packet is calls[0]


def test_observability_markdown_escapes_backslash_pipe_cells(tmp_path: Path) -> None:
    _write_diagnostics(
        tmp_path,
        [
            _event(
                component="report",
                operation="runtime_card",
                severity="warning",
                code="evidence.partial",
                summary=r"warning\|split",
            )
        ],
    )

    markdown = render_observability_packet_markdown(
        build_observability_packet(project_root=tmp_path)
    )

    assert "warning&#92;\\|split" in markdown


def _event(
    *,
    component: str,
    operation: str,
    severity: DiagnosticSeverity,
    code: str,
    summary: str,
    attributes: dict[str, object] | None = None,
) -> dict[str, object]:
    return diagnostic_event_to_dict(
        build_diagnostic_event(
            component=component,
            operation=operation,
            severity=severity,
            code=code,
            summary=summary,
            attributes=attributes,
            timestamp="2026-06-20T00:00:00+00:00",
        )
    )


def _write_diagnostics(root: Path, events: list[dict[str, object]]) -> Path:
    diagnostics_dir = root / ".entroping"
    diagnostics_dir.mkdir(exist_ok=True)
    path = diagnostics_dir / "latest-diagnostics.jsonl"
    path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    return path


def _write_runtime_card(
    root: Path,
    *,
    status: str = "pass",
    failed_gate_ids: tuple[str, ...] = (),
) -> None:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
            "summary": {
                "status": status,
                "findings": 2,
                "evidence_links": 3,
            },
            "run": {
                "project": "checkout-api",
                "environment": "ci",
                "total": 3,
                "passed": 2,
                "failed": 1 if failed_gate_ids else 0,
                "exit_code": 1 if failed_gate_ids else 0,
                "failed_tests": 1 if failed_gate_ids else 0,
                "failed_gate_ids": list(failed_gate_ids),
            },
            "drift": {
                "status": "none",
                "findings": 0,
                "drifted": 0,
                "missing_baseline": False,
            },
            "redaction": {
                "status": "verified",
                "total_records": 0,
                "redacted_records": 0,
                "unredacted_records": 0,
                "low_confidence_categories": [],
            },
            "release": {
                "artifact_manifest_audit_status": "verified",
                "evidence_bundle_status": "ready",
                "evidence_links": ["reports/evidence-bundle.json"],
            },
            "pilot_readiness": {
                "status": "ready",
                "path": "reports/evidence-bundle.json",
                "missing_artifacts": 0,
                "invalid_artifacts": 0,
                "checksum_mismatches": 0,
                "diagnostics": 0,
                "manifest_audit_status": "verified",
            },
            "test_pyramid": {
                "status": "complete",
                "path": "reports/test-pyramid.json",
                "total_layers": 6,
                "present_layers": 6,
                "attention_layers": 0,
                "findings": 0,
            },
            "agent_provenance": {
                "status": "pass",
                "configured_roles": 3,
                "manifests": 3,
                "findings": 0,
            },
            "artifacts": [],
            "findings": [],
        },
    )


def _write_evidence_index(root: Path, *, status: str = "ready") -> Path:
    path = root / "reports" / "evidence-index.json"
    _write_json(
        path,
        {
            "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
            "generated_at": "2026-06-20T00:00:00+00:00",
            "project": "checkout-api",
            "summary": {
                "status": status,
                "artifacts_total": 1,
                "artifacts_present": 1,
                "artifacts_missing": 0,
                "artifacts_invalid": 0,
                "artifacts_unsafe": 0,
            },
            "artifacts": [
                {
                    "id": "runtime-card-json",
                    "label": "Runtime Card JSON",
                    "path": "reports/runtime-card.json",
                    "state": "present",
                    "schema_version": RUNTIME_CARD_SCHEMA_VERSION,
                    "summary": "raw-artifact-marker",
                }
            ],
        },
    )
    return path


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
