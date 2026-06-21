"""Tests for local Evidence Cloud workspace dashboard packets."""

import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence_cloud_workspace as evidence_cloud_workspace
from entroping.core.evidence_cloud_workspace import (
    EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION,
    EvidenceCloudWorkspaceError,
    build_evidence_cloud_workspace_packet,
    render_evidence_cloud_workspace_markdown,
    run_evidence_cloud_workspace_report,
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
    raw_marker: str = "raw export detail must not render",
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


def test_evidence_cloud_workspace_writes_value_free_json_from_explicit_manifests(
    tmp_path: Path,
) -> None:
    raw_marker = "customer-specific workspace detail must not render"
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

    result = run_evidence_cloud_workspace_report(
        project_root=tmp_path,
        manifests=(
            tmp_path / "reports" / "repo-a-export.json",
            tmp_path / "reports" / "repo-b-export.json",
        ),
        output="json",
    )

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-workspace.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION
    assert payload["project"] == tmp_path.name
    assert payload["summary"] == {
        "status": "partial",
        "manifests_total": 2,
        "manifests_present": 2,
        "manifests_missing": 0,
        "manifests_invalid": 0,
        "manifests_unsafe": 0,
        "repositories_total": 2,
        "repositories_ready": 1,
        "repositories_partial": 1,
        "repositories_insufficient": 0,
        "export_items_total": 4,
        "export_items_ready": 3,
        "export_items_blocked": 1,
        "boundary_controls_total": 2,
        "next_actions_total": 1,
    }
    manifests = {manifest["id"]: manifest for manifest in payload["manifests"]}
    assert manifests["manifest-1"]["project"] == "checkout-api"
    assert manifests["manifest-1"]["sha256"]
    repositories = {repo["project"]: repo for repo in payload["repositories"]}
    assert repositories["checkout-api"]["status"] == "ready"
    assert repositories["billing-api"]["status"] == "partial"
    controls = {control["id"]: control for control in payload["boundary_controls"]}
    assert controls["explicit_upload_only"]["enforced_manifests"] == 2
    assert raw_marker not in json.dumps(payload)


def test_evidence_cloud_workspace_markdown_is_escaped_and_value_free(tmp_path: Path) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout|api", raw_marker=raw_marker),
    )

    markdown = render_evidence_cloud_workspace_markdown(
        build_evidence_cloud_workspace_packet(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
        )
    )

    assert "# Entroping Evidence Cloud Workspace" in markdown
    assert "| manifest-1 | present | checkout\\|api | ready |" in markdown
    assert "| checkout\\|api | ready | 2/2 | 2/2 |" in markdown
    assert "Explicit upload only" in markdown
    assert raw_marker not in markdown
    assert "<script>" not in markdown


def test_evidence_cloud_workspace_markdown_renders_next_actions(tmp_path: Path) -> None:
    markdown = render_evidence_cloud_workspace_markdown(
        build_evidence_cloud_workspace_packet(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "missing-export.json",),
        )
    )

    assert (
        "`medium` Generate or provide manifest-1 before Evidence Cloud workspace review."
        in markdown
    )


def test_evidence_cloud_workspace_marks_missing_invalid_unsafe_and_symlinked_manifests(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "invalid-schema.json",
        {"schema_version": "entroping.evidence-cloud-export.v999"},
    )
    _write_json(
        tmp_path / "reports" / "unsafe.json",
        {
            **_export_manifest(project="unsafe-api"),
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    real_manifest = tmp_path / "reports" / "real-export.json"
    _write_json(real_manifest, _export_manifest(project="linked-api"))
    symlinked = tmp_path / "reports" / "linked-export.json"
    os.symlink(real_manifest, symlinked)

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(
            tmp_path / "reports" / "missing-export.json",
            tmp_path / "reports" / "invalid-schema.json",
            tmp_path / "reports" / "unsafe.json",
            symlinked,
        ),
    )
    manifests = {manifest.id: manifest for manifest in packet.manifests}

    assert packet.summary.status == "insufficient"
    assert manifests["manifest-1"].state == "missing"
    assert manifests["manifest-2"].state == "invalid"
    assert manifests["manifest-3"].state == "unsafe"
    assert manifests["manifest-4"].state == "unsafe"
    assert packet.repositories == ()
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_evidence_cloud_workspace_marks_forbidden_directory_oversized_and_unreadable_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = tmp_path / "envs" / "evidence-cloud-export.json"
    _write_json(forbidden, _export_manifest(project="forbidden-api"))
    directory = tmp_path / "reports" / "directory-export.json"
    directory.mkdir(parents=True)
    oversized = tmp_path / "reports" / "oversized-export.json"
    oversized.parent.mkdir(parents=True, exist_ok=True)
    oversized.write_text("{" + (" " * (1024 * 1024 + 1)) + "}", encoding="utf-8")
    unreadable = tmp_path / "reports" / "unreadable-export.json"
    _write_json(unreadable, _export_manifest(project="unreadable-api"))
    original_open = Path.open

    def fail_selected_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> object:
        if path == unreadable:
            raise OSError("blocked")
        return original_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", fail_selected_open)

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(forbidden, directory, oversized, unreadable),
    )
    manifests = {manifest.id: manifest for manifest in packet.manifests}

    assert manifests["manifest-1"].summary == "forbidden manifest path component"
    assert manifests["manifest-2"].summary == "manifest is not a file"
    assert manifests["manifest-3"].summary == "manifest too large"
    assert manifests["manifest-4"].summary == "manifest unreadable"
    assert all(manifest.state == "unsafe" for manifest in packet.manifests)


