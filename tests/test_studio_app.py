"""Unit tests for the interactive Studio TUI adapter boundary."""

import importlib
import sys
from pathlib import Path

import pytest

import entroping.studio.app as studio_app
from entroping.core.evidence_index import LocalEvidenceArtifact
from entroping.studio.app import TextualTypes, build_studio_view_model, run_studio_app
from entroping.studio.status import (
    LatestRunStatus,
    LatestRunTestStatus,
    StudioAppliedGateStatus,
    StudioDependencyError,
    StudioStatus,
    StudioTrafficRedactionStatus,
    StudioTrafficRouteStatus,
)


def test_studio_app_does_not_disable_type_checking() -> None:
    source = Path(studio_app.__file__).read_text(encoding="utf-8")

    assert "no_type_check" not in source


def test_studio_app_module_does_not_import_textual_at_import_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "textual", raising=False)

    importlib.reload(studio_app)

    assert "textual" not in sys.modules


def test_build_studio_view_model_exposes_summary_suite_failures_reports_and_traffic() -> None:
    status = StudioStatus(
        environment="local",
        project="checkout-api",
        qanstitution_status="ok",
        latest_run=LatestRunStatus(
            generated_at="2026-05-31T12:00:00+00:00",
            passed=1,
            failed=1,
            total=2,
            exit_code=1,
            tests=(
                LatestRunTestStatus(
                    path="tests/health.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=("global_latency",),
                    stderr="",
                ),
                LatestRunTestStatus(
                    path="tests/checkout.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=25,
                    rule_ids=("global_latency", "auth_required"),
                    stderr="assertion failed\nsecret-token",
                ),
            ),
        ),
        latest_run_status="ok",
        report_paths=("reports/run-latest.json", "reports/drift.json"),
        evidence_artifacts=(
            LocalEvidenceArtifact(
                id="drift-json",
                label="Drift JSON",
                path="reports/drift.json",
                state="present",
                schema_version="entroping.drift-report.v1",
                summary="0 findings, 0 drifted",
            ),
            LocalEvidenceArtifact(
                id="run-json",
                label="Run JSON",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
                summary="2 total, 1 passed, 1 failed",
            ),
        ),
        traffic_state_available=True,
        applied_gates=(
            StudioAppliedGateStatus(
                rule_id="global_latency",
                test_path="tests/health.hurl",
                test_status="passed",
                enforcement="block",
                condition="true",
                assertion="duration < 2000",
            ),
            StudioAppliedGateStatus(
                rule_id="auth_required",
                test_path="tests/checkout.hurl",
                test_status="failed",
                enforcement="unknown",
                condition="unknown",
                assertion="unknown",
            ),
        ),
        traffic_state_status="ok",
        traffic_record_count=3,
        traffic_redacted_count=3,
        traffic_routes=(
            StudioTrafficRouteStatus(
                role="target",
                destination_host="api.example.test",
                method="GET",
                path_template="/orders/{id}",
                call_count=2,
                failure_count=1,
                latency_average_ms=150,
            ),
            StudioTrafficRouteStatus(
                role="dependency",
                destination_host="payments.example.test",
                method="POST",
                path_template="/charge",
                call_count=1,
                failure_count=0,
                latency_average_ms=None,
            ),
        ),
        traffic_redactions=(
            StudioTrafficRedactionStatus(
                category="request authorization header",
                count=3,
            ),
            StudioTrafficRedactionStatus(
                category="request password body field",
                count=3,
            ),
        ),
    )

    model = build_studio_view_model(status)

    assert model.summary_rows == (
        ("Environment", "local"),
        ("Project", "checkout-api"),
        ("QAnstitution", "ok"),
        ("Latest run", "1 passed, 1 failed, 2 total"),
        ("Exit code", "1"),
        ("Generated", "2026-05-31T12:00:00+00:00"),
    )
    assert model.suite_rows == (
        ("tests/health.hurl", "passed", "0", "10 ms", "global_latency"),
        ("tests/checkout.hurl", "failed", "1", "25 ms", "auth_required, global_latency"),
    )
    assert model.failure_rows == (
        ("tests/checkout.hurl", "exit 1", "assertion failed"),
    )
    assert model.gate_rows == (
        (
            "global_latency",
            "tests/health.hurl",
            "block",
            "passed",
            "true",
            "duration < 2000",
        ),
        (
            "auth_required",
            "tests/checkout.hurl",
            "unknown",
            "failed",
            "unknown",
            "unknown",
        ),
    )
    assert model.report_rows == (
        (
            "drift-json",
            "present",
            "reports/drift.json",
            "entroping.drift-report.v1",
            "0 findings, 0 drifted",
        ),
        (
            "run-json",
            "present",
            "reports/run-latest.json",
            "entroping.run-report.v1",
            "2 total, 1 passed, 1 failed",
        ),
    )
    assert model.traffic_rows == (
        ("summary", "traffic records", "-", "-", "3", "-", "-", "3/3 redacted"),
        (
            "redaction",
            "request authorization header",
            "-",
            "-",
            "3",
            "-",
            "-",
            "safe category count",
        ),
        (
            "redaction",
            "request password body field",
            "-",
            "-",
            "3",
            "-",
            "-",
            "safe category count",
        ),
        ("target", "api.example.test", "GET", "/orders/{id}", "2", "1", "150 ms", "redacted"),
        (
            "dependency",
            "payments.example.test",
            "POST",
            "/charge",
            "1",
            "0",
            "n/a",
            "redacted",
        ),
    )


