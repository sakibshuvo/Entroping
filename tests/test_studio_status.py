"""Unit tests for read-only Studio status collection."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import entroping.studio.status as studio_status
from entroping.core.config_loader import QanstitutionLoadError
from entroping.core.evidence.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse

BASE_TIME = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
_HASH = "a" * 64


def _present_bundle_artifact(path: str = "reports/evidence-bundle.json") -> LocalEvidenceArtifact:
    return LocalEvidenceArtifact(
        id="evidence-bundle-json",
        label="Evidence Bundle",
        path=path,
        state="present",
        schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
        summary="ready",
    )


def _diagnostic(
    code: str,
    *,
    path: str | None,
    severity: str = "error",
) -> dict[str, object]:
    return {
        "severity": severity,
        "code": code,
        "path": path,
        "message": "value-free diagnostic",
        "remediation_hint": "local remediation command",
    }


def _write_evidence_bundle(
    root: Path,
    *,
    status: str,
    required_present: int,
    required_missing: int,
    required_invalid: int,
    diagnostics: list[dict[str, object]] | None = None,
    manifest_status: str | None = "verified",
) -> None:
    reports_dir = root / "reports"
    reports_dir.mkdir(exist_ok=True)
    artifacts = [
        {
            "kind": "artifact_manifest",
            "path": "reports/artifact-manifest.json",
            "required": True,
            "schema_version": "entroping.report-artifact-manifest.v1",
            "size_bytes": 100,
            "sha256": _HASH,
        },
        {
            "kind": "effective_policy",
            "path": "reports/effective-policy.json",
            "required": True,
            "schema_version": "entroping.effective-policy-report.v1",
            "size_bytes": 100,
            "sha256": _HASH,
        },
        {
            "kind": "run_json",
            "path": "reports/run-latest.json",
            "required": True,
            "schema_version": "entroping.run-report.v1",
            "size_bytes": 100,
            "sha256": _HASH,
        },
    ][:required_present]
    bundle = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "generated_at": "2026-06-19T00:00:00+00:00",
        "purpose": "design-partner-upload-readiness",
        "project": "checkout-api",
        "summary": {
            "status": status,
            "required_total": 3,
            "required_present": required_present,
            "required_missing": required_missing,
            "required_invalid": required_invalid,
            "artifacts_total": len(artifacts),
            "diagnostics_total": len(diagnostics or []),
        },
        "artifacts": artifacts,
        "missing_artifacts": [
            {
                "kind": "run_json",
                "path": "reports/run-latest.json",
                "required": True,
            }
        ][:required_missing],
        "diagnostics": diagnostics or [],
        "manifest_audit": (
            {
                "path": "reports/artifact-manifest.json",
                "status": manifest_status,
                "chain_path": "reports/audit-chain.jsonl",
                "checked_events": 2,
                "latest_event_hash": _HASH,
                "diagnostics": (),
            }
            if manifest_status is not None
            else None
        ),
    }
    (reports_dir / "evidence-bundle.json").write_text(
        json.dumps(bundle),
        encoding="utf-8",
    )


def _traffic_exchange(
    *,
    method: str,
    url: str,
    secret: str,
    status_code: int = 200,
    duration_ms: int | None = 100,
    offset_seconds: int = 0,
) -> TrafficExchange:
    return TrafficExchange(
        captured_at=BASE_TIME + timedelta(seconds=offset_seconds),
        duration_ms=duration_ms,
        request=TrafficRequest(
            method=method,
            url=f"{url}?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=64,
                text=f'{{"password":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=status_code,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(content_type="application/json", size_bytes=11, text='{"ok":true}'),
        ),
    )


def test_ensure_studio_available_reports_missing_textual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("entroping.studio.status.importlib.util.find_spec", lambda name: None)

    with pytest.raises(studio_status.StudioDependencyError, match="uv sync --extra studio"):
        studio_status.ensure_studio_available()


def test_collect_studio_status_without_latest_run(tmp_path: Path) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        'project: "checkout-api"\ngates: []\n',
        encoding="utf-8",
    )

    status = studio_status.collect_studio_status(project_root=tmp_path, environment="local")

    assert status.environment == "local"
    assert status.project == "checkout-api"
    assert status.qanstitution_status == "ok"
    assert status.latest_run is None
    assert not status.traffic_state_available
    rendered = studio_status.render_studio_status(status)
    assert "Latest run: none" in rendered
    assert "Reports: none" in rendered


def test_collect_studio_status_without_qanstitution(tmp_path: Path) -> None:
    status = studio_status.collect_studio_status(project_root=tmp_path, environment=None)

    assert status.project == "not configured"
    assert status.qanstitution_status == "missing"


def test_collect_studio_status_reports_qanstitution_load_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "qanstitution.yaml").write_text("project: checkout-api\n", encoding="utf-8")

    def fail_load(path: Path) -> object:
        _ = path
        raise QanstitutionLoadError("invalid policy")

    monkeypatch.setattr(studio_status, "load_qanstitution", fail_load)

    status = studio_status.collect_studio_status(project_root=tmp_path, environment=None)

    assert status.project == "unavailable"
    assert status.qanstitution_status == "error: invalid policy"


def test_collect_studio_status_reports_latest_run_load_errors(tmp_path: Path) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        'project: "checkout-api"\ngates: []\n',
        encoding="utf-8",
    )
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    (state_dir / "latest-run.json").write_text('{"summary":{}}\n', encoding="utf-8")

    status = studio_status.collect_studio_status(project_root=tmp_path, environment=None)

    assert status.latest_run is None
    assert status.latest_run_status.startswith("error:")


def test_collect_studio_status_with_latest_run_reports_and_traffic_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        """
project: "checkout-api"
gates:
  - id: "global_latency"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
