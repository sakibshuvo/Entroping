"""Tests for sanitized run execution event logs."""

import json
from pathlib import Path

import pytest

from entroping.core import run_event_log
from entroping.core.run_event_log import RunEventLog, RunEventLogError
from entroping.core.safe_write import SafeWriteError


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_event_log_records_failed_stdout_with_redaction(tmp_path: Path) -> None:
    log = RunEventLog.open_project(tmp_path)

    log.record_test_result(
        path="tests/health.hurl",
        status="failed",
        exit_code=1,
        duration_ms=12,
        timeout_ms=30_000,
        rule_ids=("no_server_errors",),
        operation_id=None,
        stdout="Authorization: Bearer live-secret\nassert failed",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
    )

    content = log.path.read_text(encoding="utf-8")
    assert "live-secret" not in content
    event = _read_jsonl(log.path)[0]
    assert event["stdout"] == "Authorization: [REDACTED]\nassert failed"


def test_event_log_renders_external_paths_as_absolute(tmp_path: Path) -> None:
    project = tmp_path / "project"
    external = tmp_path / "external" / "artifact.json"
    log = RunEventLog.open_project(project)

    log.record_artifact(artifact_type="external", path=external)

    event = _read_jsonl(log.path)[0]
    assert event["path"] == str(external.resolve())


def test_event_log_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = RunEventLog.open_project(tmp_path)

    def fail_safe_write_text(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = (path, content, artifact, root)
        raise SafeWriteError("blocked")

    monkeypatch.setattr(run_event_log, "safe_write_text", fail_safe_write_text)

    with pytest.raises(RunEventLogError, match="blocked"):
        log.record_completed(
            status="error",
            exit_code=1,
            duration_ms=1,
            total=0,
            passed=0,
            failed=0,
        )
