"""Tests for sanitized evidence bundle generation."""

import hashlib
import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence_bundle as evidence_bundle
import entroping.core.report_artifact_manifest as report_artifact_manifest
from entroping.core.evidence_bundle import (
    EVIDENCE_BUNDLE_SCHEMA_VERSION,
    EvidenceBundleError,
    run_evidence_bundle_report,
)
from entroping.core.report_artifact_manifest import write_report_artifact_manifest
from entroping.core.safe_write import SafeWriteError


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _sha256(content: str) -> str:
    return hashlib.sha256(content.lstrip().encode("utf-8")).hexdigest()


def _write_required_artifacts(root: Path) -> None:
    _write_text(
        root / "reports" / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "stdout": "Authorization: Bearer sk-proj-this-secret-must-not-enter-the-bundle"
}
""",
    )
    _write_text(
        root / "reports" / "effective-policy.json",
        """
{
  "schema_version": "entroping.effective-policy-report.v1",
  "project": "checkout-api",
  "gates": []
}
""",
    )
    write_report_artifact_manifest(project_root=root)


def test_run_evidence_bundle_report_writes_value_free_ready_bundle(tmp_path: Path) -> None:
    _write_required_artifacts(tmp_path)

    result = run_evidence_bundle_report(project_root=tmp_path)

    assert result.output_path == tmp_path / "reports" / "evidence-bundle.json"
    assert result.bundle.schema_version == EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert result.bundle.summary.status == "ready"
    assert result.bundle.summary.required_present == 3
    assert result.bundle.summary.required_missing == 0
    assert result.bundle.summary.required_invalid == 0
    assert result.bundle.manifest_audit is not None
    assert result.bundle.manifest_audit.status == "verified"
    by_path = {artifact.path: artifact for artifact in result.bundle.artifacts}
    assert set(by_path) == {
        "reports/artifact-manifest.json",
        "reports/effective-policy.json",
        "reports/run-latest.json",
    }
    assert by_path["reports/run-latest.json"].sha256 == _sha256(
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "stdout": "Authorization: Bearer sk-proj-this-secret-must-not-enter-the-bundle"
}
"""
    )
    payload = result.output_path.read_text(encoding="utf-8")
    assert "sk-proj-this-secret-must-not-enter-the-bundle" not in payload
    assert "checkout-api" in payload


def test_run_evidence_bundle_report_writes_value_free_ready_markdown(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)

    result = run_evidence_bundle_report(
        project_root=tmp_path,
        output_path=Path("reports") / "evidence-bundle.md",
    )

    assert result.output_path == tmp_path / "reports" / "evidence-bundle.md"
    assert result.bundle.summary.status == "ready"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Evidence Bundle" in markdown
    assert "- Status: `ready`" in markdown
    assert "- Required artifacts: `3/3` present, `0` missing, `0` invalid" in markdown
    assert "- Artifact manifest audit: `verified`" in markdown
    assert "| run_json | reports/run-latest.json | present |" in markdown
    assert "No diagnostics were found." in markdown
    assert "No missing required artifacts were found." in markdown
    assert "sk-proj-this-secret-must-not-enter-the-bundle" not in markdown


def test_run_evidence_bundle_report_records_missing_required_artifacts(
    tmp_path: Path,
) -> None:
    result = run_evidence_bundle_report(project_root=tmp_path)

    assert result.bundle.summary.status == "not_ready"
    assert result.bundle.summary.required_present == 0
    assert result.bundle.summary.required_missing == 3
    assert result.bundle.summary.required_invalid == 0
    assert [item.path for item in result.bundle.missing_artifacts] == [
        "reports/artifact-manifest.json",
        "reports/effective-policy.json",
        "reports/run-latest.json",
    ]
    assert {diagnostic.code for diagnostic in result.bundle.diagnostics} == {
        "missing_required_artifact"
    }


def test_run_evidence_bundle_report_writes_not_ready_markdown_with_next_commands(
    tmp_path: Path,
) -> None:
    result = run_evidence_bundle_report(
        project_root=tmp_path,
        output_path=Path("reports") / "evidence-bundle.md",
    )

    assert result.bundle.summary.status == "not_ready"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "- Status: `not_ready`" in markdown
    assert "- Required artifacts: `0/3` present, `3` missing, `0` invalid" in markdown
    assert "| artifact_manifest | reports/artifact-manifest.json | missing |" in markdown
    assert "| effective_policy | reports/effective-policy.json | missing |" in markdown
    assert "| run_json | reports/run-latest.json | missing |" in markdown
    assert "## Next Local Commands" in markdown
    assert "- `entroping report artifact-manifest`" in markdown
    assert "- `entroping report policy --output json`" in markdown
    assert "- `entroping run --report json`" in markdown
    assert (
        "- `entroping report evidence-bundle --output reports/evidence-bundle.md`"
        in markdown
    )


