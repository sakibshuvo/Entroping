"""Tests for sanitized run execution event logs."""

import json
from pathlib import Path

import pytest

from entroping.core import run_event_log, safe_write
from entroping.core.run_event_log import RunEventLog, RunEventLogError, read_run_events
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


def test_event_log_appends_after_initial_safe_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_safe_write_text = safe_write.safe_write_text
    original_safe_append_text = safe_write.safe_append_text
    rewrite_payloads: list[str] = []
    append_payloads: list[str] = []

    def spy_safe_write_text(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        rewrite_payloads.append(content)
        return original_safe_write_text(path, content, artifact=artifact, root=root)

    def spy_safe_append_text(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        append_payloads.append(content)
        return original_safe_append_text(path, content, artifact=artifact, root=root)

    monkeypatch.setattr(
        "entroping.core.run_event_log.safe_write_text",
        spy_safe_write_text,
    )
    monkeypatch.setattr(
        "entroping.core.run_event_log.safe_append_text",
        spy_safe_append_text,
    )
    log = RunEventLog.open_project(tmp_path)

    log.record_artifact(artifact_type="json-report", path=tmp_path / "reports" / "one.json")
    log.record_artifact(artifact_type="junit-report", path=tmp_path / "reports" / "two.xml")
    log.record_artifact(artifact_type="html-report", path=tmp_path / "reports" / "three.html")

    assert len(rewrite_payloads) == 1
    assert rewrite_payloads[0].count("\n") == 1
    assert len(append_payloads) == 2
    assert all(payload.count("\n") == 1 for payload in append_payloads)
    events = _read_jsonl(log.path)
    assert [event["artifact_type"] for event in events] == [
        "json-report",
        "junit-report",
        "html-report",
    ]


def test_event_log_initial_write_resets_stale_latest_events(tmp_path: Path) -> None:
    stale_log = tmp_path / ".entroping" / "latest-run-events.jsonl"
    stale_log.parent.mkdir()
    stale_log.write_text('{"event":"stale"}\n', encoding="utf-8")
    log = RunEventLog.open_project(tmp_path)

    log.record_artifact(artifact_type="json-report", path=tmp_path / "reports" / "one.json")

    events = _read_jsonl(log.path)
    assert [event["event"] for event in events] == ["artifact_written"]
    assert "stale" not in log.path.read_text(encoding="utf-8")


def test_event_log_rejects_concurrent_latest_writers(tmp_path: Path) -> None:
    log = RunEventLog.open_project(tmp_path)

    with pytest.raises(
        RunEventLogError,
        match="Another entroping run is already active.*remove that stale directory",
    ):
        RunEventLog.open_project(tmp_path)

    log.close()


def test_event_log_close_releases_latest_writer_lock(tmp_path: Path) -> None:
    first = RunEventLog.open_project(tmp_path)
    first.close()
    second = RunEventLog.open_project(tmp_path)

    second.record_artifact(artifact_type="json-report", path=tmp_path / "reports" / "one.json")

    events = _read_jsonl(second.path)
    assert [event["event"] for event in events] == ["artifact_written"]
    second.close()


def test_event_log_rejects_lock_through_symlinked_state_dir(tmp_path: Path) -> None:
    outside = tmp_path / "outside-state"
    outside.mkdir()
    (tmp_path / ".entroping").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RunEventLogError, match="symlinked path component"):
        RunEventLog.open_project(tmp_path)


def test_event_log_wraps_lock_acquire_os_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_mkdir = Path.mkdir

    def fail_lock_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if self.name == "latest-run-events.lock":
            raise OSError("disk failed")
        original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_lock_mkdir)

    with pytest.raises(RunEventLogError, match="Could not acquire run event log lock"):
        RunEventLog.open_project(tmp_path)


def test_event_log_wraps_lock_release_os_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = RunEventLog.open_project(tmp_path)

    def fail_rmdir(self: Path) -> None:
        if self.name == "latest-run-events.lock":
            raise OSError("busy")
        raise AssertionError(f"unexpected rmdir for {self}")

    monkeypatch.setattr(Path, "rmdir", fail_rmdir)

    with pytest.raises(RunEventLogError, match="Could not release run event log lock"):
        log.close()


def test_event_log_wraps_safe_append_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = RunEventLog.open_project(tmp_path)
    log.record_artifact(artifact_type="json-report", path=tmp_path / "reports" / "one.json")

    def fail_safe_append_text(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = (path, content, artifact, root)
        raise SafeWriteError("append blocked")

    monkeypatch.setattr(
        "entroping.core.run_event_log.safe_append_text",
        fail_safe_append_text,
    )

    with pytest.raises(RunEventLogError, match="append blocked"):
        log.record_artifact(artifact_type="junit-report", path=tmp_path / "reports" / "two.xml")


def test_read_run_events_recovers_valid_prefix_from_partial_trailing_line(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / ".entroping" / "latest-run-events.jsonl"
    log_path.parent.mkdir()
    log_path.write_text(
        '{"event":"run_started","schema_version":"entroping.run-events.v1"}\n'
        '{"event":"partial"',
        encoding="utf-8",
    )

    events = read_run_events(log_path)

    assert [event["event"] for event in events] == ["run_started"]


def test_read_run_events_rejects_complete_malformed_line(tmp_path: Path) -> None:
    log_path = tmp_path / ".entroping" / "latest-run-events.jsonl"
    log_path.parent.mkdir()
    log_path.write_text(
        '{"event":"run_started","schema_version":"entroping.run-events.v1"}\n'
        "not-json\n",
        encoding="utf-8",
    )

    with pytest.raises(RunEventLogError, match="invalid JSON on line 2"):
        read_run_events(log_path)


def test_read_run_events_rejects_non_object_line(tmp_path: Path) -> None:
    log_path = tmp_path / ".entroping" / "latest-run-events.jsonl"
    log_path.parent.mkdir()
    log_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(RunEventLogError, match="line 1 is not an object"):
        read_run_events(log_path)


def test_read_run_events_rejects_oversized_log_before_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / ".entroping" / "latest-run-events.jsonl"
    log_path.parent.mkdir()
    content = '{"event":"run_started","schema_version":"entroping.run-events.v1"}\n'
    log_path.write_text(content, encoding="utf-8")
    original_read_text = Path.read_text

    def reject_full_log_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == log_path:
            msg = "run event log used unbounded read_text"
            raise AssertionError(msg)
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(
        run_event_log,
        "_MAX_RUN_EVENT_LOG_BYTES",
        len(content) - 1,
    )
    monkeypatch.setattr(Path, "read_text", reject_full_log_read)

    with pytest.raises(RunEventLogError, match="run event log .* exceeds"):
        read_run_events(log_path)


def test_read_run_events_skips_blank_lines(tmp_path: Path) -> None:
    log_path = tmp_path / ".entroping" / "latest-run-events.jsonl"
    log_path.parent.mkdir()
    log_path.write_text(
        "\n"
        '{"event":"run_started","schema_version":"entroping.run-events.v1"}\n',
        encoding="utf-8",
    )

    events = read_run_events(log_path)

    assert [event["event"] for event in events] == ["run_started"]


def test_read_run_events_returns_empty_list_when_log_is_missing(tmp_path: Path) -> None:
    assert read_run_events(tmp_path / ".entroping" / "latest-run-events.jsonl") == []
