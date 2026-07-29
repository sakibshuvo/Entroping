from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import final

from scripts.opencode_usage_receipt import AccountingReason, UsageTotals

MAX_USAGE_VALUE = 9_223_372_036_854_775_807
MAX_COST_USD = Decimal("1000000000")

JsonValue = (
    str
    | int
    | bool
    | Decimal
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)
JsonObject = dict[str, JsonValue]
UsageKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class UsagePart:
    message_id: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost: Decimal


@final
class UsageAccumulator:
    __slots__ = ("_parts",)

    def __init__(self) -> None:
        self._parts: dict[UsageKey, UsagePart] = {}

    @property
    def unique_step_count(self) -> int:
        return len(self._parts)

    def consume(self, part: JsonObject, session_id: str) -> set[AccountingReason]:
        issues: set[AccountingReason] = set()
        part_session = validated_identifier(part.get("sessionID"))
        part_id = validated_identifier(part.get("id"))
        message_id = validated_identifier(part.get("messageID"))
        if part_session is None or part_id is None or message_id is None:
            return {"malformed_usage"}
        if part_session != session_id:
            return {"inconsistent_session"}
        if "cost" not in part:
            return {"missing_cost"}
        cost = _cost_value(part.get("cost"))
        tokens = part.get("tokens")
        if cost is None or not isinstance(tokens, dict):
            return {"malformed_usage"}
        cache = tokens.get("cache")
        if not isinstance(cache, dict):
            return {"malformed_usage"}
        values = _token_values(tokens, cache)
        if values is None:
            return {"malformed_usage"}
        normalized = UsagePart(message_id, *values, cost)
        key: UsageKey = (session_id, part_id, "step_finish")
        existing = self._parts.get(key)
        if existing is not None:
            return {"conflicting_duplicate_usage"} if existing != normalized else set()
        if self._would_overflow(values, cost):
            return {"malformed_usage"}
        self._parts[key] = normalized
        if cost == 0 or float(cost) == 0.0:
            issues.add("ambiguous_zero_cost")
        return issues

    def totals(self) -> UsageTotals:
        token_totals = [0, 0, 0, 0, 0]
        cost_total = Decimal(0)
        for part in self._parts.values():
            for index, value in enumerate(
                (
                    part.input_tokens,
                    part.output_tokens,
                    part.reasoning_tokens,
                    part.cache_read_tokens,
                    part.cache_write_tokens,
                )
            ):
                token_totals[index] += value
            cost_total += part.cost
        return UsageTotals(
            input_tokens=token_totals[0],
            output_tokens=token_totals[1],
            reasoning_tokens=token_totals[2],
            cache_read_tokens=token_totals[3],
            cache_write_tokens=token_totals[4],
            cost_usd=float(cost_total),
        )

    def _would_overflow(
        self,
        values: tuple[int, int, int, int, int],
        cost: Decimal,
    ) -> bool:
        for index, value in enumerate(values):
            observed_total = sum(
                (
                    part.input_tokens,
                    part.output_tokens,
                    part.reasoning_tokens,
                    part.cache_read_tokens,
                    part.cache_write_tokens,
                )[index]
                for part in self._parts.values()
            )
            if observed_total + value > MAX_USAGE_VALUE:
                return True
        observed_cost = sum((part.cost for part in self._parts.values()), Decimal(0))
        return observed_cost + cost > MAX_COST_USD


def validated_identifier(value: JsonValue) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 256:
        return None
    return value


def _token_values(
    tokens: JsonObject,
    cache: JsonObject,
) -> tuple[int, int, int, int, int] | None:
    input_tokens = _bounded_token_value(tokens.get("input"))
    output_tokens = _bounded_token_value(tokens.get("output"))
    reasoning_tokens = _bounded_token_value(tokens.get("reasoning"))
    cache_read_tokens = _bounded_token_value(cache.get("read"))
    cache_write_tokens = _bounded_token_value(cache.get("write"))
    if any(
        value is None
        for value in (
            input_tokens,
            output_tokens,
            reasoning_tokens,
            cache_read_tokens,
            cache_write_tokens,
        )
    ):
        return None
    assert input_tokens is not None
    assert output_tokens is not None
    assert reasoning_tokens is not None
    assert cache_read_tokens is not None
    assert cache_write_tokens is not None
    return (
        input_tokens,
        output_tokens,
        reasoning_tokens,
        cache_read_tokens,
        cache_write_tokens,
    )


def _bounded_token_value(value: JsonValue) -> int | None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= MAX_USAGE_VALUE
    ):
        return None
    return value


def _cost_value(value: JsonValue) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        return None
    cost = Decimal(value)
    if not cost.is_finite() or cost < 0 or cost > MAX_COST_USD:
        return None
    try:
        converted = float(cost)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(converted):
        return None
    return cost
