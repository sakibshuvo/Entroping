"""Sanitized JSONL execution event logs for deterministic runs."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from entroping.core.hurl_runner import redact_hurl_output
from entroping.core.safe_write import SafeWriteError, safe_write_text

RUN_EVENT_LOG_SCHEMA_VERSION = "entroping.run-events.v1"


class RunEventLogError(RuntimeError):
    """Raised when execution event evidence cannot be written safely."""


@dataclass(slots=True)
class RunEventLog:
    """Append-safe enough JSONL writer for latest run progress evidence."""

    project_root: Path
    path: Path
    _events: list[dict[str, object]] = field(default_factory=list)

    @classmethod
    def open_project(cls, project_root: Path) -> "RunEventLog":
        root = project_root.expanduser().resolve()
        return cls(
            project_root=root,
            path=root / ".entroping" / "latest-run-events.jsonl",
        )

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
        self._events.append(
            {
                "schema_version": RUN_EVENT_LOG_SCHEMA_VERSION,
                "event": event,
                "timestamp": datetime.now(UTC).isoformat(),
                **fields,
            }
        )
        self._write()

    def _write(self) -> None:
        content = "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in self._events
        )
        try:
            safe_write_text(
                self.path,
                content,
                artifact="run event log",
                root=self.project_root,
            )
        except SafeWriteError as exc:
            raise RunEventLogError(str(exc)) from exc

    def _display_path(self, path: Path) -> str:
        resolved = path.expanduser().resolve()
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return resolved.as_posix()
