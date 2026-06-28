"""Tests for local Evidence Cloud export manifests."""

import json
import os
from pathlib import Path

import pytest

import entroping.core.export.evidence_cloud_export as evidence_cloud_export
from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.export.evidence_cloud_export import (
    EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION,
    EvidenceCloudExportError,
    build_evidence_cloud_export_packet,
    render_evidence_cloud_export_markdown,
    run_evidence_cloud_export_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path, *, raw_marker: str = "raw-export-source") -> None:
    reports = root / "reports"
    for filename, schema_version, status in (
        ("evidence-portal.json", "entroping.evidence-portal.v1", "ready"),
        ("evidence-links.json", "entroping.evidence-links.v1", "ready"),
        (
            "evidence-cloud-readiness.json",
            "entroping.evidence-cloud-readiness.v1",
            "ready",
        ),
        ("team-evidence-readiness.json", "entroping.team-evidence-readiness.v1", "ready"),
        ("evidence-bundle.json", "entroping.evidence-bundle.v1", "ready"),
        ("artifact-manifest.json", "entroping.report-artifact-manifest.v1", "ready"),
        ("runtime-card.json", "entroping.runtime-card.v1", "pass"),
        ("handoff.json", "entroping.handoff.v1", "ready"),
        ("integration-readiness.json", "entroping.integration-readiness.v1", "ready"),
        ("devex-readiness.json", "entroping.devex-readiness.v1", "ready"),
        ("connector-intent.json", "entroping.connector-intent.v1", "ready"),
        ("observability-packet.json", "entroping.observability-packet.v1", "ready"),
        ("evidence-index.json", "entroping.evidence-index.v1", "ready"),
    ):
        _write_json(
            reports / filename,
            {
                "schema_version": schema_version,
                "project": "checkout-api",
                "summary": {"status": status},
                "details": raw_marker,
            },
        )


def test_evidence_cloud_export_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    raw_marker = "customer-specific export detail must not render"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    result = run_evidence_cloud_export_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-export.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 13,
        "sources_present": 13,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "export_items_total": 13,
        "export_items_ready": 13,
        "export_items_blocked": 0,
        "boundary_controls_total": 8,
        "next_actions_total": 0,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["evidence-portal-json"]["sha256"]
    items = {item["id"]: item for item in payload["export_items"]}
    assert items["evidence-portal-json"]["state"] == "ready"
    assert items["evidence-portal-json"]["local_reference"] == (
        "entroping://evidence-cloud-export/evidence-portal-json"
    )
    controls = {control["id"]: control for control in payload["boundary_controls"]}
    assert controls["explicit_upload_only"]["enforced"] is True
    assert controls["no_remote_api"]["enforced"] is True
    assert raw_marker not in json.dumps(payload)


def test_evidence_cloud_export_markdown_is_escaped_and_value_free(tmp_path: Path) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    markdown = render_evidence_cloud_export_markdown(
        build_evidence_cloud_export_packet(project_root=tmp_path)
    )

    assert "# Entroping Evidence Cloud Export" in markdown
    assert "| evidence-portal-json | present | reports/evidence-portal.json |" in markdown
    assert (
        "| evidence-portal-json | ready | entroping://evidence-cloud-export/evidence-portal-json |"
    ) in markdown
    assert "Explicit upload only" in markdown
    assert raw_marker not in markdown
    assert "<script>" not in markdown


def test_evidence_cloud_export_writes_markdown_by_default(tmp_path: Path) -> None:
    _write_ready_sources(tmp_path)

    result = run_evidence_cloud_export_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-export.md"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Evidence Cloud Export" in markdown
    assert "No Evidence Cloud export actions are currently needed." in markdown


def test_evidence_cloud_export_markdown_renders_next_actions(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-portal.json",
        {
            "schema_version": "entroping.evidence-portal.v1",
            "project": "checkout-api",
            "summary": {"status": "ready"},
        },
    )

    markdown = render_evidence_cloud_export_markdown(
        build_evidence_cloud_export_packet(project_root=tmp_path)
    )

    assert "`medium` Generate Evidence Links JSON before Evidence Cloud export." in markdown


def test_evidence_cloud_export_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "evidence-portal.json",
        {"schema_version": "entroping.evidence-portal.v999"},
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass"},
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    real_handoff = reports / "real-handoff.json"
    _write_json(
        real_handoff,
        {"schema_version": "entroping.handoff.v1", "summary": {"status": "ready"}},
    )
    os.symlink(real_handoff, reports / "handoff.json")

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    items = {item.id: item for item in packet.export_items}

    assert packet.summary.status == "insufficient"
    assert sources["evidence-portal-json"].state == "invalid"
    assert sources["runtime-card-json"].state == "unsafe"
    assert sources["handoff-json"].state == "unsafe"
    assert sources["evidence-links-json"].state == "missing"
    assert items["evidence-portal-json"].state == "blocked"
    assert items["runtime-card-json"].required_user_action == (
        "Repair Runtime Card JSON before Evidence Cloud export."
    )
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_evidence_cloud_export_allows_sha256_source_metadata(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-portal.json",
        {
            "schema_version": "entroping.evidence-portal.v1",
            "project": "checkout-api",
            "summary": {"status": "ready"},
            "artifact_sha256": "a" * 64,
        },
    )

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-portal-json"].state == "present"
    assert sources["evidence-portal-json"].summary == "ready"


