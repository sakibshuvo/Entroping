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


def _chain_path(root: Path) -> Path:
    return root / ".entroping" / "report-audit-chain.jsonl"


def _audit_event_line(event: dict[str, object]) -> str:
    payload = {key: value for key, value in event.items() if key != "event_hash"}
    return json.dumps(
        {
            **payload,
            "event_hash": artifact_manifest._hash_audit_event_payload(payload),
        },
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


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
    assert payload["audit"]["chain_path"] == ".entroping/report-audit-chain.jsonl"
    assert payload["audit"]["verification"] == {
        "status": "verified",
        "checked_events": 1,
        "latest_event_hash": payload["audit"]["event"]["event_hash"],
        "diagnostics": [],
    }


def test_write_report_artifact_manifest_appends_tamper_evident_audit_events(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )

    first = write_report_artifact_manifest(project_root=tmp_path)
    _write_text(
        tmp_path / "reports" / "run-plan.json",
        '{"schema_version":"entroping.run-plan.v1"}\n',
    )
    second = write_report_artifact_manifest(project_root=tmp_path)

    chain_path = _chain_path(tmp_path)
    chain = [
        json.loads(line)
        for line in chain_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert first.manifest.audit.chain_path == ".entroping/report-audit-chain.jsonl"
    assert first.manifest.audit.verification.status == "verified"
    assert first.manifest.audit.event is not None
    assert second.manifest.audit.verification.status == "verified"
    assert second.manifest.audit.event is not None
    assert [event["sequence"] for event in chain] == [1, 2]
    assert chain[0]["previous_event_hash"] is None
    assert chain[1]["previous_event_hash"] == chain[0]["event_hash"]
    assert chain[1]["event_hash"] == second.manifest.audit.event.event_hash
    assert chain[1]["command"] == {
        "name": "entroping report artifact-manifest",
        "output_path": "reports/artifact-manifest.json",
    }
    assert chain[1]["artifacts"] == [
        {
            "kind": "run_json",
            "path": "reports/run-latest.json",
            "schema_version": "entroping.run-report.v1",
            "size_bytes": 45,
            "sha256": _sha256('{"schema_version":"entroping.run-report.v1"}\n'),
        },
        {
            "kind": "run_plan",
            "path": "reports/run-plan.json",
            "schema_version": "entroping.run-plan.v1",
            "size_bytes": 43,
            "sha256": _sha256('{"schema_version":"entroping.run-plan.v1"}\n'),
        },
    ]


def test_write_report_artifact_manifest_reports_broken_existing_audit_chain(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    write_report_artifact_manifest(project_root=tmp_path)
    chain_path = tmp_path / ".entroping" / "report-audit-chain.jsonl"
    tampered = chain_path.read_text(encoding="utf-8").replace(
        "entroping.run-report.v1",
        "entroping.run-report.v9",
    )
    chain_path.write_text(tampered, encoding="utf-8")

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.manifest.audit.verification.status == "broken"
    assert result.manifest.audit.verification.checked_events == 1
    assert result.manifest.audit.verification.latest_event_hash is None
    assert result.manifest.audit.verification.diagnostics == (
        "line 1 event hash mismatch",
    )
    assert result.manifest.audit.event is None
    assert len(chain_path.read_text(encoding="utf-8").splitlines()) == 1


def test_write_report_artifact_manifest_redacts_secret_like_audit_metadata(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"password=live-secret"}\n',
    )

    result = write_report_artifact_manifest(
        project_root=tmp_path,
        output_path=Path("reports") / "token=live-secret.json",
    )

    assert result.manifest.artifacts[0].schema_version == "password=[REDACTED]"
    payload = result.output_path.read_text(encoding="utf-8")
    chain = _chain_path(tmp_path).read_text(encoding="utf-8")
    assert "live-secret" not in payload
    assert "live-secret" not in chain
    assert "token=[REDACTED]" in payload
    assert "token=[REDACTED]" in chain


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


def test_write_report_artifact_manifest_rejects_non_file_audit_chain(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    _chain_path(tmp_path).mkdir(parents=True)

    with pytest.raises(ReportArtifactManifestError, match="audit chain path is not a file"):
        write_report_artifact_manifest(project_root=tmp_path)


def test_write_report_artifact_manifest_wraps_audit_chain_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    write_report_artifact_manifest(project_root=tmp_path)
    original_read_text = Path.read_text

    def fail_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == _chain_path(tmp_path):
            raise OSError("read failed")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(ReportArtifactManifestError, match="Could not read report audit chain"):
        write_report_artifact_manifest(project_root=tmp_path)


@pytest.mark.parametrize(
    ("chain_content", "diagnostic"),
    (
        ("{not json}\n", "line 1 invalid JSON"),
        ("[]\n", "line 1 is not an object"),
        ('{"schema_version":"entroping.report-audit-event.v1"}\n', "line 1 missing event hash"),
    ),
)
def test_write_report_artifact_manifest_reports_malformed_audit_chain_lines(
    tmp_path: Path,
    chain_content: str,
    diagnostic: str,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    _write_text(_chain_path(tmp_path), chain_content)

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.manifest.audit.verification.status == "broken"
    assert result.manifest.audit.verification.diagnostics == (diagnostic,)


def test_write_report_artifact_manifest_reports_previous_hash_mismatch(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    write_report_artifact_manifest(project_root=tmp_path)
    event = json.loads(_chain_path(tmp_path).read_text(encoding="utf-8"))
    event["previous_event_hash"] = "0" * 64
    _chain_path(tmp_path).write_text(_audit_event_line(event), encoding="utf-8")

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.manifest.audit.verification.status == "broken"
    assert result.manifest.audit.verification.diagnostics == (
        "line 1 previous hash mismatch",
    )


def test_write_report_artifact_manifest_reports_audit_event_schema_mismatch(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    write_report_artifact_manifest(project_root=tmp_path)
    event = json.loads(_chain_path(tmp_path).read_text(encoding="utf-8"))
    event["sequence"] = 0
    _chain_path(tmp_path).write_text(_audit_event_line(event), encoding="utf-8")

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.manifest.audit.verification.status == "broken"
    assert result.manifest.audit.verification.diagnostics == (
        "line 1 failed schema validation",
    )


def test_write_report_artifact_manifest_ignores_blank_audit_chain_lines(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    write_report_artifact_manifest(project_root=tmp_path)
    chain_path = _chain_path(tmp_path)
    chain_path.write_text(chain_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = write_report_artifact_manifest(project_root=tmp_path)

    assert result.manifest.audit.verification.status == "verified"
    assert result.manifest.audit.verification.checked_events == 2


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


def test_write_report_artifact_manifest_wraps_final_manifest_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )

    def fail_manifest_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        if artifact == "report artifact manifest":
            _ = path, content, root
            raise SafeWriteError("manifest replacement failed")
        return Path(path)

    monkeypatch.setattr(artifact_manifest, "safe_write_text", fail_manifest_write)

    with pytest.raises(ReportArtifactManifestError, match="manifest replacement failed"):
        write_report_artifact_manifest(project_root=tmp_path)
