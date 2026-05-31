"""Unit tests for read-only Studio status collection."""

import json
from pathlib import Path

import pytest

import entroping.studio.status as studio_status
from entroping.core.config_loader import QanstitutionLoadError
from entroping.studio.status import (
    StudioDependencyError,
    collect_studio_status,
    ensure_studio_available,
    render_studio_status,
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
        'project: "checkout-api"\ngates: []\n',
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
    assert status.report_paths == ("reports/junit.xml", "reports/run-latest.json")
    assert status.traffic_state_available
    assert "Latest run: 1 passed, 1 failed, 2 total" in rendered
    assert "Traffic state: available" in rendered