def test_build_studio_view_model_handles_absent_latest_run_reports_and_traffic() -> None:
    status = StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=(),
        traffic_state_available=False,
    )

    model = build_studio_view_model(status)

    assert model.summary_rows[-1] == ("Latest run", "none")
    assert model.suite_rows == (("No latest run found", "", "", "", ""),)
    assert model.failure_rows == (("No failed tests", "", ""),)
    assert model.gate_rows == (("No applied gates found", "", "", "", "", ""),)
    assert model.report_rows == (("No evidence artifacts found", "", "", "", ""),)
    assert model.traffic_rows == (("state", "missing", "", "", "", "", "", ""),)


def test_build_studio_view_model_exposes_unsafe_evidence_artifact_rows() -> None:
    status = StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=(),
        traffic_state_available=False,
        evidence_artifacts=(
            LocalEvidenceArtifact(
                id="run-json",
                label="Run JSON",
                path="reports/run-latest.json",
                state="unsafe",
                schema_version=None,
                summary="symlinked path component",
            ),
        ),
    )

    model = build_studio_view_model(status)

    assert model.report_rows == (
        (
            "run-json",
            "unsafe",
            "reports/run-latest.json",
            "-",
            "symlinked path component",
        ),
    )


def test_build_studio_view_model_preserves_legacy_report_paths_without_evidence_index() -> None:
    status = StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=("reports/run-latest.json",),
        traffic_state_available=False,
    )

    model = build_studio_view_model(status)

    assert model.report_rows == (
        (
            "legacy-report",
            "present",
            "reports/run-latest.json",
            "-",
            "report path present",
        ),
    )


def test_build_studio_view_model_handles_traffic_state_errors() -> None:
    status = StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=(),
        traffic_state_available=True,
        traffic_state_status="error: could not read traffic state",
    )

    model = build_studio_view_model(status)

    assert model.traffic_rows == (
        ("state", "error: could not read traffic state", "", "", "", "", "", ""),
    )


def test_build_studio_view_model_handles_failed_test_without_stderr() -> None:
    status = StudioStatus(
        environment="local",
        project="checkout-api",
        qanstitution_status="ok",
        latest_run=LatestRunStatus(
            generated_at="2026-05-31T12:00:00+00:00",
            passed=0,
            failed=1,
            total=1,
            exit_code=1,
            tests=(
                LatestRunTestStatus(
                    path="tests/checkout.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=25,
                    rule_ids=(),
                    stderr="",
                ),
            ),
        ),
        latest_run_status="ok",
        report_paths=(),
        traffic_state_available=False,
    )

    model = build_studio_view_model(status)

    assert model.suite_rows == (("tests/checkout.hurl", "failed", "1", "25 ms", "-"),)
    assert model.failure_rows == (("tests/checkout.hurl", "exit 1", ""),)


def test_run_studio_app_launches_lazily_created_textual_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=(),
        traffic_state_available=False,
    )
    launched: list[bool] = []
    created_models: list[studio_app.StudioViewModel] = []

    class FakeApp:
        def run(self) -> object:
            launched.append(True)
            return None

    def fake_create_textual_app(model: studio_app.StudioViewModel) -> FakeApp:
        created_models.append(model)
        return FakeApp()

    monkeypatch.setattr(studio_app, "_load_textual_types", lambda: TextualTypes())
    monkeypatch.setattr(studio_app, "_create_textual_app", fake_create_textual_app)

    run_studio_app(status)

    assert launched == [True]
    assert created_models[0].summary_rows[-1] == ("Latest run", "none")


def test_run_studio_app_wraps_missing_textual_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    status = StudioStatus(
        environment="default",
        project="not configured",
        qanstitution_status="missing",
        latest_run=None,
        latest_run_status="none",
        report_paths=(),
        traffic_state_available=False,
    )

    def fail_load_textual() -> studio_app.TextualTypes:
        raise ModuleNotFoundError("textual")

    monkeypatch.setattr(studio_app, "_load_textual_types", fail_load_textual)

    with pytest.raises(StudioDependencyError, match="uv sync --extra studio"):
        run_studio_app(status)


def test_render_table_pads_columns_and_handles_short_rows() -> None:
    rendered = studio_app._render_table(
        ("Name", "Value"),
        (
            ("long-name", "1"),
            ("short",),
        ),
    )

    assert rendered.splitlines() == [
        "Name       Value",
        "---------  -----",
        "long-name  1",
        "short",
    ]
