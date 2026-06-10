"""Tests for the freeze workflow filesystem boundary."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import entroping.core.freeze as freeze
from entroping.bridge.traffic_to_hurl import GeneratedTrafficHurlFile
from entroping.bridge.traffic_to_wiremock import GeneratedWireMockMapping
from entroping.core.freeze import FreezeError, run_freeze, run_freeze_mock
from entroping.core.hurl_validator import HurlValidationError
from entroping.core.safe_write import SafeWriteError
from entroping.core.traffic_filters import TrafficCaptureFilters
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _record_exchange(project_root: Path) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method="GET",
            url="https://api.example.test/checkout",
            headers={"Content-Type": "application/json"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=15,
                text='{"ok":true}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def _record_dependency_exchange(project_root: Path) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 1, tzinfo=UTC),
        duration_ms=40,
        request=TrafficRequest(
            method="POST",
            url="https://payments.example.test/charge",
            headers={"Content-Type": "application/json"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=17,
                text='{"ok":true}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def _record_internal_exchange(project_root: Path) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 2, tzinfo=UTC),
        duration_ms=35,
        request=TrafficRequest(
            method="GET",
            url="https://api.example.test/checkout/internal/health?token=filter-secret",
            headers={"Authorization": "Bearer filter-secret"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=15,
                text='{"ok":true}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def _record_sensitive_freeze_exchange(
    project_root: Path,
    *,
    secret: str = "preview-secret",
) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 3, tzinfo=UTC),
        duration_ms=45,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=44,
                text=f'{{"cart_id":"cart-1","password":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=43,
                text='{"id":"ord_123","status":"accepted"}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def _record_sensitive_mock_exchange(
    project_root: Path,
    *,
    secret: str = "wire-preview-secret",
) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 4, tzinfo=UTC),
        duration_ms=50,
        request=TrafficRequest(
            method="POST",
            url=f"https://payments.example.test/charge?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=34,
                text=f'{{"card_token":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": f"session={secret}",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=43,
                text=f'{{"approved":true,"token":"{secret}"}}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def _record_low_confidence_freeze_exchange(
    project_root: Path,
    *,
    secret: str = "low-confidence-secret",
) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 5, tzinfo=UTC),
        duration_ms=55,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "text/plain",
            },
            body=TrafficBody(
                content_type="text/plain",
                size_bytes=40,
                text=f"token={secret}&status=ok",
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": "text/plain"},
            body=TrafficBody(
                content_type="text/plain",
                size_bytes=31,
                text=f"response={secret}",
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def test_run_freeze_reports_missing_or_empty_traffic_state(tmp_path: Path) -> None:
    with pytest.raises(FreezeError, match="No traffic state found"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )

    TrafficStore.open_project(tmp_path)
    with pytest.raises(FreezeError, match="contains no traffic"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )


def test_preview_freeze_summarizes_hurl_without_writing_artifacts(tmp_path: Path) -> None:
    _record_sensitive_freeze_exchange(tmp_path, secret="preview-secret")

    preview = freeze.preview_freeze(
        project_root=tmp_path,
        name="checkout_flow",
        golden=True,
    )

    assert preview.workflow == "freeze-hurl"
    assert preview.name == "checkout_flow"
    assert preview.service is None
    assert preview.golden is True
    assert preview.record_count == 1
    assert [(artifact.kind, artifact.path) for artifact in preview.artifacts] == [
        ("hurl", tmp_path / "tests" / "generated" / "checkout_flow.hurl")
    ]
    assert [(record.method, record.path, record.status_code) for record in preview.records] == [
        ("POST", "/checkout", 201)
    ]
    assert {category.category: category.count for category in preview.redaction_categories} == {
        "request authorization header": 1,
        "request password body field": 1,
        "request JSON body summary": 1,
        "response JSON body summary": 1,
        "token-like query parameter": 1,
    }
    serialized = repr(preview)
    assert "preview-secret" not in serialized
    assert "token=preview-secret" not in serialized
    assert "?token=" not in serialized
    assert not (tmp_path / "tests").exists()
    assert not (tmp_path / "reports").exists()


def test_preview_freeze_mock_summarizes_mappings_without_writing_artifacts(
    tmp_path: Path,
) -> None:
    _record_sensitive_mock_exchange(tmp_path, secret="wire-preview-secret")

    preview = freeze.preview_freeze_mock(
        project_root=tmp_path,
        name="refund_flow",
        service="payments",
    )

    assert preview.workflow == "freeze-wiremock"
    assert preview.name == "refund_flow"
    assert preview.service == "payments"
    assert preview.golden is False
    assert preview.record_count == 1
    assert [(artifact.kind, artifact.path) for artifact in preview.artifacts] == [
        ("wiremock", tmp_path / "mocks" / "payments" / "refund_flow-001.json")
    ]
    assert [(record.method, record.path, record.status_code) for record in preview.records] == [
        ("POST", "/charge", 201)
    ]
    categories = {category.category: category.count for category in preview.redaction_categories}
    assert categories["request authorization header"] == 1
    assert categories["response cookie header"] == 1
    assert categories["response token body field"] == 1
    serialized = repr(preview)
    assert "wire-preview-secret" not in serialized
    assert "?token=" not in serialized
    assert not (tmp_path / "mocks").exists()
    assert not (tmp_path / "reports").exists()


def test_preview_freeze_mock_supports_exact_host_service(tmp_path: Path) -> None:
    _record_sensitive_mock_exchange(tmp_path)

    preview = freeze.preview_freeze_mock(
        project_root=tmp_path,
        name="refund_flow",
        service="payments.example.test",
    )

    assert preview.record_count == 1
    assert [(artifact.kind, artifact.path) for artifact in preview.artifacts] == [
        (
            "wiremock",
            tmp_path / "mocks" / "payments.example.test" / "refund_flow-001.json",
        )
    ]


def test_preview_freeze_mock_rejects_invalid_generated_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_sensitive_mock_exchange(tmp_path)

    def invalid_mapping(*args: object, **kwargs: object) -> tuple[GeneratedWireMockMapping, ...]:
        _ = args, kwargs
        return (GeneratedWireMockMapping("mocks/payments/refund_flow-001.json", "{"),)

    monkeypatch.setattr(freeze, "compile_traffic_session_to_wiremock", invalid_mapping)

    with pytest.raises(FreezeError, match="Expecting property name"):
        freeze.preview_freeze_mock(
            project_root=tmp_path,
            name="refund_flow",
            service="payments",
        )

    assert not (tmp_path / "mocks").exists()
    assert not (tmp_path / "reports").exists()


def test_preview_freeze_reports_missing_or_empty_traffic_state_without_writing(
    tmp_path: Path,
) -> None:
    with pytest.raises(FreezeError, match="No traffic state found"):
        freeze.preview_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
        )

    TrafficStore.open_project(tmp_path)
    with pytest.raises(FreezeError, match="contains no traffic"):
        freeze.preview_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
        )

    assert not (tmp_path / "tests").exists()
    assert not (tmp_path / "mocks").exists()
    assert not (tmp_path / "reports").exists()


def test_run_freeze_writes_generated_hurl(tmp_path: Path) -> None:
    _record_exchange(tmp_path)

    result = run_freeze(
        project_root=tmp_path,
        name="checkout_flow",
        golden=False,
        hurl_validator=lambda content, display_path: None,
    )

    assert result.record_count == 1
    assert result.output_path == tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    assert "GET https://api.example.test/checkout" in result.output_path.read_text(
        encoding="utf-8"
    )
    assert result.manifest_path == tmp_path / "reports" / "approvals" / "freeze-checkout_flow.json"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "entroping.traffic-artifact-approval.v1"
    assert manifest["workflow"] == "freeze-hurl"
    assert manifest["source"]["session_name"] == "checkout_flow"
    assert manifest["source"]["record_count"] == 1
    assert manifest["artifacts"][0]["kind"] == "hurl"
    assert manifest["artifacts"][0]["path"] == "tests/generated/checkout_flow.hurl"


def test_run_freeze_applies_capture_filters_before_hurl_generation(tmp_path: Path) -> None:
    _record_exchange(tmp_path)
    _record_internal_exchange(tmp_path)

    result = run_freeze(
        project_root=tmp_path,
        name="checkout_flow",
        golden=False,
        capture_filters=TrafficCaptureFilters(
            include_hosts=("api.example.test",),
            include_methods=("get",),
            include_paths=("/checkout",),
            exclude_paths=("/checkout/internal/*",),
        ),
        hurl_validator=lambda content, display_path: None,
    )

    content = result.output_path.read_text(encoding="utf-8")
    assert result.record_count == 1
    assert "GET https://api.example.test/checkout" in content
    assert "internal" not in content
    assert "filter-secret" not in content


def test_run_freeze_reports_empty_filtered_session(tmp_path: Path) -> None:
    _record_exchange(tmp_path)

    with pytest.raises(FreezeError, match="No traffic records matched capture filters"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            capture_filters=TrafficCaptureFilters(include_hosts=("missing.example.test",)),
            hurl_validator=lambda content, display_path: None,
        )

    assert not (tmp_path / "tests" / "generated" / "checkout_flow.hurl").exists()


@pytest.mark.parametrize("name", ["", "bad\nname", "../flow", ".hidden", "bad name!"])
def test_run_freeze_rejects_unsafe_names_before_state_lookup(tmp_path: Path, name: str) -> None:
    with pytest.raises(FreezeError, match="freeze name"):
        run_freeze(
            project_root=tmp_path,
            name=name,
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )


def test_run_freeze_wraps_hurl_validation_errors(tmp_path: Path) -> None:
    _record_exchange(tmp_path)

    def fail_validation(content: str, display_path: str) -> None:
        _ = content, display_path
        raise HurlValidationError("invalid hurl")

    with pytest.raises(FreezeError, match="invalid hurl"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=fail_validation,
        )


def test_run_freeze_refuses_symlink_generated_target(tmp_path: Path) -> None:
    _record_exchange(tmp_path)
    output_dir = tmp_path / "tests" / "generated"
    output_dir.mkdir(parents=True)
    victim = tmp_path / "victim.hurl"
    victim.write_text("victim\n", encoding="utf-8")
    (output_dir / "checkout_flow.hurl").symlink_to(victim)

    with pytest.raises(FreezeError, match="symlinked generated Hurl file"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )


def test_run_freeze_rejects_low_confidence_records(tmp_path: Path) -> None:
    _record_low_confidence_freeze_exchange(tmp_path)

    with pytest.raises(FreezeError, match="refusing to write freeze artifacts"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )

    assert not (tmp_path / "tests" / "generated" / "checkout_flow.hurl").exists()


def test_run_freeze_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)
    output = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    output.parent.mkdir(parents=True)
    output.write_text("old\n", encoding="utf-8")

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(freeze, "safe_write_text", fail_safe_write)

    with pytest.raises(FreezeError, match="temporary write failed"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )

    assert output.read_text(encoding="utf-8") == "old\n"


def test_run_freeze_mock_refuses_symlink_mapping_target(tmp_path: Path) -> None:
    _record_dependency_exchange(tmp_path)
    output_dir = tmp_path / "mocks" / "payments"
    output_dir.mkdir(parents=True)
    victim = tmp_path / "victim.json"
    victim.write_text("victim\n", encoding="utf-8")
    (output_dir / "refund_flow-001.json").symlink_to(victim)

    with pytest.raises(FreezeError, match="symlinked WireMock mapping"):
        run_freeze_mock(
            project_root=tmp_path,
            name="refund_flow",
            service="payments",
        )

    assert victim.read_text(encoding="utf-8") == "victim\n"


def test_run_freeze_mock_reports_missing_state_and_writes_mappings(tmp_path: Path) -> None:
    with pytest.raises(FreezeError, match="No traffic state found"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")

    _record_dependency_exchange(tmp_path)

    result = run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")

    assert result.record_count == 1
    assert result.output_paths == (tmp_path / "mocks" / "payments" / "refund_flow-001.json",)
    assert '"request"' in result.output_paths[0].read_text(encoding="utf-8")
    assert (
        result.manifest_path
        == tmp_path / "reports" / "approvals" / "freeze-refund_flow-mock-payments.json"
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "entroping.traffic-artifact-approval.v1"
    assert manifest["workflow"] == "freeze-wiremock"
    assert manifest["source"]["session_name"] == "refund_flow"
    assert manifest["source"]["record_count"] == 1
    assert manifest["artifacts"][0]["kind"] == "wiremock"
    assert manifest["artifacts"][0]["path"] == "mocks/payments/refund_flow-001.json"


def test_run_freeze_mock_applies_capture_filters_before_wiremock_generation(
    tmp_path: Path,
) -> None:
    _record_exchange(tmp_path)
    _record_dependency_exchange(tmp_path)

    result = run_freeze_mock(
        project_root=tmp_path,
        name="refund_flow",
        service="payments",
        capture_filters=TrafficCaptureFilters(include_hosts=("payments.example.test",)),
    )

    assert result.record_count == 1
    assert result.output_paths == (tmp_path / "mocks" / "payments" / "refund_flow-001.json",)


@pytest.mark.parametrize("service", ["", "bad\nservice", "../payments", ".hidden", "bad service!"])
def test_run_freeze_mock_rejects_unsafe_service_names(tmp_path: Path, service: str) -> None:
    with pytest.raises(FreezeError, match="mock service"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service=service)


def test_run_freeze_mock_rejects_invalid_generated_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_dependency_exchange(tmp_path)

    def invalid_mapping(*args: object, **kwargs: object) -> tuple[GeneratedWireMockMapping, ...]:
        _ = args, kwargs
        return (GeneratedWireMockMapping("mocks/payments/refund_flow-001.json", "{"),)

    monkeypatch.setattr(freeze, "compile_traffic_session_to_wiremock", invalid_mapping)

    with pytest.raises(FreezeError, match="Expecting property name"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")


def test_run_freeze_mock_rejects_low_confidence_records(tmp_path: Path) -> None:
    _record_low_confidence_freeze_exchange(tmp_path, secret="mock-low-confidence")

    with pytest.raises(FreezeError, match="refusing to write mock freeze artifacts"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")

    assert not (tmp_path / "mocks" / "payments" / "refund_flow-001.json").exists()


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("tests\\generated\\flow.hurl", "POSIX separators"),
        ("../flow.hurl", "stay inside"),
        ("tests/manual/flow.hurl", "tests/generated"),
        ("tests/generated/flow.txt", "tests/generated"),
    ],
)
def test_generated_hurl_path_validation_rejects_unsafe_paths(
    tmp_path: Path,
    relative_path: str,
    message: str,
) -> None:
    generated = GeneratedTrafficHurlFile(relative_path=relative_path, content="GET https://x.test")

    with pytest.raises(FreezeError, match=message):
        freeze._resolve_generated_hurl_path(generated, root=tmp_path)


def test_generated_hurl_path_validation_rejects_non_file_target(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "generated" / "flow.hurl"
    target.mkdir(parents=True)

    with pytest.raises(FreezeError, match="non-file generated Hurl"):
        freeze._resolve_generated_hurl_path(
            GeneratedTrafficHurlFile("tests/generated/flow.hurl", "GET https://x.test"),
            root=tmp_path,
        )


def test_generated_hurl_path_validation_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "tests" / "generated" / "flow.hurl"
    output.parent.mkdir(parents=True)
    outside = tmp_path / "outside.hurl"
    outside.write_text("GET https://x.test\n", encoding="utf-8")
    output.symlink_to(outside)
    monkeypatch.setattr(freeze, "_reject_symlink_path", lambda *args, **kwargs: None)

    with pytest.raises(FreezeError, match="tests/generated"):
        freeze._resolve_generated_hurl_path(
            GeneratedTrafficHurlFile("tests/generated/flow.hurl", "GET https://x.test"),
            root=tmp_path,
        )


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("mocks\\payments\\flow.json", "POSIX separators"),
        ("../flow.json", "stay inside"),
        ("tests/generated/flow.json", "mocks/<service>"),
        ("mocks/payments/flow.txt", "mocks/<service>"),
    ],
)
def test_wiremock_mapping_path_validation_rejects_unsafe_paths(
    tmp_path: Path,
    relative_path: str,
    message: str,
) -> None:
    generated = GeneratedWireMockMapping(relative_path=relative_path, content="{}")

    with pytest.raises(FreezeError, match=message):
        freeze._resolve_wiremock_mapping_path(generated, root=tmp_path)


def test_wiremock_mapping_path_validation_rejects_non_file_target(tmp_path: Path) -> None:
    target = tmp_path / "mocks" / "payments" / "flow.json"
    target.mkdir(parents=True)

    with pytest.raises(FreezeError, match="non-file WireMock mapping"):
        freeze._resolve_wiremock_mapping_path(
            GeneratedWireMockMapping("mocks/payments/flow.json", "{}"),
            root=tmp_path,
        )


def test_wiremock_mapping_path_validation_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "mocks" / "payments" / "flow.json"
    output.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    output.symlink_to(outside)
    monkeypatch.setattr(freeze, "_reject_symlink_path", lambda *args, **kwargs: None)

    with pytest.raises(FreezeError, match="under mocks"):
        freeze._resolve_wiremock_mapping_path(
            GeneratedWireMockMapping("mocks/payments/flow.json", "{}"),
            root=tmp_path,
        )