def test_evidence_cloud_workspace_allows_sha256_metadata(tmp_path: Path) -> None:
    manifest = _export_manifest(project="checkout-api")
    sources = manifest["sources"]
    assert isinstance(sources, list)
    first_source = sources[0]
    assert isinstance(first_source, dict)
    first_source["summary"] = "b" * 64
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        manifest,
    )

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(tmp_path / "reports" / "repo-a-export.json",),
    )

    assert packet.manifests[0].state == "present"
    assert packet.repositories[0].project == "checkout-api"


def test_evidence_cloud_workspace_supports_explicit_manifest_outside_project(
    tmp_path: Path,
) -> None:
    external_manifest = tmp_path.parent / f"{tmp_path.name}-evidence-cloud-export.json"
    _write_json(external_manifest, _export_manifest(project="external-api"))

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(external_manifest,),
    )

    assert packet.manifests[0].path == external_manifest.as_posix()
    assert packet.repositories[0].project == "external-api"


def test_evidence_cloud_workspace_supports_relative_manifest_paths(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(Path("reports") / "repo-a-export.json",),
    )

    assert packet.manifests[0].path == "reports/repo-a-export.json"
    assert packet.repositories[0].project == "checkout-api"


def test_evidence_cloud_workspace_summarizes_partial_boundary_controls(
    tmp_path: Path,
) -> None:
    first = _export_manifest(project="checkout-api")
    second = _export_manifest(project="billing-api")
    controls = second["boundary_controls"]
    assert isinstance(controls, list)
    first_control = controls[0]
    assert isinstance(first_control, dict)
    first_control["enforced"] = False
    _write_json(tmp_path / "reports" / "repo-a-export.json", first)
    _write_json(tmp_path / "reports" / "repo-b-export.json", second)

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(
            tmp_path / "reports" / "repo-a-export.json",
            tmp_path / "reports" / "repo-b-export.json",
        ),
    )
    controls_by_id = {control.id: control for control in packet.boundary_controls}

    assert controls_by_id["explicit_upload_only"].enforced_manifests == 1
    assert "1/2" in controls_by_id["explicit_upload_only"].summary


def test_evidence_cloud_workspace_marks_insufficient_repository_state(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(
            project="checkout-api",
            status="insufficient",
            sources_present=0,
            sources_total=2,
            export_items_ready=0,
            export_items_total=2,
            export_items_blocked=2,
        ),
    )

    packet = build_evidence_cloud_workspace_packet(
        project_root=tmp_path,
        manifests=(tmp_path / "reports" / "repo-a-export.json",),
    )

    assert packet.summary.status == "insufficient"
    assert packet.repositories[0].status == "insufficient"
    assert packet.next_actions[0].priority == "high"


def test_evidence_cloud_workspace_private_status_handles_no_repositories() -> None:
    assert (
        evidence_cloud_workspace._workspace_status(manifests=(), repositories=())
        == "insufficient"
    )


def test_evidence_cloud_workspace_private_boundary_summary_handles_empty_set() -> None:
    assert (
        evidence_cloud_workspace._boundary_summary(label="No remote API", enforced=0, total=0)
        == "No remote API has no valid manifests to summarize."
    )


def test_evidence_cloud_workspace_requires_manifest_paths(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudWorkspaceError, match="at least one export manifest"):
        build_evidence_cloud_workspace_packet(project_root=tmp_path, manifests=())


def test_evidence_cloud_workspace_rejects_output_outside_project(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    with pytest.raises(EvidenceCloudWorkspaceError, match="must stay under the project root"):
        run_evidence_cloud_workspace_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
            output_path=tmp_path.parent / "workspace.json",
        )


def test_evidence_cloud_workspace_rejects_output_under_forbidden_directory(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    with pytest.raises(EvidenceCloudWorkspaceError, match="must not be written"):
        run_evidence_cloud_workspace_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
            output_path=Path("envs") / "workspace.json",
        )


def test_evidence_cloud_workspace_writes_markdown_report(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    result = run_evidence_cloud_workspace_report(
        project_root=tmp_path,
        manifests=(tmp_path / "reports" / "repo-a-export.json",),
        output="md",
    )

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-workspace.md"
    assert "# Entroping Evidence Cloud Workspace" in result.output_path.read_text(
        encoding="utf-8"
    )


def test_evidence_cloud_workspace_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )
    monkeypatch.setattr(
        evidence_cloud_workspace,
        "_render_packet_content",
        lambda *_args, **_kwargs: "sk-proj-" + ("a" * 24),
    )

    with pytest.raises(EvidenceCloudWorkspaceError, match="contains secret-like content"):
        run_evidence_cloud_workspace_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
        )


def test_evidence_cloud_workspace_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "repo-a-export.json",
        _export_manifest(project="checkout-api"),
    )

    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(evidence_cloud_workspace, "safe_write_text", fail_write)

    with pytest.raises(EvidenceCloudWorkspaceError, match="blocked write"):
        run_evidence_cloud_workspace_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="json",
        )


def test_evidence_cloud_workspace_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudWorkspaceError, match="Unsupported"):
        run_evidence_cloud_workspace_report(
            project_root=tmp_path,
            manifests=(tmp_path / "reports" / "repo-a-export.json",),
            output="html",  # type: ignore[arg-type]
        )
