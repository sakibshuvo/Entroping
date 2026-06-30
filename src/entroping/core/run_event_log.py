"""Sanitized JSONL execution event logs for deterministic runs."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from entroping.core.bounded_read import BoundedReadError, read_text_bounded
from entroping.core.evidence_common import LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
from entroping.core.hurl_runner import redact_hurl_output
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_append_text, safe_write_text

RUN_EVENT_LOG_SCHEMA_VERSION = "entroping.run-events.v1"
RUN_EVENT_LOG_LOCK_NAME = "latest-run-events.lock"
_MAX_RUN_EVENT_LOG_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES


class RunEventLogError(RuntimeError):
    """Raised when execution event evidence cannot be written safely."""


def read_run_events(path: Path) -> list[dict[str, object]]:
    """Read valid run events, ignoring one incomplete trailing JSONL record."""

    if not path.exists():
        return []
    try:
        content = read_text_bounded(
            path,
            max_bytes=_MAX_RUN_EVENT_LOG_BYTES,
            label="run event log",
        )
    except BoundedReadError as exc:
        raise RunEventLogError(str(exc)) from exc
    events: list[dict[str, object]] = []
    lines = content.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == len(lines) and not content.endswith("\n"):
                break
            msg = f"run event log contains invalid JSON on line {line_number}"
            raise RunEventLogError(msg) from exc
        if not isinstance(event, dict):
            msg = f"run event log line {line_number} is not an object"
            raise RunEventLogError(msg)
        events.append(event)
    return events


@dataclass(slots=True)
class RunEventLog:
    """JSONL writer for latest run progress evidence."""

    project_root: Path
    path: Path
    lock_path: Path
    _initialized: bool = False

    @classmethod
    def open_project(cls, project_root: Path) -> "RunEventLog":
        root = project_root.expanduser().resolve()
        state_dir = root / ".entroping"
        _reject_lock_symlink_components(state_dir / RUN_EVENT_LOG_LOCK_NAME, root=root)
        state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = state_dir / RUN_EVENT_LOG_LOCK_NAME
        _acquire_latest_writer_lock(lock_path, root=root)
        return cls(
            project_root=root,
            path=root / ".entroping" / "latest-run-events.jsonl",
            lock_path=lock_path,
        )

    def close(self) -> None:
        """Release the latest event-log writer lock."""

        try:
            self.lock_path.rmdir()
        except OSError as exc:
            msg = f"Could not release run event log lock {self.lock_path}: {exc}"
            raise RunEventLogError(msg) from exc

    def record_started(
        self,
        *,
        environment: str | None,
        tag_filters: tuple[str, ...],
        tag_expression: str | None,
        operation_ids: tuple[str, ...],
        report_formats: tuple[str, ...],
        parallel: bool,
        fail_fast: bool,
        drift_check: bool,
        changed_from: str | None,
    ) -> None:
        self._append(
            "run_started",
            environment=environment or "default",
            tag_filters=list(tag_filters),
            tag_expression=tag_expression,
            operation_ids=list(operation_ids),
            report_formats=list(report_formats),
            parallel=parallel,
            fail_fast=fail_fast,
            drift_check=drift_check,
            changed_from=changed_from,
        )

    def record_test_selected(
        self,
        *,
        path: Path,
        tags: tuple[str, ...],
        operation_id: str | None,
        rule_ids: tuple[str, ...],
    ) -> None:
        self._append(
            "test_selected",
            path=self._display_path(path),
            tags=list(tags),
            operation_id=operation_id,
            rule_ids=list(rule_ids),
        )

    def record_test_result(
        self,
        *,
        path: str,
        status: str,
        exit_code: int,
        duration_ms: int,
        timeout_ms: int,
        rule_ids: tuple[str, ...],
        operation_id: str | None,
        stdout: str,
        stderr: str,
        stdout_truncated: bool,
        stderr_truncated: bool,
    ) -> None:
        fields: dict[str, object] = {
            "path": path,
            "status": status,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timeout_ms": timeout_ms,
            "rule_ids": list(rule_ids),
            "operation_id": operation_id,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        if status != "passed":
            if stdout:
                fields["stdout"] = redact_hurl_output(stdout)
            if stderr:
                fields["stderr"] = redact_hurl_output(stderr)
        self._append("test_result", **fields)

    def record_artifact(self, *, artifact_type: str, path: Path) -> None:
        self._append(
            "artifact_written",
            artifact_type=artifact_type,
            path=self._display_path(path),
        )

    def record_no_match(
        self,
        *,
        message: str,
        selected_count: int,
        skipped_count: int,
        discovered_count: int,
    ) -> None:
        self._append(
            "selection_no_match",
            message=redact_hurl_output(message),
            selected_count=selected_count,
            skipped_count=skipped_count,
            discovered_count=discovered_count,
        )

    def record_error(self, exc: BaseException) -> None:
        self._append(
            "run_error",
            error_type=type(exc).__name__,
            message=redact_hurl_output(str(exc)),
        )

    def record_completed(
        self,
        *,
        status: str,
        exit_code: int | None,
        duration_ms: int,
        total: int,
        passed: int,
        failed: int,
    ) -> None:
        self._append(
            "run_completed",
            status=status,
            exit_code=exit_code,
            duration_ms=duration_ms,
            total=total,
            passed=passed,
            failed=failed,
        )

    def _append(self, event: str, **fields: object) -> None:
        payload = {
            "schema_version": RUN_EVENT_LOG_SCHEMA_VERSION,
            "event": event,
            "timestamp": datetime.now(UTC).isoformat(),
            **fields,
        }
        self._write_line(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")

    def _write_line(self, line: str) -> None:
        try:
            if self._initialized:
                safe_append_text(
                    self.path,
                    line,
                    artifact="run event log",
                    root=self.project_root,
                )
            else:
                safe_write_text(
                    self.path,
                    line,
                    artifact="run event log",
                    root=self.project_root,
                )
                self._initialized = True
        except SafeWriteError as exc:
            raise RunEventLogError(str(exc)) from exc

    def _display_path(self, path: Path) -> str:
        resolved = path.expanduser().resolve()
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return resolved.as_posix()


def _acquire_latest_writer_lock(lock_path: Path, *, root: Path) -> None:
    _reject_lock_symlink_components(lock_path, root=root)
    try:
        lock_path.mkdir()
    except FileExistsError as exc:
        msg = (
            "Another entroping run is already active in this project root; "
            f"latest run event evidence is locked at {lock_path}. If no run is "
            "active, remove that stale directory and rerun."
        )
        raise RunEventLogError(msg) from exc
    except OSError as exc:
        msg = f"Could not acquire run event log lock {lock_path}: {exc}"
        raise RunEventLogError(msg) from exc
    _reject_lock_symlink_components(lock_path, root=root)


def _reject_lock_symlink_components(lock_path: Path, *, root: Path) -> None:
    symlink_component = first_symlink_path_component(lock_path, root=root)
    if symlink_component is None:
        return
    msg = (
        "Refusing to acquire run event log lock through symlinked path component: "
        f"{symlink_component}"
    )
    raise RunEventLogError(msg)
