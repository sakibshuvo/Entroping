from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol, final

from scripts.opencode_usage_aggregation import (
    JsonObject,
    JsonValue,
    UsageAccumulator,
    validated_identifier,
)
from scripts.opencode_usage_receipt import (
    AccountingReason,
    OpenCodeStreamSummary,
    OpenCodeUsageReceipt,
    ReceiptReason,
    build_usage_receipt,
)

MAX_EVENT_LINE_BYTES = 262_144
MAX_TEXT_BYTES = 262_144

__all__ = [
    "OpenCodeEventStream",
    "OpenCodeStreamSummary",
    "OpenCodeUsageReceipt",
    "ReceiptReason",
    "build_usage_receipt",
]


class OpenCodeEventStreamError(ValueError):
    pass


class JsonEventLoader(Protocol):
    def __call__(
        self,
        s: str | bytes | bytearray,
        *,
        object_pairs_hook: Callable[[list[tuple[str, JsonValue]]], JsonObject],
        parse_float: Callable[[str], Decimal],
        parse_constant: Callable[[str], None],
    ) -> JsonValue: ...


_load_json_event: JsonEventLoader = json.loads


@final
class OpenCodeEventStream:
    def __init__(
        self,
        *,
        max_event_line_bytes: int = MAX_EVENT_LINE_BYTES,
        max_text_bytes: int = MAX_TEXT_BYTES,
    ) -> None:
        if max_event_line_bytes <= 0 or max_text_bytes <= 0:
            raise OpenCodeEventStreamError("OpenCode event limits must be positive")
        self._max_event_line_bytes = max_event_line_bytes
        self._max_text_bytes = max_text_bytes
        self._buffer = bytearray()
        self._discarding_line = False
        self._finished = False
        self._text_parts: list[str] = []
        self._text_bytes = 0
        self._session_id: str | None = None
        self._session_inconsistent = False
        self._issues: set[AccountingReason] = set()
        self._saw_error_event = False
        self._usage = UsageAccumulator()

    def feed(self, chunk: bytes) -> None:
        if self._finished:
            raise OpenCodeEventStreamError("OpenCode event stream is already finished")
        if not chunk:
            return
        self._buffer.extend(chunk)
        self._consume_lines()

    def finish(self) -> OpenCodeStreamSummary:
        if self._finished:
            raise OpenCodeEventStreamError("OpenCode event stream is already finished")
        self._finished = True
        if self._discarding_line:
            self._issues.add("malformed_event")
        elif self._buffer:
            self._consume_line(bytes(self._buffer))
        self._buffer.clear()
        reason = self._accounting_reason()
        usage = self._usage.totals() if reason == "complete" else None
        session_fingerprint = None
        if self._session_id is not None and not self._session_inconsistent:
            session_fingerprint = hashlib.sha256(self._session_id.encode()).hexdigest()
        return OpenCodeStreamSummary(
            output_text="\n".join(self._text_parts),
            accounting_status="accounted" if reason == "complete" else "unaccounted",
            accounting_reason=reason,
            session_fingerprint=session_fingerprint,
            usage=usage,
            unique_step_count=self._usage.unique_step_count,
            saw_error_event=self._saw_error_event,
        )

    def _consume_lines(self) -> None:
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                if len(self._buffer) > self._max_event_line_bytes:
                    self._buffer.clear()
                    self._discarding_line = True
                    self._issues.add("malformed_event")
                return
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if self._discarding_line:
                self._discarding_line = False
                continue
            if len(line) > self._max_event_line_bytes:
                self._issues.add("malformed_event")
                continue
            self._consume_line(line.rstrip(b"\r"))

    def _consume_line(self, line: bytes) -> None:
        if not line:
            return
        event = _decode_event(line)
        if event is None:
            self._issues.add("malformed_event")
            return
        event_type = event.get("type")
        if event_type not in {
            "error",
            "reasoning",
            "step_finish",
            "step_start",
            "text",
            "tool_use",
        }:
            return
        session_id = validated_identifier(event.get("sessionID"))
        if session_id is None:
            self._issues.add("malformed_event")
            return
        self._observe_session(session_id)
        part = event.get("part")
        if isinstance(part, dict) and "sessionID" in part:
            part_session = validated_identifier(part.get("sessionID"))
            if part_session is None or part_session != session_id:
                self._mark_inconsistent_session()
                return
        if event_type == "text":
            self._consume_text(part)
        elif event_type == "step_finish":
            self._consume_usage(part, session_id)
        elif event_type == "error":
            self._saw_error_event = True
            self._issues.add("error_event")

    def _consume_text(self, part: JsonValue) -> None:
        if not isinstance(part, dict):
            self._issues.add("malformed_event")
            return
        text = part.get("text")
        if not isinstance(text, str):
            self._issues.add("malformed_event")
            return
        encoded = text.encode("utf-8")
        available = self._max_text_bytes - self._text_bytes
        if len(encoded) > available:
            if available > 0:
                retained = encoded[:available].decode("utf-8", errors="ignore")
                self._text_parts.append(retained)
                self._text_bytes += len(retained.encode("utf-8"))
            self._issues.add("text_limit_exceeded")
            return
        self._text_parts.append(text)
        self._text_bytes += len(encoded)

    def _consume_usage(self, part: JsonValue, session_id: str) -> None:
        if not isinstance(part, dict):
            self._issues.add("malformed_usage")
            return
        issues = self._usage.consume(part, session_id)
        self._issues.update(issues)
        if "inconsistent_session" in issues:
            self._session_inconsistent = True

    def _observe_session(self, session_id: str) -> None:
        if self._session_id is None:
            self._session_id = session_id
        elif self._session_id != session_id:
            self._mark_inconsistent_session()

    def _mark_inconsistent_session(self) -> None:
        self._session_inconsistent = True
        self._issues.add("inconsistent_session")

    def _accounting_reason(self) -> AccountingReason:
        priorities: tuple[AccountingReason, ...] = (
            "malformed_event",
            "malformed_usage",
            "conflicting_duplicate_usage",
            "inconsistent_session",
            "error_event",
            "text_limit_exceeded",
            "missing_cost",
            "ambiguous_zero_cost",
        )
        for reason in priorities:
            if reason in self._issues:
                return reason
        if self._usage.unique_step_count == 0:
            return "usage_absent"
        return "complete"


def _decode_event(line: bytes) -> JsonObject | None:
    try:
        decoded = line.decode("utf-8", errors="strict")
        event = _load_json_event(
            decoded,
            object_pairs_hook=_unique_object,
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        return None
    return event if isinstance(event, dict) else None


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    value: JsonObject = {}
    for key, item in pairs:
        if key in value:
            raise OpenCodeEventStreamError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_json_constant(_value: str) -> None:
    raise OpenCodeEventStreamError("non-finite JSON value")
