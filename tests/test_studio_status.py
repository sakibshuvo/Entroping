"""Unit tests for the read-only Studio status shell."""

import json
from pathlib import Path

from entroping.studio.status import collect_studio_status, render_studio_status


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
