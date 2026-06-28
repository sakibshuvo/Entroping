"""Tests for local Evidence Cloud workspace HTML dashboards."""

import json
from pathlib import Path

import pytest

import entroping.core.evidence.evidence_cloud_dashboard as evidence_cloud_dashboard
from entroping.core.evidence.evidence_cloud_dashboard import (
    EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION,
    EvidenceCloudDashboardError,
    build_evidence_cloud_dashboard_packet,
    render_evidence_cloud_dashboard_html,
    run_evidence_cloud_dashboard_report,
)
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _export_manifest(
    *,
    project: str,
    status: str = "ready",
    sources_present: int = 2,
    sources_total: int = 2,
    export_items_ready: int = 2,
    export_items_total: int = 2,
    export_items_blocked: int = 0,
    boundary_controls_total: int = 2,
    raw_marker: str = "raw dashboard detail must not render",
) -> dict[str, object]:
    return {
        "schema_version": "entroping.evidence-cloud-export.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": project,
        "summary": {
            "status": status,
            "sources_total": sources_total,
            "sources_present": sources_present,
            "sources_missing": sources_total - sources_present,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "export_items_total": export_items_total,
            "export_items_ready": export_items_ready,
            "export_items_blocked": export_items_blocked,
            "boundary_controls_total": boundary_controls_total,
            "next_actions_total": 0,
        },
        "sources": [
            {
                "id": "evidence-portal-json",
                "label": "Evidence Portal JSON",
                "path": "reports/evidence-portal.json",
                "state": "present",
                "schema_version": "entroping.evidence-portal.v1",
                "sha256": "a" * 64,
                "summary": raw_marker,
            }
        ],
        "export_items": [
            {
                "id": "evidence-portal-json",
                "label": "Evidence Portal JSON",
                "source_id": "evidence-portal-json",
                "path": "reports/evidence-portal.json",
                "state": "ready" if export_items_blocked == 0 else "blocked",
                "local_reference": "entroping://evidence-cloud-export/evidence-portal-json",
                "schema_version": "entroping.evidence-portal.v1",
                "sha256": "a" * 64,
                "summary": "ready",
                "required_user_action": "Review artifact metadata before explicit upload.",
            }
        ],
        "boundary_controls": [
            {
                "id": "explicit_upload_only",
                "label": "Explicit upload only",
                "enforced": True,
                "summary": "This manifest never uploads artifacts.",
            },
            {
                "id": "no_remote_api",
                "label": "No remote API",
                "enforced": True,
                "summary": "The report does not call hosted Evidence Cloud APIs.",
            },
        ],
        "next_actions": [],
    }


def test_evidence_cloud_dashboard_writes_value_free_json_from_explicit_manifests(
    tmp_path: Path,
) -> None:
    raw_marker = "customer-specific dashboard detail must not render"
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api", raw_marker=raw_marker),
    )
    _write_json(
        tmp_path / "reports" / "repo-b-export.json",
        _export_manifest(
            project="billing-api",
            status="partial",
            sources_present=1,
            sources_total=2,
            export_items_ready=1,
            export_items_total=2,
            export_items_blocked=1,
            raw_marker=raw_marker,
        ),
    )

    result = run_evidence_cloud_dashboard_report(
        project_root=tmp_path,
        manifests=(
            tmp_path / "reports" / "repo-a-export.json",
            tmp_path / "reports" / "repo-b-export.json",
        ),
        output="json",
    )

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-dashboard.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION
    assert payload["workspace_schema_version"] == "entroping.evidence-cloud-workspace.v1"
    assert payload["summary"] == {
        "status": "partial",
        "manifests_total": 2,
        "manifests_present": 2,
        "repositories_total": 2,
        "repositories_ready": 1,
        "repositories_attention": 1,
        "export_items_total": 4,
        "export_items_ready": 3,
        "export_items_blocked": 1,
        "boundary_controls_total": 2,
        "next_actions_total": 1,
    }
    repositories = {repo["project"]: repo for repo in payload["repositories"]}
    assert repositories["checkout-api"]["dashboard_state"] == "ready"
    assert repositories["checkout-api"]["summary"] == (
        "ready; 2/2 sources present; 2/2 export items ready"
    )
    assert repositories["billing-api"]["dashboard_state"] == "attention"
    controls = {control["id"]: control for control in payload["boundary_controls"]}
    assert controls["explicit_upload_only"]["enforced_manifests"] == 2
    assert raw_marker not in json.dumps(payload)