def test_run_evidence_bundle_report_detects_schema_and_checksum_mismatches(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v9",
  "project": "checkout-api"
}
""",
    )

    result = run_evidence_bundle_report(project_root=tmp_path)

    assert result.bundle.summary.status == "not_ready"
    assert result.bundle.summary.required_invalid == 2
    assert [
        (diagnostic.code, diagnostic.path)
        for diagnostic in result.bundle.diagnostics
        if diagnostic.path == "reports/run-latest.json"
    ] == [
        ("schema_mismatch", "reports/run-latest.json"),
        ("checksum_mismatch", "reports/run-latest.json"),
    ]


def test_run_evidence_bundle_report_writes_checksum_and_audit_diagnostics_markdown(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)
    chain_path = tmp_path / ".entroping" / "report-audit-chain.jsonl"
    chain_path.write_text(
        chain_path.read_text(encoding="utf-8").replace(
            "entroping.run-report.v1",
            "entroping.run-report.v9",
        ),
        encoding="utf-8",
    )
    write_report_artifact_manifest(project_root=tmp_path)
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v9",
  "project": "checkout-api"
}
""",
    )

    result = run_evidence_bundle_report(
        project_root=tmp_path,
        output_path=Path("reports") / "evidence-bundle.md",
    )

    assert result.bundle.summary.status == "not_ready"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "- Artifact manifest audit: `broken`" in markdown
    assert "| error | artifact_manifest_audit_broken | reports/artifact-manifest.json |" in (
        markdown
    )
    assert "| error | schema_mismatch | reports/run-latest.json |" in markdown
    assert "| error | checksum_mismatch | reports/run-latest.json |" in markdown
    assert "sk-proj-this-secret-must-not-enter-the-bundle" not in markdown


def test_run_evidence_bundle_report_allows_digest_shaped_audit_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest_with_luhn_digit_run = (
        "bc52ae1be5e2f4d1716762f476eab11b90d6ab62746d7b34945091693438190b"
    )
    monkeypatch.setattr(
        report_artifact_manifest,
        "_hash_audit_event_payload",
        lambda _payload: digest_with_luhn_digit_run,
    )
    _write_required_artifacts(tmp_path)

    result = run_evidence_bundle_report(project_root=tmp_path)

    assert result.bundle.manifest_audit is not None
    assert result.bundle.manifest_audit.latest_event_hash == digest_with_luhn_digit_run


def test_run_evidence_bundle_report_reports_invalid_artifact_manifest(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "artifact-manifest.json",
        '{"schema_version":"entroping.report-artifact-manifest.v1"}\n',
    )
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )
    _write_text(
        tmp_path / "reports" / "effective-policy.json",
        '{"schema_version":"entroping.effective-policy-report.v1"}\n',
    )

    result = run_evidence_bundle_report(project_root=tmp_path)

    assert result.bundle.summary.status == "not_ready"
    assert ("artifact_manifest_invalid", "reports/artifact-manifest.json") in {
        (diagnostic.code, diagnostic.path) for diagnostic in result.bundle.diagnostics
    }
    assert result.bundle.manifest_audit is None


def test_run_evidence_bundle_report_reports_broken_artifact_manifest_audit(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)
    chain_path = tmp_path / ".entroping" / "report-audit-chain.jsonl"
    chain_path.write_text(
        chain_path.read_text(encoding="utf-8").replace(
            "entroping.run-report.v1",
            "entroping.run-report.v9",
        ),
        encoding="utf-8",
    )
    write_report_artifact_manifest(project_root=tmp_path)

    result = run_evidence_bundle_report(project_root=tmp_path)

    assert result.bundle.summary.status == "not_ready"
    assert result.bundle.manifest_audit is not None
    assert result.bundle.manifest_audit.status == "broken"
    assert result.bundle.summary.required_invalid == 0
    assert ("artifact_manifest_audit_broken", "reports/artifact-manifest.json") in {
        (diagnostic.code, diagnostic.path) for diagnostic in result.bundle.diagnostics
    }