""",
        encoding="utf-8",
    )
    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    (state_dir / "state.db").write_bytes(b"sqlite")
    (state_dir / "latest-run.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "local",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "execution_path": ".entroping/run-1/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 10,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "",
                    },
                    {
                        "path": "tests/checkout.hurl",
                        "execution_path": ".entroping/run-1/checkout.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 20,
                        "rule_ids": ["global_latency"],
                        "stdout": "",
                        "stderr": "assert failed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text("{}\n", encoding="utf-8")
    (reports_dir / "junit.xml").write_text("<testsuite />\n", encoding="utf-8")

    status = studio_status.collect_studio_status(project_root=tmp_path, environment=None)
    rendered = studio_status.render_studio_status(status)

    assert status.environment == "default"
    assert status.latest_run is not None
    assert status.latest_run.failed == 1
    assert status.applied_gates[0].rule_id == "global_latency"
    assert status.applied_gates[0].test_path == "tests/health.hurl"
    assert status.applied_gates[0].enforcement == "block"
    assert status.applied_gates[0].assertion == "duration < 2000"
    assert status.applied_gates[1].test_status == "failed"
    assert status.report_paths == ("reports/junit.xml", "reports/run-latest.json")
    assert status.traffic_state_available
    assert "Latest run: 1 passed, 1 failed, 2 total" in rendered
    assert "Applied gates: 2" in rendered
    assert "Traffic state: available" in rendered


def test_collect_studio_status_exposes_read_only_evidence_artifacts(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "capture-summary.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.capture-summary.v1",
                "summary": {
                    "total_records": 2,
                    "redacted_records": 2,
                    "unredacted_records": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "evidence-bundle.json").write_text("not json\n", encoding="utf-8")

    status = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    by_id = {artifact.id: artifact for artifact in status.evidence_artifacts}
    rendered = studio_status.render_studio_status(status)

    assert status.report_paths == (
        "reports/capture-summary.json",
        "reports/evidence-bundle.json",
        "reports/run-latest.json",
    )
    assert by_id["run-json"].summary == "1 total, 1 passed, 0 failed"
    assert by_id["capture-summary-json"].summary == "2/2 records redacted, 0 unredacted"
    assert by_id["evidence-bundle-json"].state == "invalid"
    assert "Evidence artifacts: 2 present, 1 attention" in rendered


def test_collect_studio_status_exposes_ready_evidence_bundle_readiness(
    tmp_path: Path,
) -> None:
    _write_evidence_bundle(
        tmp_path,
        status="ready",
        required_present=3,
        required_missing=0,
        required_invalid=0,
    )

    status = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    readiness = status.evidence_bundle_readiness
    rendered = studio_status.render_studio_status(status)

    assert readiness is not None
    assert readiness.artifact_state == "present"
    assert readiness.schema_version == EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert readiness.status == "ready"
    assert readiness.required_present == 3
    assert readiness.required_total == 3
    assert readiness.required_missing == 0
    assert readiness.required_invalid == 0
    assert readiness.missing_diagnostics == 0
    assert readiness.invalid_diagnostics == 0
    assert readiness.unsafe_diagnostics == 0
    assert readiness.checksum_mismatches == 0
    assert readiness.audit_chain_status == "verified"
    assert "Evidence bundle: ready (3/3 required, 0 missing, 0 invalid; audit verified)" in rendered


def test_collect_studio_status_exposes_not_ready_evidence_bundle_diagnostics(
    tmp_path: Path,
) -> None:
    _write_evidence_bundle(
        tmp_path,
        status="not_ready",
        required_present=2,
        required_missing=1,
        required_invalid=1,
        diagnostics=[
            _diagnostic("missing_required_artifact", path="reports/run-latest.json"),
            _diagnostic("artifact_contract_invalid", path="reports/run-latest.json"),
            _diagnostic("checksum_mismatch", path="reports/run-latest.json"),
            _diagnostic(
                "artifact_manifest_audit_broken",
                path="reports/artifact-manifest.json",
            ),
        ],
        manifest_status="broken",
    )

    status = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    readiness = status.evidence_bundle_readiness
    rendered = studio_status.render_studio_status(status)

    assert readiness is not None
    assert readiness.artifact_state == "present"
    assert readiness.status == "not_ready"
    assert readiness.required_present == 2
    assert readiness.required_total == 3
    assert readiness.required_missing == 1
    assert readiness.required_invalid == 1
    assert readiness.diagnostics_total == 4
    assert readiness.missing_diagnostics == 1
    assert readiness.invalid_diagnostics == 1
    assert readiness.unsafe_diagnostics == 0
    assert readiness.checksum_mismatches == 1
    assert readiness.audit_chain_status == "broken"
    assert (
        "Evidence bundle: not_ready (2/3 required, 1 missing, 1 invalid; audit broken)" in rendered
    )


def test_collect_studio_status_exposes_invalid_missing_and_unsafe_bundle_states(
    tmp_path: Path,
) -> None:
    missing = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    assert missing.evidence_bundle_readiness is not None
    assert missing.evidence_bundle_readiness.artifact_state == "missing"
    assert missing.evidence_bundle_readiness.status == "missing"
    assert missing.evidence_bundle_readiness.missing_diagnostics == 1

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "evidence-bundle.json").write_text("not json\n", encoding="utf-8")
    invalid = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    assert invalid.evidence_bundle_readiness is not None
    assert invalid.evidence_bundle_readiness.artifact_state == "invalid"
    assert invalid.evidence_bundle_readiness.status == "invalid"
    assert invalid.evidence_bundle_readiness.invalid_diagnostics == 1
    assert "Evidence bundle: invalid" in studio_status.render_studio_status(invalid)

    (reports_dir / "evidence-bundle.json").unlink()
    (reports_dir / "evidence-bundle.json").mkdir()
    unsafe = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    assert unsafe.evidence_bundle_readiness is not None
    assert unsafe.evidence_bundle_readiness.artifact_state == "unsafe"
    assert unsafe.evidence_bundle_readiness.status == "unsafe"
    assert unsafe.evidence_bundle_readiness.unsafe_diagnostics == 1
    assert "Evidence bundle: unsafe" in studio_status.render_studio_status(unsafe)


def test_studio_evidence_bundle_readiness_handles_absent_artifact_definition(
    tmp_path: Path,
) -> None:
    assert studio_status._load_evidence_bundle_readiness(tmp_path, ()) is None


def test_studio_evidence_bundle_readiness_rechecks_missing_after_index(
    tmp_path: Path,
) -> None:
    readiness = studio_status._load_evidence_bundle_readiness(
        tmp_path,
        (_present_bundle_artifact(),),
    )

    assert readiness is not None
    assert readiness.artifact_state == "missing"
    assert readiness.status == "missing"


def test_studio_evidence_bundle_readiness_rejects_invalid_bundle_contract(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "evidence-bundle.json").write_text(
        json.dumps({"schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION}),
        encoding="utf-8",
    )

    status = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    readiness = status.evidence_bundle_readiness

    assert readiness is not None
    assert readiness.artifact_state == "invalid"
    assert readiness.invalid_diagnostics == 1


def test_read_studio_evidence_bundle_bytes_defends_path_races_and_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path = tmp_path / "reports" / "evidence-bundle.json"
    bundle_path.parent.mkdir()

    def raise_outside(path: Path, *, root: Path) -> Path | None:
        _ = path, root
        raise ValueError("outside")

    monkeypatch.setattr(studio_status, "first_symlink_path_component", raise_outside)
    assert studio_status._read_evidence_bundle_bytes(bundle_path, root=tmp_path) == (
        None,
        "unsafe",
    )

    monkeypatch.setattr(
        studio_status,
        "first_symlink_path_component",
        lambda path, *, root: path,
    )
    assert studio_status._read_evidence_bundle_bytes(bundle_path, root=tmp_path) == (
        None,
        "unsafe",
    )

    monkeypatch.setattr(
        studio_status,
        "first_symlink_path_component",
        lambda path, *, root: None,
    )
    bundle_path.mkdir()
    assert studio_status._read_evidence_bundle_bytes(bundle_path, root=tmp_path) == (
        None,
        "unsafe",
    )

    bundle_path.rmdir()
    bundle_path.write_text("{}\n", encoding="utf-8")
    original_open = Path.open

    def fail_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == bundle_path:
            raise OSError("denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)
    assert studio_status._read_evidence_bundle_bytes(bundle_path, root=tmp_path) == (
        None,
        "invalid",
    )

    monkeypatch.setattr(Path, "open", original_open)
    monkeypatch.setattr(studio_status, "_MAX_STUDIO_EVIDENCE_BUNDLE_BYTES", 2)
    assert studio_status._read_evidence_bundle_bytes(bundle_path, root=tmp_path) == (
        None,
        "invalid",
    )


def test_render_studio_status_handles_missing_evidence_index() -> None:
    status = studio_status.StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=(),
        traffic_state_available=False,
    )

    rendered = studio_status.render_studio_status(status)

    assert "Evidence artifacts: none" in rendered


def test_collect_studio_status_reads_redacted_traffic_routes_without_raw_values(
    tmp_path: Path,
) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        'project: "checkout-api"\ngates: []\n',
        encoding="utf-8",
    )
    store = TrafficStore.open_project(tmp_path)
    for exchange in (
        _traffic_exchange(
            method="GET",
            url="https://api.example.test/orders/123",
            secret="studio-secret-1",
            duration_ms=100,
        ),
        _traffic_exchange(
            method="GET",
            url="https://api.example.test/orders/456",
            secret="studio-secret-2",
            status_code=503,
            duration_ms=200,
            offset_seconds=1,
        ),
        _traffic_exchange(
            method="POST",
            url="https://payments.example.test/charge",
            secret="studio-secret-3",
            duration_ms=None,
            offset_seconds=2,
        ),
    ):
        store.record_exchange(redact_traffic_exchange(exchange))
    before = (tmp_path / ".entroping" / "state.db").stat().st_mtime_ns

    status = studio_status.collect_studio_status(project_root=tmp_path, environment="local")
    after = (tmp_path / ".entroping" / "state.db").stat().st_mtime_ns
    rendered = studio_status.render_studio_status(status)
    serialized_status = repr(status.traffic_routes) + repr(status.traffic_redactions) + rendered

    assert after == before
    assert status.traffic_state_available
    assert status.traffic_state_status == "ok"
    assert status.traffic_record_count == 3
    assert status.traffic_redacted_count == 3
    assert [
        (
            route.role,
            route.destination_host,
            route.method,
            route.path_template,
            route.call_count,
            route.failure_count,
            route.latency_average_ms,
        )
        for route in status.traffic_routes
    ] == [
        ("target", "api.example.test", "GET", "/orders/{id}", 2, 1, 150),
        ("dependency", "payments.example.test", "POST", "/charge", 1, 0, None),
    ]
    assert [(item.category, item.count) for item in status.traffic_redactions] == [
        ("request authorization header", 3),
        ("request password body field", 3),
        ("token-like query parameter", 3),
    ]
    assert "Traffic routes: 2" in rendered
    assert "Traffic redaction categories: 3" in rendered
    assert "studio-secret" not in serialized_status
    assert "token=" not in serialized_status


def test_collect_studio_status_handles_empty_traffic_state(tmp_path: Path) -> None:
    TrafficStore.open_project(tmp_path)

    status = studio_status.collect_studio_status(project_root=tmp_path, environment=None)

    assert status.traffic_state_available
    assert status.traffic_state_status == "empty"
    assert status.traffic_record_count == 0
    assert status.traffic_redacted_count == 0
    assert status.traffic_routes == ()
    assert status.traffic_redactions == ()


def test_collect_studio_status_reports_traffic_state_errors_without_crashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".entroping").mkdir()
    (tmp_path / ".entroping" / "state.db").write_text("not sqlite\n", encoding="utf-8")

    def fail_readonly(project_root: Path, *, limit: int | None = None) -> object:
        _ = (project_root, limit)
        raise TrafficStoreError("traffic store failed")

    monkeypatch.setattr(studio_status, "list_project_exchanges_readonly", fail_readonly)

    status = studio_status.collect_studio_status(project_root=tmp_path, environment=None)

    assert status.traffic_state_available
    assert status.traffic_state_status == "error: traffic store failed"
    assert status.traffic_routes == ()
