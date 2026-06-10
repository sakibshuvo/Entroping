"""Tests for local report artifact integrity manifests."""

import hashlib
import json
from pathlib import Path

import pytest

import entroping.core.report_artifact_manifest as artifact_manifest
from entroping.core.report_artifact_manifest import (
    REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ReportArtifactManifestError,
    write_report_artifact_manifest,
)
from entroping.core.safe_write import SafeWriteError


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _sha256(content: str) -> str:
    return hashlib.sha256(content.lstrip().encode("utf-8")).hexdigest()


def test_write_report_artifact_manifest_records_default_artifacts_with_checksums(
    tmp_path: Path,
) -> None:
    artifacts = {
        "reports/agent-bundle.json": '{"schema_version":"entroping.agent-review-bundle.v1"}\n',
        "reports/run-latest.json": '{"schema_version":"entroping.run-report.v1"}\n',
        "reports/run-plan.json": '{"schema_version":"entroping.run-plan.v1"}\n',
        "reports/junit.xml": "<testsuite tests=\"1\"></testsuite>\n",
        "reports/run-latest.html": "<!doctype html><title>Entroping</title>\n",
        "reports/drift.json": '{"schema_version":"entroping.drift-report.v1"}\n',
        "reports/entroping.sarif": '{"version":"2.1.0","runs":[]}\n',
        "reports/review-summary.md": "# Review\n",
    }
    for path, content in artifacts.items():
        _write_text(tmp_path / path, content)

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.output_path == tmp_path / "reports" / "artifact-manifest.json"
    assert result.manifest.schema_version == REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION
    assert result.manifest.summary.total_expected == 8
    assert result.manifest.summary.total_present == 8
    assert result.manifest.summary.total_missing == 0
    assert result.manifest.missing_artifacts == ()
    assert [artifact.path for artifact in result.manifest.artifacts] == sorted(artifacts)
    assert [
        (artifact.kind, artifact.path, artifact.schema_version)
        for artifact in result.manifest.artifacts
    ] == [
        ("agent_bundle", "reports/agent-bundle.json", "entroping.agent-review-bundle.v1"),
        ("drift_json", "reports/drift.json", "entroping.drift-report.v1"),
        ("sarif", "reports/entroping.sarif", "SARIF 2.1.0"),
        ("junit", "reports/junit.xml", "junit.xml"),
        ("review_summary", "reports/review-summary.md", "entroping.review-summary.md"),
        ("run_html", "reports/run-latest.html", "entroping.run-report.html"),
        ("run_json", "reports/run-latest.json", "entroping.run-report.v1"),
        ("run_plan", "reports/run-plan.json", "entroping.run-plan.v1"),
    ]
    for entry in result.manifest.artifacts:
        content = artifacts[entry.path]
        assert entry.size_bytes == len(content.lstrip().encode("utf-8"))
        assert entry.sha256 == _sha256(content)

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["artifacts"][0]["path"] == "reports/agent-bundle.json"
    assert payload["summary"] == {
        "total_expected": 8,
        "total_present": 8,
        "total_missing": 0,
    }


def test_write_report_artifact_manifest_records_missing_defaults(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.manifest.summary.total_expected == 8
    assert result.manifest.summary.total_present == 1
    assert result.manifest.summary.total_missing == 7
    assert [artifact.path for artifact in result.manifest.artifacts] == [
        "reports/run-latest.json"
    ]
    assert [missing.path for missing in result.manifest.missing_artifacts] == [
        "reports/agent-bundle.json",
        "reports/drift.json",
        "reports/entroping.sarif",
        "reports/junit.xml",
        "reports/review-summary.md",
        "reports/run-latest.html",
        "reports/run-plan.json",
    ]


def test_write_report_artifact_manifest_rejects_unsafe_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.xml"
    outside.write_text("<testsuite />\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").symlink_to(outside)

    with pytest.raises(ReportArtifactManifestError, match="symlinked component"):
        write_report_artifact_manifest(project_root=tmp_path)

    with pytest.raises(ReportArtifactManifestError, match="output path must stay inside"):
        write_report_artifact_manifest(
            project_root=tmp_path,
            output_path=tmp_path.parent / "artifact-manifest.json",
        )

    with pytest.raises(ReportArtifactManifestError, match="must not be written into .entroping"):
        write_report_artifact_manifest(
            project_root=tmp_path,
            output_path=Path(".entroping") / "artifact-manifest.json",
        )


def test_write_report_artifact_manifest_rejects_non_file_artifacts(tmp_path: Path) -> None:
    (tmp_path / "reports" / "run-latest.json").mkdir(parents=True)

    with pytest.raises(ReportArtifactManifestError, match="not a file"):
        write_report_artifact_manifest(project_root=tmp_path)


def test_write_report_artifact_manifest_rejects_invalid_default_definitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        artifact_manifest,
        "_DEFAULT_REPORT_ARTIFACTS",
        (
            artifact_manifest._ReportArtifactDefinition(
                kind="run_json",
                path=tmp_path / "reports" / "run-latest.json",
                schema_hint=None,
            ),
        ),
    )

    with pytest.raises(ReportArtifactManifestError, match="project-relative"):
        write_report_artifact_manifest(project_root=tmp_path)

    monkeypatch.setattr(
        artifact_manifest,
        "_DEFAULT_REPORT_ARTIFACTS",
        (
            artifact_manifest._ReportArtifactDefinition(
                kind="run_json",
                path=Path("../outside.json"),
                schema_hint=None,
            ),
        ),
    )

    with pytest.raises(ReportArtifactManifestError, match="must stay inside"):
        write_report_artifact_manifest(project_root=tmp_path)


def test_write_report_artifact_manifest_allows_unknown_schema_versions(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "reports" / "run-latest.json", "[]\n")
    _write_text(tmp_path / "reports" / "entroping.sarif", "[]\n")

    result = write_report_artifact_manifest(project_root=tmp_path)

    by_path = {artifact.path: artifact for artifact in result.manifest.artifacts}
    assert by_path["reports/run-latest.json"].schema_version is None
    assert by_path["reports/entroping.sarif"].schema_version is None


def test_write_report_artifact_manifest_wraps_malformed_json_artifacts(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "reports" / "run-latest.json", "{not json}\n")

    with pytest.raises(ReportArtifactManifestError, match="Could not read schema version"):
        write_report_artifact_manifest(project_root=tmp_path)


def test_write_report_artifact_manifest_wraps_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    original_read_bytes = Path.read_bytes

    def fail_read_bytes(path: Path) -> bytes:
        if path.name == "run-latest.json":
            raise OSError("read failed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    with pytest.raises(ReportArtifactManifestError, match="Could not read report artifact"):
        write_report_artifact_manifest(project_root=tmp_path)


def test_display_path_falls_back_to_absolute_path_for_external_paths(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.json"

    assert artifact_manifest._display_path(outside, root=tmp_path) == outside.as_posix()


def test_write_report_artifact_manifest_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(artifact_manifest, "safe_write_text", fail_safe_write)

    with pytest.raises(ReportArtifactManifestError, match="temporary write failed"):
        write_report_artifact_manifest(project_root=tmp_path)
