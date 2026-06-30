"""Value-free structured diagnostics for headless Entroping operation."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from entroping.core.bounded_read import BoundedReadError, read_text_bounded
from entroping.core.evidence_common import LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
from entroping.core.safe_write import SafeWriteError, safe_append_text, safe_write_text
from entroping.models.secrets import (
    contains_secret_like_value,
    has_disallowed_control,
    is_sensitive_key,
    redact_secret_like_values,
)

STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION: Final = "entroping.diagnostics.v1"
_MAX_DIAGNOSTIC_EVENT_LOG_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES

type DiagnosticSeverity = Literal["debug", "info", "warning", "error"]
type DiagnosticAttributeValue = str | int | float | bool | None
DiagnosticIdentifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,95}$"),
]
DiagnosticComponent = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$"),
]
DiagnosticAttributeName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$"),
]
DiagnosticSummary = Annotated[str, StringConstraints(min_length=1, max_length=240)]

_DIAGNOSTIC_LOG_NAME: Final = "latest-diagnostics.jsonl"
_FORBIDDEN_ATTRIBUTE_NAMES: Final = frozenset(
    {
        "body",
        "cookie",
        "env",
        "env_value",
        "environment_value",
        "full_source_hurl",
        "headers",
        "prompt",
        "provider_output",
        "raw_body",
        "raw_headers",
        "request",
        "request_body",
        "request_headers",
        "response",
        "response_body",
        "response_headers",
        "secret",
        "source",
        "source_hurl",
        "traffic",
        "variable_value",
    }
)


class StructuredDiagnosticsError(ValueError):
    """Raised when structured diagnostic evidence is unsafe or malformed."""


class StructuredDiagnosticAttribute(BaseModel):
    """One value-free diagnostic attribute."""

    model_config = ConfigDict(extra="forbid")

    name: DiagnosticAttributeName
    value: DiagnosticAttributeValue

    @field_validator("name")
    @classmethod
    def _name_must_be_value_free(cls, value: str) -> str:
        return _safe_attribute_name(value)

    @field_validator("value")
    @classmethod
    def _value_must_be_safe(cls, value: object) -> DiagnosticAttributeValue:
        return _safe_attribute_value("attribute", value)


class StructuredDiagnosticEvent(BaseModel):
    """One local structured diagnostic event."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.diagnostics.v1"] = (
        STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION
    )
    timestamp: str
    component: DiagnosticComponent
    operation: DiagnosticIdentifier
    severity: DiagnosticSeverity
    code: DiagnosticIdentifier
    summary: DiagnosticSummary
    attributes: tuple[StructuredDiagnosticAttribute, ...] = ()

    @field_validator("timestamp", "component", "operation", "code", "summary")
    @classmethod
    def _text_fields_must_be_safe(cls, value: str, info: ValidationInfo) -> str:
        return _safe_text(value, field=info.field_name or "field")


@dataclass(slots=True)
class StructuredDiagnosticLog:
    """JSONL writer for local headless diagnostic evidence."""

    project_root: Path
    path: Path
    _initialized: bool = False

    @classmethod
    def open_project(cls, project_root: Path) -> "StructuredDiagnosticLog":
        root = project_root.expanduser().resolve()
        return cls(
            project_root=root,
            path=root / ".entroping" / _DIAGNOSTIC_LOG_NAME,
        )

    def record(self, event: StructuredDiagnosticEvent) -> None:
        line = json.dumps(
            diagnostic_event_to_dict(event),
            sort_keys=True,
            separators=(",", ":"),
        )
        self._write_line(line + "\n")

    def _write_line(self, line: str) -> None:
        try:
            if self._initialized:
                safe_append_text(
                    self.path,
                    line,
                    artifact="structured diagnostics log",
                    root=self.project_root,
                )
            else:
                safe_write_text(
                    self.path,
                    line,
                    artifact="structured diagnostics log",
                    root=self.project_root,
                )
                self._initialized = True
        except SafeWriteError as exc:
            raise StructuredDiagnosticsError(str(exc)) from exc


