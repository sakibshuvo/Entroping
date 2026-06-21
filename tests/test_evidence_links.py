"""Tests for cross-surface evidence link packets."""

import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence_links as evidence_links
from entroping.core.evidence_links import (
    EVIDENCE_LINKS_SCHEMA_VERSION,
    EvidenceLinksError,
    build_evidence_links_packet,
    render_evidence_links_markdown,
    run_evidence_links_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path, *, raw_marker: str = "raw-link-source") -> None:
    reports = root / "reports"
    for filename, schema_version, status in (
        ("evidence-index.json", "entroping.evidence-index.v1", "ready"),
        ("handoff.json", "entroping.handoff.v1", "ready"),
        ("runtime-card.json", "entroping.runtime-card.v1", "pass"),
        ("evidence-bundle.json", "entroping.evidence-bundle.v1", "ready"),
        (
            "evidence-cloud-readiness.json",
            "entroping.evidence-cloud-readiness.v1",
            "ready",
        ),
        ("notification-packet.json", "entroping.notification-packet.v1", "ready"),
        ("connector-intent.json", "entroping.connector-intent.v1", "ready"),
        ("integration-readiness.json", "entroping.integration-readiness.v1", "ready"),
        ("devex-readiness.json", "entroping.devex-readiness.v1", "ready"),
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


def test_evidence_links_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    raw_marker = "customer-specific free-form detail must not render"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    result = run_evidence_links_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "evidence-links.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_LINKS_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
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
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["runtime-card-json"]["sha256"]
    targets = {target["id"]: target for target in payload["targets"]}
    assert targets["runtime-card-json"]["link_token"] == ("entroping://evidence/runtime-card-json")
    assert targets["runtime-card-json"]["surfaces"] == [
        "cli",
        "pr",
        "desktop",
        "cloud",
        "mobile",
        "agent",
    ]
    assert raw_marker not in json.dumps(payload)


def test_evidence_links_markdown_is_escaped_and_value_free(tmp_path: Path) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    markdown = render_evidence_links_markdown(build_evidence_links_packet(project_root=tmp_path))

    assert "# Entroping Evidence Links" in markdown
    assert "| runtime-card-json | present | reports/runtime-card.json |" in markdown
    assert "| runtime-card-json | ready | entroping://evidence/runtime-card-json |" in markdown
    assert "entroping://evidence/runtime-card-json" in markdown
    assert raw_marker not in markdown
    assert "<script>" not in markdown


def test_evidence_links_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {"schema_version": "entroping.runtime-card.v999"},
    )
    _write_json(
        reports / "evidence-bundle.json",
        {
            "schema_version": "entroping.evidence-bundle.v1",
            "summary": {"status": "ready"},
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    real_handoff = reports / "real-handoff.json"
    _write_json(
        real_handoff,
        {"schema_version": "entroping.handoff.v1", "summary": {"status": "ready"}},
    )
    os.symlink(real_handoff, reports / "handoff.json")

    packet = build_evidence_links_packet(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    targets = {target.id: target for target in packet.targets}

    assert packet.summary.status == "insufficient"
    assert sources["runtime-card-json"].state == "invalid"
    assert sources["evidence-bundle-json"].state == "unsafe"
    assert sources["handoff-json"].state == "unsafe"
    assert sources["evidence-index-json"].state == "missing"
    assert targets["runtime-card-json"].state == "blocked"
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_evidence_links_reports_partial_when_some_sources_are_ready(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "project": "checkout-api",
            "summary": {"status": "pass"},
        },
    )

    packet = build_evidence_links_packet(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.sources_present == 1
    assert packet.summary.sources_missing == 8
    assert packet.summary.targets_ready == 1
    assert packet.summary.targets_blocked == 8


def test_evidence_links_uses_fallback_sources_when_index_definition_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evidence_links, "build_local_evidence_index", lambda **_: ())

    packet = build_evidence_links_packet(project_root=tmp_path)

    assert packet.sources[0].id == "evidence-index-json"
    assert packet.sources[0].label == "Evidence Index Json"
    assert packet.sources[0].path == "reports/evidence-index.json"
    assert packet.sources[0].state == "missing"
    assert packet.sources[0].summary == "not indexed"


def test_evidence_links_marks_source_invalid_when_present_file_disappears_after_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def unreadable_after_index(*args: object, **kwargs: object) -> tuple[None, str]:
        return None, "lost after index"

    monkeypatch.setattr(
        evidence_links,
        "read_local_evidence_json_artifact_bytes",
        unreadable_after_index,
    )

    packet = build_evidence_links_packet(project_root=tmp_path)

    assert packet.sources[0].state == "invalid"
    assert packet.sources[0].summary == "lost after index"
    assert packet.summary.sources_invalid == 9


def test_evidence_links_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = evidence_links.EvidenceLinksPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=evidence_links.EvidenceLinksSummary(
            status="insufficient",
            sources_total=0,
            sources_present=0,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            targets_total=0,
            targets_ready=0,
            targets_blocked=0,
            surfaces_total=6,
            next_actions_total=0,
        ),
        sources=(),
        targets=(),
        next_actions=(),
    )
    monkeypatch.setattr(evidence_links, "build_evidence_links_packet", lambda **_: packet)

    with pytest.raises(EvidenceLinksError, match="secret-like content"):
        run_evidence_links_report(project_root=tmp_path, output="json")


def test_evidence_links_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceLinksError, match="Unsupported evidence-links output"):
        run_evidence_links_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_evidence_links_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(EvidenceLinksError, match="must not be written"):
        run_evidence_links_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "evidence-links.json",
        )


def test_evidence_links_rejects_output_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(EvidenceLinksError, match="must stay under the project root"):
        run_evidence_links_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-links.json",
        )


def test_evidence_links_wraps_safe_write_failures(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    with pytest.raises(EvidenceLinksError, match="Refusing to overwrite non-file"):
        run_evidence_links_report(
            project_root=tmp_path,
            output="json",
            output_path=reports_dir,
        )


def test_evidence_links_source_rejects_invalid_sha256() -> None:
    payload = {
        "id": "runtime-card-json",
        "label": "Runtime Card JSON",
        "path": "reports/runtime-card.json",
        "state": "present",
        "schema_version": "entroping.runtime-card.v1",
        "sha256": "not-a-sha",
        "summary": "pass",
    }

    with pytest.raises(ValueError):
        evidence_links.EvidenceLinksSource.model_validate(payload)


def test_evidence_links_json_document_rejects_unsafe_documents(tmp_path: Path) -> None:
    missing = tmp_path / "reports" / "missing.json"
    assert evidence_links._json_document(missing, root=tmp_path) is None

    missing.parent.mkdir()
    secret = tmp_path / "reports" / "secret.json"
    secret.write_text(
        json.dumps({"token": "sk-proj-" + ("a" * 24)}),
        encoding="utf-8",
    )
    assert evidence_links._json_document(secret, root=tmp_path) is None

    invalid = tmp_path / "reports" / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    assert evidence_links._json_document(invalid, root=tmp_path) is None
