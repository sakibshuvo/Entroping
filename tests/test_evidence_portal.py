"""Tests for static evidence portal reports."""

import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence.evidence_portal as evidence_portal
from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.evidence.evidence_portal import (
    EVIDENCE_PORTAL_SCHEMA_VERSION,
    EvidencePortalError,
    build_evidence_portal_packet,
    render_evidence_portal_html,
    run_evidence_portal_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path, *, raw_marker: str = "raw-portal-source") -> None:
    reports = root / "reports"
    _write_json(
        reports / "evidence-links.json",
        {
            "schema_version": "entroping.evidence-links.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "sources_total": 9,
                "sources_present": 9,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
                "targets_total": 9,
                "targets_ready": 9,
                "targets_blocked": 0,
                "surfaces_total": 6,
                "next_actions_total": 0,
            },
            "details": raw_marker,
        },
    )
    for filename, schema_version, status in (
        ("evidence-index.json", "entroping.evidence-index.v1", "ready"),
        ("runtime-card.json", "entroping.runtime-card.v1", "pass"),
        ("handoff.json", "entroping.handoff.v1", "ready"),
        ("evidence-cloud-readiness.json", "entroping.evidence-cloud-readiness.v1", "ready"),
        ("devex-readiness.json", "entroping.devex-readiness.v1", "ready"),
        ("connector-intent.json", "entroping.connector-intent.v1", "ready"),
        ("observability-packet.json", "entroping.observability-packet.v1", "ready"),
        ("test-pyramid.json", "entroping.test-pyramid-report.v1", "ready"),
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


def test_evidence_portal_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    raw_marker = "customer-specific portal detail must not render"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    result = run_evidence_portal_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "evidence-portal.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_PORTAL_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 9,
        "sources_present": 9,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "cards_total": 9,
        "cards_ready": 9,
        "cards_blocked": 0,
        "surfaces_total": 6,
        "next_actions_total": 0,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["evidence-links-json"]["sha256"]
    cards = {card["id"]: card for card in payload["cards"]}
    assert cards["evidence-links-json"]["ready_targets"] == 9
    assert cards["evidence-links-json"]["blocked_targets"] == 0
    assert cards["evidence-links-json"]["surface_count"] == 6
    assert raw_marker not in json.dumps(payload)


def test_evidence_portal_html_is_static_escaped_and_value_free(tmp_path: Path) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    html = render_evidence_portal_html(build_evidence_portal_packet(project_root=tmp_path))

    assert html.startswith("<!doctype html>")
    assert "<h1>Entroping Evidence Portal</h1>" in html
    assert "Evidence Links JSON" in html
    assert "reports/evidence-links.json" in html
    assert "Target coverage" in html
    assert raw_marker not in html
    assert "<script" not in html.lower()
    assert "https://" not in html


def test_evidence_portal_writes_static_html_by_default(tmp_path: Path) -> None:
    _write_ready_sources(tmp_path)

    result = run_evidence_portal_report(project_root=tmp_path, output="html")

    assert result.output_path == tmp_path / "reports" / "evidence-portal.html"
    html = result.output_path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "Target coverage" in html


def test_evidence_portal_marks_partial_when_some_sources_are_missing(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-links.json",
        {"schema_version": "entroping.evidence-links.v1"},
    )

    packet = build_evidence_portal_packet(project_root=tmp_path)
    cards = {card.id: card for card in packet.cards}

    assert packet.project == tmp_path.name
    assert packet.summary.status == "partial"
    assert cards["evidence-links-json"].summary == "present"
    assert cards["evidence-links-json"].ready_targets is None


def test_evidence_portal_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "evidence-links.json",
        {"schema_version": "entroping.evidence-links.v999"},
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

    packet = build_evidence_portal_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    cards = {card.id: card for card in packet.cards}

    assert packet.summary.status == "insufficient"
    assert sources["evidence-links-json"].state == "invalid"
    assert sources["runtime-card-json"].state == "unsafe"
    assert sources["handoff-json"].state == "unsafe"
    assert sources["evidence-index-json"].state == "missing"
    assert cards["evidence-links-json"].state == "blocked"
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_evidence_portal_marks_post_index_oversized_reads_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-links-json",
        label="Evidence Links JSON",
        path="reports/evidence-links.json",
        state="present",
        schema_version="entroping.evidence-links.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_portal,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_portal,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "artifact too large"),
    )

    packet = build_evidence_portal_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-links-json"].state == "unsafe"
    assert sources["evidence-links-json"].summary == "artifact too large"
    assert sources["evidence-index-json"].state == "missing"
    assert sources["evidence-index-json"].summary == "not indexed"


def test_evidence_portal_marks_post_index_invalid_read_errors_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-links-json",
        label="Evidence Links JSON",
        path="reports/evidence-links.json",
        state="present",
        schema_version="entroping.evidence-links.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_portal,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_portal,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "invalid JSON"),
    )

    packet = build_evidence_portal_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-links-json"].state == "invalid"
    assert sources["evidence-links-json"].summary == "invalid JSON"


def test_evidence_portal_marks_post_index_invalid_json_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="evidence-links-json",
        label="Evidence Links JSON",
        path="reports/evidence-links.json",
        state="present",
        schema_version="entroping.evidence-links.v1",
        summary="ready",
    )
    monkeypatch.setattr(
        evidence_portal,
        "build_local_evidence_index",
        lambda **_: (artifact,),
    )
    monkeypatch.setattr(
        evidence_portal,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b"{", ""),
    )

    packet = build_evidence_portal_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence-links-json"].state == "invalid"
    assert sources["evidence-links-json"].summary == "invalid JSON"
    assert sources["evidence-links-json"].sha256 is None


def test_evidence_portal_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidencePortalError, match="Unsupported evidence-portal output"):
        run_evidence_portal_report(
            project_root=tmp_path,
            output="md",  # type: ignore[arg-type]
        )


def test_evidence_portal_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(EvidencePortalError, match="must not be written"):
        run_evidence_portal_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "evidence-portal.json",
        )


def test_evidence_portal_rejects_output_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(EvidencePortalError, match="must stay under the project root"):
        run_evidence_portal_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-portal.json",
        )


def test_evidence_portal_wraps_safe_write_failures(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    with pytest.raises(EvidencePortalError, match="Refusing to overwrite non-file"):
        run_evidence_portal_report(
            project_root=tmp_path,
            output="json",
            output_path=reports_dir,
        )


def test_evidence_portal_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = evidence_portal.EvidencePortalPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=evidence_portal.EvidencePortalSummary(
            status="insufficient",
            sources_total=0,
            sources_present=0,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            cards_total=0,
            cards_ready=0,
            cards_blocked=0,
            surfaces_total=6,
            next_actions_total=0,
        ),
        sources=(),
        cards=(),
        next_actions=(),
    )
    monkeypatch.setattr(evidence_portal, "build_evidence_portal_packet", lambda **_: packet)

    with pytest.raises(EvidencePortalError, match="secret-like content"):
        run_evidence_portal_report(project_root=tmp_path, output="json")


def test_evidence_portal_source_rejects_invalid_sha256() -> None:
    payload = {
        "id": "evidence-links-json",
        "label": "Evidence Links JSON",
        "path": "reports/evidence-links.json",
        "state": "present",
        "schema_version": "entroping.evidence-links.v1",
        "sha256": "not-a-sha",
        "summary": "ready",
    }

    with pytest.raises(ValueError):
        evidence_portal.EvidencePortalSource.model_validate(payload)