def test_evidence_cloud_export_marks_post_index_invalid_read_errors_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-portal-json",
        label="Evidence Portal JSON",
        path="reports/evidence-portal.json",
        state="present",
        schema_version="entroping.evidence-portal.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "lost after index"),
    )

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-portal-json"].state == "invalid"
    assert sources["evidence-portal-json"].summary == "lost after index"


def test_evidence_cloud_export_marks_post_index_invalid_json_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-portal-json",
        label="Evidence Portal JSON",
        path="reports/evidence-portal.json",
        state="present",
        schema_version="entroping.evidence-portal.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b"{", ""),
    )

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-portal-json"].state == "invalid"
    assert sources["evidence-portal-json"].summary == "invalid JSON"
    assert sources["evidence-portal-json"].sha256 is None


def test_evidence_cloud_export_marks_post_index_schema_mismatch_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-portal-json",
        label="Evidence Portal JSON",
        path="reports/evidence-portal.json",
        state="present",
        schema_version="entroping.evidence-portal.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b'{"schema_version":"wrong"}', ""),
    )

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-portal-json"].state == "invalid"
    assert sources["evidence-portal-json"].summary == "schema mismatch"
    assert sources["evidence-portal-json"].sha256 is None


def test_evidence_cloud_export_reports_partial_when_some_sources_are_ready(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-portal.json",
        {
            "schema_version": "entroping.evidence-portal.v1",
            "project": "checkout-api",
            "summary": {"status": "ready"},
        },
    )

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.sources_present == 1
    assert packet.summary.sources_missing == 12
    assert packet.summary.export_items_ready == 1
    assert packet.summary.export_items_blocked == 12


def test_evidence_cloud_export_marks_post_index_oversized_reads_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-portal-json",
        label="Evidence Portal JSON",
        path="reports/evidence-portal.json",
        state="present",
        schema_version="entroping.evidence-portal.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "artifact too large"),
    )

    packet = build_evidence_cloud_export_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-portal-json"].state == "unsafe"
    assert sources["evidence-portal-json"].summary == "artifact too large"
    assert sources["evidence-links-json"].state == "missing"
    assert sources["evidence-links-json"].summary == "not indexed"


def test_evidence_cloud_export_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudExportError, match="Unsupported evidence-cloud-export output"):
        run_evidence_cloud_export_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_evidence_cloud_export_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudExportError, match="must not be written"):
        run_evidence_cloud_export_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "evidence-cloud-export.json",
        )


def test_evidence_cloud_export_rejects_output_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudExportError, match="must stay under the project root"):
        run_evidence_cloud_export_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-cloud-export.json",
        )


def test_evidence_cloud_export_wraps_safe_write_failures(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    with pytest.raises(EvidenceCloudExportError, match="Refusing to overwrite non-file"):
        run_evidence_cloud_export_report(
            project_root=tmp_path,
            output="json",
            output_path=reports_dir,
        )


def test_evidence_cloud_export_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = evidence_cloud_export.EvidenceCloudExportPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=evidence_cloud_export.EvidenceCloudExportSummary(
            status="insufficient",
            sources_total=0,
            sources_present=0,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            export_items_total=0,
            export_items_ready=0,
            export_items_blocked=0,
            boundary_controls_total=0,
            next_actions_total=0,
        ),
        sources=(),
        export_items=(),
        boundary_controls=(),
        next_actions=(),
    )
    monkeypatch.setattr(
        evidence_cloud_export,
        "build_evidence_cloud_export_packet",
        lambda **_: packet,
    )

    with pytest.raises(EvidenceCloudExportError, match="secret-like content"):
        run_evidence_cloud_export_report(project_root=tmp_path, output="json")


def test_evidence_cloud_export_source_rejects_invalid_sha256() -> None:
    payload = {
        "id": "evidence-portal-json",
        "label": "Evidence Portal JSON",
        "path": "reports/evidence-portal.json",
        "state": "present",
        "schema_version": "entroping.evidence-portal.v1",
        "sha256": "not-a-sha",
        "summary": "ready",
    }

    with pytest.raises(ValueError):
        evidence_cloud_export.EvidenceCloudExportSource.model_validate(payload)
