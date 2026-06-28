import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import entroping.core.notification_packet as notification_packet
from entroping.core.evidence_packet_base import EvidencePacketResult
from entroping.core.handoff_packet import HANDOFF_SCHEMA_VERSION
from entroping.core.notification_packet import (
    NotificationPacket,
    NotificationPacketError,
    build_notification_packet,
    render_notification_packet_markdown,
    run_notification_packet_report,
)
from entroping.core.safe_write import SafeWriteError


def test_run_notification_packet_writes_value_free_json_from_handoff(
    tmp_path: Path,
) -> None:
    _write_handoff(tmp_path)

    result = run_notification_packet_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "notification-packet.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.notification-packet.v1"
    assert payload["summary"] == {
        "status": "ready",
        "severity": "blocker",
        "sources_total": 6,
        "sources_present": 6,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
    }
    assert payload["project"] == "checkout-api"
    assert payload["runtime"] == {
        "status": "attention",
        "findings": 2,
        "evidence_links": 3,
        "failed_gate_ids": 1,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    handoff_path = tmp_path / "reports" / "handoff.json"
    assert sources["handoff"] == {
        "id": "handoff",
        "label": "Cross-surface handoff",
        "path": "reports/handoff.json",
        "state": "present",
        "schema_version": "entroping.handoff.v1",
        "sha256": hashlib.sha256(handoff_path.read_bytes()).hexdigest(),
        "summary": "ready handoff evidence",
    }
    assert {message["surface"] for message in payload["messages"]} == {
        "jira",
        "linear",
        "monday",
        "slack",
        "discord",
        "workato",
        "agent",
    }
    jira = next(message for message in payload["messages"] if message["surface"] == "jira")
    assert jira["severity"] == "blocker"
    assert jira["artifact_paths"] == [
        "reports/notification-packet.json",
        "reports/handoff.json",
        "reports/runtime-card.json",
        "reports/evidence-bundle.json",
        "reports/pilot-metrics.json",
        "reports/artifact-manifest.json",
        "reports/test-pyramid.json",
    ]
    assert "sk-proj" not in json.dumps(payload)


def test_notification_packet_falls_back_to_runtime_card_when_handoff_missing(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
            "run": {"project": "checkout-api", "failed_gate_ids": []},
        },
    )

    result = run_notification_packet_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "notification-packet.md"
    assert result.packet.summary.status == "partial"
    assert result.packet.summary.severity == "attention"
    sources = {source.id: source for source in result.packet.sources}
    assert sources["handoff"].state == "missing"
    assert sources["runtime_card"].state == "present"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Notification Packet" in markdown
    assert "| jira | blocker |" not in markdown
    assert "| jira | attention |" in markdown


def test_notification_packet_marks_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(reports / "handoff.json", {"schema_version": "wrong"})
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
            "secret": "sk-proj-" + ("a" * 24),
        },
    )
    (reports / "evidence-bundle.json").mkdir()
    real_pilot = reports / "pilot-source.json"
    _write_json(
        real_pilot,
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "summary": {"status": "partial"},
        },
    )
    os.symlink(real_pilot, reports / "pilot-metrics.json")
    (reports / "artifact-manifest.json").write_text("not json\n", encoding="utf-8")

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "invalid"
    assert sources["runtime_card"].state == "unsafe"
    assert sources["evidence_bundle"].state == "unsafe"
    assert sources["pilot_metrics"].state == "unsafe"
    assert sources["artifact_manifest"].state == "invalid"
    assert packet.summary.status == "insufficient"
    assert packet.summary.severity == "attention"
    assert "sk-proj" not in packet.model_dump_json()


def test_notification_packet_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(NotificationPacketError, match="Unsupported notification output"):
        run_notification_packet_report(project_root=tmp_path, output="html")  # type: ignore[arg-type]
    with pytest.raises(NotificationPacketError, match="must stay under"):
        run_notification_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "notification-packet.json",
        )
    with pytest.raises(NotificationPacketError, match="must not be written into"):
        run_notification_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "notification-packet.json",
        )
    monkeypatch.setattr(
        notification_packet,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(NotificationPacketError, match="must stay under"):
        run_notification_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-notification-packet.json",
        )


def test_notification_packet_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(NotificationPacketError, match="symlinked component"):
        run_notification_packet_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "notification-packet.json",
        )


def test_notification_packet_marks_unsafe_handoff_source_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_reports = tmp_path / "real-reports"
    real_reports.mkdir()
    os.symlink(real_reports, tmp_path / "reports")

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "unsafe"
    assert "symlinked component" in sources["handoff"].summary

    reports_link = tmp_path / "reports"
    reports_link.unlink()
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "handoff.json").mkdir()

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "unsafe"
    assert "not a file" in sources["handoff"].summary

    def reject_path(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("outside")

    monkeypatch.setattr(notification_packet, "first_symlink_path_component", reject_path)

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "unsafe"
    assert "must stay under" in sources["handoff"].summary


def test_notification_packet_marks_invalid_handoff_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "handoff.json").write_bytes(b"\xff")

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "invalid"
    assert "UTF-8" in sources["handoff"].summary

    (reports / "handoff.json").write_text("[]\n", encoding="utf-8")

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "invalid"
    assert "JSON object" in sources["handoff"].summary

    (reports / "handoff.json").write_text(
        json.dumps({"schema_version": HANDOFF_SCHEMA_VERSION, "token": "sk-proj-" + ("a" * 24)}),
        encoding="utf-8",
    )

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "unsafe"
    assert "secret-like content" in sources["handoff"].summary

    _write_handoff(tmp_path)
    monkeypatch.setattr(notification_packet, "_MAX_NOTIFICATION_ARTIFACT_BYTES", 1)

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "invalid"
    assert "exceeds 1 bytes" in sources["handoff"].summary