def test_evidence_cloud_dashboard_html_is_static_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout|api", raw_marker=raw_marker),
    )

    html = render_evidence_cloud_dashboard_html(
        build_evidence_cloud_dashboard_packet(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
        )
    )

    assert html.startswith("<!doctype html>")
    assert "<h1>Entroping Evidence Cloud Dashboard</h1>" in html
    assert "checkout|api" in html
    assert "Explicit upload only" in html
    assert "SHA-256" in html
    assert "ready; 2/2 sources present; 2/2 export items ready" in html
    assert "Workspace status" in html
    assert raw_marker not in html
    assert "<script" not in html.lower()
    assert "https://" not in html


@pytest.mark.parametrize(
    "secret_like_value",
    (
        "ghp_" + "abcdefghijklmnopqrstuvwxyz123456",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "AIza" + "ABCDEFGHIJKLMNOP",
    ),
)
def test_evidence_cloud_dashboard_html_excludes_secret_like_manifest_content(
    tmp_path: Path,
    secret_like_value: str,
) -> None:
    _write_json(
        tmp_path / "reports" / "unsafe-export.json",
        _export_manifest(
            project="unsafe-api",
            raw_marker=f"raw secret-like marker {secret_like_value}",
        ),
    )

    packet = build_evidence_cloud_dashboard_packet(
        project_root=tmp_path,
        manifests=(tmp_path / "reports" / "unsafe-export.json",),
    )
    html = render_evidence_cloud_dashboard_html(packet)

    assert packet.manifests[0].state == "unsafe"
    assert packet.repositories == ()
    assert secret_like_value not in html
    assert "secret-like content" in html


def test_evidence_cloud_dashboard_writes_static_html_by_default(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    result = run_evidence_cloud_dashboard_report(
        project_root=tmp_path,
        manifests=(tmp_path / "reports" / "repo-a-export.json",),
        output="html",
    )

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-dashboard.html"
    html = result.output_path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "Repository Cards" in html


def test_evidence_cloud_dashboard_marks_missing_invalid_and_unsafe_manifests(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "invalid-export.json",
        {"schema_version": "entroping.evidence-cloud-export.v999"},
    )
    _write_json(
        tmp_path / "reports" / "unsafe-export.json",
        {
            **_export_manifest(project="unsafe-api"),
            "token": "sk-proj-" + ("a" * 24),
        },
    )

    packet = build_evidence_cloud_dashboard_packet(
        project_root=tmp_path,
        manifests=(
            tmp_path / "reports" / "missing-export.json",
            tmp_path / "reports" / "invalid-export.json",
            tmp_path / "reports" / "unsafe-export.json",
        ),
    )
    manifests = {manifest.id: manifest for manifest in packet.manifests}

    assert packet.summary.status == "insufficient"
    assert manifests["manifest-1"].state == "missing"
    assert manifests["manifest-2"].state == "invalid"
    assert manifests["manifest-3"].state == "unsafe"
    assert packet.repositories == ()
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()
    html = render_evidence_cloud_dashboard_html(packet)
    assert "No valid Evidence Cloud export manifests loaded." in html
    assert "No boundary controls available." in html


def test_evidence_cloud_dashboard_requires_manifest_paths(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudDashboardError, match="at least one export manifest"):
        build_evidence_cloud_dashboard_packet(project_root=tmp_path, manifests=())


def test_evidence_cloud_dashboard_rejects_output_outside_project(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    with pytest.raises(EvidenceCloudDashboardError, match="must stay under the project root"):
        run_evidence_cloud_dashboard_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
            output_path=tmp_path.parent / "dashboard.json",
        )


def test_evidence_cloud_dashboard_rejects_output_under_forbidden_directory(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    with pytest.raises(EvidenceCloudDashboardError, match="must not be written"):
        run_evidence_cloud_dashboard_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
            output_path=Path("envs") / "dashboard.json",
        )


def test_evidence_cloud_dashboard_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )
    monkeypatch.setattr(
        evidence_cloud_dashboard,
        "_render_packet_content",
        lambda *_args, **_kwargs: "sk-proj-" + ("a" * 24),
    )

    with pytest.raises(EvidenceCloudDashboardError, match="contains secret-like content"):
        run_evidence_cloud_dashboard_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
        )


def test_evidence_cloud_dashboard_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(evidence_cloud_dashboard, "safe_write_text", fail_write)

    with pytest.raises(EvidenceCloudDashboardError, match="blocked write"):
        run_evidence_cloud_dashboard_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
        )


def test_evidence_cloud_dashboard_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudDashboardError, match="Unsupported"):
        run_evidence_cloud_dashboard_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="md",  # type: ignore[arg-type]
        )