def build_diagnostic_event(
    *,
    component: str,
    operation: str,
    severity: DiagnosticSeverity,
    code: str,
    summary: str,
    attributes: Mapping[str, object] | None = None,
    timestamp: str | None = None,
) -> StructuredDiagnosticEvent:
    """Build a sanitized, value-free structured diagnostic event."""

    try:
        return StructuredDiagnosticEvent(
            timestamp=timestamp or datetime.now(UTC).isoformat(),
            component=_safe_text(component, field="component"),
            operation=_safe_text(operation, field="operation"),
            severity=severity,
            code=_safe_text(code, field="code"),
            summary=_safe_text(summary, field="summary"),
            attributes=tuple(
                StructuredDiagnosticAttribute(
                    name=_safe_attribute_name(name),
                    value=_safe_attribute_value(name, value),
                )
                for name, value in sorted((attributes or {}).items())
            ),
        )
    except ValidationError as exc:
        msg = "structured diagnostic event failed schema validation"
        raise StructuredDiagnosticsError(msg) from exc


def diagnostic_event_to_dict(event: StructuredDiagnosticEvent) -> dict[str, object]:
    """Serialize a structured diagnostic event to its public v1 payload."""

    return event.model_dump(mode="json")


def read_diagnostic_events(path: Path) -> list[StructuredDiagnosticEvent]:
    """Read diagnostic events, ignoring one incomplete trailing JSONL record."""

    if not path.exists():
        return []
    try:
        content = read_text_bounded(
            path,
            max_bytes=_MAX_DIAGNOSTIC_EVENT_LOG_BYTES,
            label="diagnostic event log",
        )
    except BoundedReadError as exc:
        raise StructuredDiagnosticsError(str(exc)) from exc
    events: list[StructuredDiagnosticEvent] = []
    lines = content.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == len(lines) and not content.endswith("\n"):
                break
            msg = f"diagnostic event log contains invalid JSON on line {line_number}"
            raise StructuredDiagnosticsError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"diagnostic event log line {line_number} is not an object"
            raise StructuredDiagnosticsError(msg)
        try:
            events.append(StructuredDiagnosticEvent.model_validate(payload))
        except ValidationError as exc:
            msg = f"diagnostic event log contains invalid event on line {line_number}"
            raise StructuredDiagnosticsError(msg) from exc
    return events


def _safe_attribute_name(name: str) -> str:
    raw_name = name.lower()
    if raw_name in _FORBIDDEN_ATTRIBUTE_NAMES or is_sensitive_key(raw_name):
        msg = f"diagnostic attribute {raw_name!r} is not a value-free attribute name"
        raise StructuredDiagnosticsError(msg)
    normalized = _safe_text(name, field="attribute name")
    if normalized in _FORBIDDEN_ATTRIBUTE_NAMES or is_sensitive_key(normalized):
        msg = f"diagnostic attribute {normalized!r} is not a value-free attribute name"
        raise StructuredDiagnosticsError(msg)
    return normalized


def _safe_attribute_value(name: str, value: object) -> DiagnosticAttributeValue:
    if value is None:
        return None
    if type(value) in {bool, int, float}:
        return cast(bool | int | float, value)
    if isinstance(value, str):
        return _safe_text(value, field=f"attribute {name}")
    msg = f"unsupported attribute value for {name!r}"
    raise StructuredDiagnosticsError(msg)


def _safe_text(value: str, *, field: str) -> str:
    if has_disallowed_control(value):
        msg = f"diagnostic {field} must not contain control characters"
        raise StructuredDiagnosticsError(msg)
    normalized = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    redacted = redact_secret_like_values(normalized)
    if contains_secret_like_value(redacted):
        msg = f"diagnostic {field} contains secret-like content"
        raise StructuredDiagnosticsError(msg)
    return redacted