def test_notification_packet_marks_unreadable_handoff_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_handoff(tmp_path)

    def unreadable(self: Path) -> bytes:
        if self.name == "handoff.json":
            raise OSError("permission denied")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", unreadable)

    packet = build_notification_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["handoff"].state == "invalid"
    assert "Could not read handoff packet" in sources["handoff"].summary


def test_notification_packet_uses_runtime_status_for_severity(tmp_path: Path) -> None:
    _write_handoff(tmp_path, runtime_status="fail", failed_gate_ids=0)

    packet = build_notification_packet(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "blocker"

    _write_handoff(tmp_path, runtime_status="warning", failed_gate_ids=0)

    packet = build_notification_packet(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "attention"


def test_notification_packet_markdown_handles_missing_runtime(tmp_path: Path) -> None:
    _write_handoff(tmp_path, runtime=None)

    markdown = render_notification_packet_markdown(
        build_notification_packet(project_root=tmp_path)
    )

    assert "No runtime summary is available." in markdown


def test_notification_packet_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_notification_packet(project_root=tmp_path)
    monkeypatch.setattr(
        notification_packet,
        "build_notification_packet",
        lambda **_: packet.model_copy(
            update={"project": "sk-proj-" + ("a" * 24)}
        ),
    )

    with pytest.raises(NotificationPacketError, match="contains secret-like content"):
        run_notification_packet_report(project_root=tmp_path, output="json")


def test_notification_packet_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(notification_packet, "safe_write_text", fail_safe_write)

    with pytest.raises(NotificationPacketError, match="disk full"):
        run_notification_packet_report(project_root=tmp_path, output="json")


def test_notification_packet_report_uses_shared_evidence_packet_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[NotificationPacket] = []

    def fake_safe_write_text(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("shared writer should receive but not call this sentinel")

    def fake_write_evidence_packet_report(
        *,
        project_root: Path,
        output: str,
        output_path: Path,
        packet: NotificationPacket,
        render_markdown: Callable[[NotificationPacket], str],
        has_secret_content: Callable[[str], bool],
        unsafe_content_message: str,
        artifact: str,
        error_type: type[Exception],
        safe_write: Callable[..., Path],
    ) -> EvidencePacketResult[NotificationPacket]:
        assert project_root == tmp_path.resolve()
        assert output == "md"
        assert output_path == tmp_path / "reports" / "notification-packet.md"
        assert render_markdown is render_notification_packet_markdown
        assert has_secret_content is notification_packet._contains_unredacted_secret_like_value
        assert unsafe_content_message == "notification packet contains secret-like content"
        assert artifact == "notification packet"
        assert error_type is NotificationPacketError
        assert safe_write is fake_safe_write_text
        calls.append(packet)
        return EvidencePacketResult(output_path=output_path, packet=packet)

    monkeypatch.setattr(
        notification_packet,
        "safe_write_text",
        fake_safe_write_text,
    )
    monkeypatch.setattr(
        notification_packet,
        "write_evidence_packet_report",
        fake_write_evidence_packet_report,
        raising=False,
    )

    result = run_notification_packet_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "notification-packet.md"
    assert result.packet is calls[0]


def test_notification_markdown_escapes_backslash_pipe_cells(tmp_path: Path) -> None:
    _write_handoff(tmp_path, runtime_status=r"attention\|split")

    markdown = render_notification_packet_markdown(
        build_notification_packet(project_root=tmp_path)
    )

    assert "attention&#92;\\|split" in markdown


def _write_handoff(
    root: Path,
    *,
    runtime: dict[str, Any] | None | object = ...,
    runtime_status: str = "attention",
    failed_gate_ids: int = 1,
) -> None:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    runtime_payload = (
        {
            "status": runtime_status,
            "findings": 2,
            "evidence_links": 3,
            "failed_gate_ids": failed_gate_ids,
            "pilot_readiness_status": "ready",
            "test_pyramid_status": "complete",
        }
        if runtime is ...
        else runtime
    )
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "generated_at": "2026-06-20T00:00:00+00:00",
            "project": "checkout-api",
            "git": {"branch": "main", "commit": "a" * 40},
            "summary": {
                "status": "ready",
                "artifacts_total": 5,
                "artifacts_present": 5,
                "artifacts_missing": 0,
                "artifacts_invalid": 0,
                "artifacts_unsafe": 0,
            },
            "runtime": runtime_payload,
            "artifacts": [
                _artifact("runtime_card", "Runtime card", "reports/runtime-card.json"),
                _artifact("evidence_bundle", "Evidence bundle", "reports/evidence-bundle.json"),
                _artifact("pilot_metrics", "Pilot metrics", "reports/pilot-metrics.json"),
                _artifact(
                    "artifact_manifest",
                    "Artifact manifest",
                    "reports/artifact-manifest.json",
                ),
                _artifact("test_pyramid", "Test pyramid", "reports/test-pyramid.json"),
            ],
            "targets": [
                {
                    "id": "cli",
                    "label": "CLI",
                    "next_action": "Open the local handoff packet.",
                    "artifact_paths": ["reports/handoff.json"],
                }
            ],
        },
    )


def _artifact(artifact_id: str, label: str, path: str) -> dict[str, object]:
    return {
        "id": artifact_id,
        "label": label,
        "path": path,
        "state": "present",
        "schema_version": f"entroping.{artifact_id}.v1",
        "sha256": "b" * 64,
        "summary": "present evidence",
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
