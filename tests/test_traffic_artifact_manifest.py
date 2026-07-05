"""Tests for captured-traffic artifact approval manifests."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import entroping.core.traffic_artifact_manifest as traffic_artifact_manifest
from entroping.core.safe_write import SafeWriteError
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def test_write_traffic_artifact_approval_manifest_is_value_free_and_deterministic(
    tmp_path: Path,
) -> None:
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\nHTTP 200\n", encoding="utf-8")

    result = traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
        project_root=tmp_path,
        manifest_name="freeze-checkout_flow",
        workflow="freeze-hurl",
        source_session_name="checkout_flow",
        source_records=(exchange,),
        artifacts=(
            traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                kind="hurl", path=artifact_path
            ),
        ),
    )

    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": traffic_artifact_manifest.TRAFFIC_ARTIFACT_APPROVAL_SCHEMA_VERSION,
        "workflow": "freeze-hurl",
        "source": {
            "session_name": "checkout_flow",
            "session_id": _expected_session_id("checkout_flow", exchange),
            "record_count": 1,
            "record_fingerprints": [_exchange_fingerprint(exchange)],
        },
        "redaction": {
            "total_records": 1,
            "redacted_records": 1,
            "unredacted_records": 0,
            "low_confidence_records": 0,
            "request_count": 1,
            "response_count": 1,
            "header_categories": [
                {"category": "request authorization header", "count": 1},
            ],
            "query_categories": [
                {"category": "token-like query parameter", "count": 1},
            ],
            "body_categories": [
                {"category": "request password body field", "count": 1},
            ],
            "body_summary_categories": [
                {"category": "request JSON body summary", "count": 1},
            ],
        },
        "artifacts": [
            {
                "kind": "hurl",
                "path": "tests/generated/checkout_flow.hurl",
                "size_bytes": artifact_path.stat().st_size,
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            },
        ],
    }
    raw_manifest = result.manifest_path.read_text(encoding="utf-8")
    assert "approval-secret" not in raw_manifest
    assert "api.example.test" not in raw_manifest
    assert "Authorization" not in raw_manifest


def test_write_traffic_artifact_approval_manifest_refuses_unredacted_source_records(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")

    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError, match="requires redacted traffic"
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(_exchange(secret="approval-secret"),),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=artifact_path
                ),
            ),
        )

    assert not (tmp_path / "reports" / "approvals" / "freeze-checkout_flow.json").exists()


def test_write_traffic_artifact_approval_manifest_requires_source_records_and_artifacts(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))

    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError,
        match="at least one source traffic record",
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=artifact_path
                ),
            ),
        )
    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError,
        match="at least one generated artifact",
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(),
        )


@pytest.mark.parametrize(
    ("manifest_name", "message"),
    [
        ("", "must not be empty"),
        ("bad\nname", "must not contain control characters"),
        ("../approval", "safe file stem"),
        (".hidden", "safe file stem"),
        ("bad name!", "letters, numbers"),
    ],
)
def test_write_traffic_artifact_approval_manifest_rejects_unsafe_manifest_names(
    tmp_path: Path,
    manifest_name: str,
    message: str,
) -> None:
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))

    with pytest.raises(traffic_artifact_manifest.TrafficArtifactApprovalError, match=message):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name=manifest_name,
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=artifact_path
                ),
            ),
        )


def test_write_traffic_artifact_approval_manifest_rejects_unsafe_session_name(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))

    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError, match="source session name"
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="bad\nsession",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=artifact_path
                ),
            ),
        )


@pytest.mark.parametrize(
    ("artifact_path", "message"),
    [
        (Path(".entroping/state.db"), "refuses local traffic state"),
        (Path("envs/local.env"), "refuses local env files"),
        (Path("../outside.hurl"), "must stay inside"),
    ],
)
def test_write_traffic_artifact_approval_manifest_refuses_unsafe_artifact_paths(
    tmp_path: Path,
    artifact_path: Path,
    message: str,
) -> None:
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))
    absolute_artifact_path = tmp_path / artifact_path
    absolute_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_artifact_path.write_text("raw local state\n", encoding="utf-8")

    with pytest.raises(traffic_artifact_manifest.TrafficArtifactApprovalError, match=message):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=absolute_artifact_path
                ),
            ),
        )


def test_write_traffic_artifact_approval_manifest_accepts_relative_artifact_paths(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))

    result = traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
        project_root=tmp_path,
        manifest_name="freeze-checkout_flow",
        workflow="freeze-hurl",
        source_session_name="checkout_flow",
        source_records=(exchange,),
        artifacts=(
            traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                kind="hurl",
                path=Path("tests/generated/checkout_flow.hurl"),
            ),
        ),
    )

    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["artifacts"][0]["path"] == "tests/generated/checkout_flow.hurl"


def test_write_traffic_artifact_approval_manifest_rejects_missing_and_non_file_artifacts(
    tmp_path: Path,
) -> None:
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))

    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError, match="does not exist"
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl",
                    path=Path("tests/generated/missing.hurl"),
                ),
            ),
        )

    directory_artifact = tmp_path / "tests" / "generated" / "not-a-file.hurl"
    directory_artifact.mkdir(parents=True)
    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError, match="is not a file"
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=directory_artifact
                ),
            ),
        )


def test_write_traffic_artifact_approval_manifest_rejects_symlink_artifact_path(
    tmp_path: Path,
) -> None:
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.hurl"
    victim.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")
    artifact_path.symlink_to(victim)

    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError, match="symlinked path component"
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=artifact_path
                ),
            ),
        )


def test_write_traffic_artifact_approval_manifest_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("GET https://api.example.test/checkout\n", encoding="utf-8")
    exchange = redact_traffic_exchange(_exchange(secret="approval-secret"))

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("approval manifest write failed")

    monkeypatch.setattr(traffic_artifact_manifest, "safe_write_text", fail_safe_write)

    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError,
        match="approval manifest write failed",
    ):
        traffic_artifact_manifest.write_traffic_artifact_approval_manifest(
            project_root=tmp_path,
            manifest_name="freeze-checkout_flow",
            workflow="freeze-hurl",
            source_session_name="checkout_flow",
            source_records=(exchange,),
            artifacts=(
                traffic_artifact_manifest.TrafficArtifactManifestArtifact(
                    kind="hurl", path=artifact_path
                ),
            ),
        )


def test_private_path_helpers_report_outside_paths_without_raw_state(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.hurl"
    with pytest.raises(
        traffic_artifact_manifest.TrafficArtifactApprovalError, match="must stay inside"
    ):
        traffic_artifact_manifest._reject_symlink_path(
            outside,
            root=tmp_path,
            artifact="generated artifact",
        )

    assert traffic_artifact_manifest._display_path(outside, tmp_path) == str(outside)


def _exchange(*, secret: str) -> TrafficExchange:
    return TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}",
            headers={"Authorization": f"Bearer {secret}"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=32,
                text=f'{{"password":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(status_code=200),
    )


def _expected_session_id(session_name: str, exchange: TrafficExchange) -> str:
    fingerprint = _exchange_fingerprint(exchange)
    return hashlib.sha256(f"{session_name}\n{fingerprint}".encode()).hexdigest()


def _exchange_fingerprint(exchange: TrafficExchange) -> str:
    canonical = json.dumps(
        exchange.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
