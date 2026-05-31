"""Unit tests for read-only Studio status collection."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import entroping.studio.status as studio_status
from entroping.core.config_loader import QanstitutionLoadError
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse
from entroping.studio.status import (
    StudioDependencyError,
    collect_studio_status,
    ensure_studio_available,
    render_studio_status,
)

BASE_TIME = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


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

    with pytest.raises(StudioDependencyError, match="uv sync --extra studio"):
        ensure_studio_available()


def test_collect_studio_status_without_latest_run(tmp_path: Path) -> None:
    (tmp_path / "qanstitution.yaml").write_text(
        'project: "checkout-api"\ngates: []\n',
        encoding="utf-8",
    )

    status = collect_studio_status(project_root=tmp_path, environment="local")

    assert status.environment == "local"
    assert status.project == "checkout-api"
    assert status.qanstitution_status == "ok"
    assert status.latest_run is None
    assert not status.traffic_state_available
    rendered = render_studio_status(status)
    assert "Latest run: none" in rendered
    assert "Reports: none" in rendered


def test_collect_studio_status_without_qanstitution(tmp_path: Path) -> None:
    status = collect_studio_status(project_root=tmp_path, environment=None)

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

    status = collect_studio_status(project_root=tmp_path, environment=None)

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

    status = collect_studio_status(project_root=tmp_path, environment=None)

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

    status = collect_studio_status(project_root=tmp_path, environment=None)
    rendered = render_studio_status(status)

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

    status = collect_studio_status(project_root=tmp_path, environment="local")
    after = (tmp_path / ".entroping" / "state.db").stat().st_mtime_ns
    rendered = render_studio_status(status)
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

    status = collect_studio_status(project_root=tmp_path, environment=None)

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

    status = collect_studio_status(project_root=tmp_path, environment=None)

    assert status.traffic_state_available
    assert status.traffic_state_status == "error: traffic store failed"
    assert status.traffic_routes == ()