@pytest.mark.parametrize(
    ("content", "expected_schema"),
    [
        ("not json\n", None),
        ("[]\n", None),
        ('{"schema_version": 7}\n', None),
    ],
)
def test_run_evidence_bundle_report_marks_unreadable_or_unsupported_schema(
    tmp_path: Path,
    content: str,
    expected_schema: str | None,
) -> None:
    _write_required_artifacts(tmp_path)
    _write_text(tmp_path / "reports" / "effective-policy.json", content)

    result = run_evidence_bundle_report(project_root=tmp_path)

    by_path = {artifact.path: artifact for artifact in result.bundle.artifacts}
    assert by_path["reports/effective-policy.json"].schema_version == expected_schema
    assert ("schema_mismatch", "reports/effective-policy.json") in {
        (diagnostic.code, diagnostic.path) for diagnostic in result.bundle.diagnostics
    }


def test_run_evidence_bundle_report_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(EvidenceBundleError, match="must stay inside the project"):
        run_evidence_bundle_report(
            project_root=tmp_path,
            output_path=tmp_path.parent / "evidence-bundle.json",
        )


def test_run_evidence_bundle_report_rejects_parent_traversal_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceBundleError, match="must stay inside the project"):
        run_evidence_bundle_report(
            project_root=tmp_path,
            output_path=Path("..") / "evidence-bundle.json",
        )


def test_run_evidence_bundle_report_rejects_local_state_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceBundleError, match="must not be written into .entroping"):
        run_evidence_bundle_report(
            project_root=tmp_path,
            output_path=Path(".entroping") / "evidence-bundle.json",
        )


def test_run_evidence_bundle_report_rejects_symlinked_artifact_path(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    target = tmp_path / "run-latest-target.json"
    target.write_text('{"schema_version":"entroping.run-report.v1"}\n', encoding="utf-8")
    (reports / "run-latest.json").symlink_to(target)

    with pytest.raises(EvidenceBundleError, match="uses symlinked component"):
        run_evidence_bundle_report(project_root=tmp_path)


def test_run_evidence_bundle_report_rejects_artifact_directory(tmp_path: Path) -> None:
    (tmp_path / "reports" / "run-latest.json").mkdir(parents=True)

    with pytest.raises(EvidenceBundleError, match="is not a file"):
        run_evidence_bundle_report(project_root=tmp_path)


def test_run_evidence_bundle_report_rejects_oversized_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_required_artifacts(tmp_path)
    original_stat = Path.stat

    def fake_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = original_stat(path, follow_symlinks=follow_symlinks)
        if path.name != "run-latest.json":
            return result
        values = list(result)
        values[6] = evidence_bundle._MAX_EVIDENCE_ARTIFACT_BYTES + 1
        return type(result)(values)

    monkeypatch.setattr(Path, "stat", fake_stat)

    with pytest.raises(EvidenceBundleError, match="exceeds"):
        run_evidence_bundle_report(project_root=tmp_path)


def test_run_evidence_bundle_report_wraps_artifact_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_required_artifacts(tmp_path)
    original_read_bytes = Path.read_bytes

    def fail_run_json(path: Path) -> bytes:
        if path.name == "run-latest.json":
            raise OSError("disk unavailable")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_run_json)

    with pytest.raises(EvidenceBundleError, match="disk unavailable"):
        run_evidence_bundle_report(project_root=tmp_path)


def test_run_evidence_bundle_report_wraps_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_required_artifacts(tmp_path)

    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("write denied")

    monkeypatch.setattr(evidence_bundle, "safe_write_text", fail_write)

    with pytest.raises(EvidenceBundleError, match="write denied"):
        run_evidence_bundle_report(project_root=tmp_path)


def test_run_evidence_bundle_report_rejects_secret_like_metadata_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_required_artifacts(tmp_path)
    monkeypatch.setattr(evidence_bundle, "_safe_metadata_text", lambda value: value)

    with pytest.raises(EvidenceBundleError, match="secret-like content"):
        run_evidence_bundle_report(
            project_root=tmp_path,
            purpose="token=live-secret",
        )


def test_run_evidence_bundle_report_rejects_secret_shaped_metadata(
    tmp_path: Path,
) -> None:
    _write_required_artifacts(tmp_path)

    result = run_evidence_bundle_report(
        project_root=tmp_path,
        purpose="token=live-secret",
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["purpose"] == "token=[REDACTED]"
    assert "live-secret" not in result.output_path.read_text(encoding="utf-8")
