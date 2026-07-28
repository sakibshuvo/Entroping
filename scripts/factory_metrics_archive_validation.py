from __future__ import annotations

import json
from typing import cast

from scripts.factory_metrics_modules.common import contains_secret_like
from scripts.factory_metrics_modules.events import validate_event

_MAX_LEDGER_EVENTS = 100_000
_MAX_JSON_NODES = 100_000


class FactoryMetricsArchiveValidationError(RuntimeError):
    pass


def validate_ledger_payload(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FactoryMetricsArchiveValidationError(
            "factory metrics ledger must contain valid UTF-8"
        ) from exc
    if contains_secret_like(text):
        raise FactoryMetricsArchiveValidationError(
            "factory metrics ledger contains unredacted secret-like data"
        )
    event_count = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        event_count += 1
        if event_count > _MAX_LEDGER_EVENTS:
            raise FactoryMetricsArchiveValidationError(
                "factory metrics ledger exceeds the event limit"
            )
        try:
            value = cast(object, json.loads(line, object_pairs_hook=_unique_object))
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise FactoryMetricsArchiveValidationError(
                "factory metrics ledger contains invalid JSON"
            ) from exc
        if (
            _contains_decoded_secret(value)
            or not isinstance(value, dict)
            or validate_event(cast(dict[str, object], value))
        ):
            raise FactoryMetricsArchiveValidationError(
                "factory metrics ledger contains an invalid event"
            )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _contains_decoded_secret(value: object) -> bool:
    pending = [value]
    inspected = 0
    while pending:
        inspected += 1
        if inspected > _MAX_JSON_NODES:
            raise FactoryMetricsArchiveValidationError(
                "factory metrics event exceeds the structure limit"
            )
        current = pending.pop()
        if isinstance(current, str):
            if contains_secret_like(current):
                return True
        elif isinstance(current, dict):
            mapping = cast(dict[object, object], current)
            pending.extend(mapping.keys())
            pending.extend(mapping.values())
        elif isinstance(current, list):
            pending.extend(cast(list[object], current))
    return False
