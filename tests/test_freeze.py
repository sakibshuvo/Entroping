"""Tests for the freeze workflow filesystem boundary."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from entroping.core.freeze import FreezeError, run_freeze
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

    assert victim.read_text(encoding="utf-8") == "victim\n"
