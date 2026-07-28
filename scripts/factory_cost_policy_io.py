from __future__ import annotations

import json
from pathlib import Path
from typing import Never, cast

from entroping.core.evidence_common import read_local_evidence_artifact_bytes

from .ai_worker_file_safety import secret_like_content_reason
from .factory_cost_policy_validation import FactoryCostPolicyError

POLICY_MAX_BYTES = 256 * 1024
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def read_policy_document(path: Path) -> str:
    raw_document, read_error = read_local_evidence_artifact_bytes(
        path,
        max_bytes=POLICY_MAX_BYTES,
    )
    if raw_document is None:
        raise FactoryCostPolicyError(
            code="policy_file",
            detail=f"could not safely read policy file ({read_error})",
        )
    try:
        document = raw_document.decode("utf-8")
    except UnicodeDecodeError:
        raise FactoryCostPolicyError(
            code="policy_file",
            detail="policy file must be valid UTF-8",
        ) from None
    secret_reason = secret_like_content_reason(document)
    if secret_reason is not None:
        raise FactoryCostPolicyError(
            code="policy_secret",
            detail=f"policy contains secret-like content ({secret_reason})",
        )
    parsed_document = _verify_unambiguous_json(document)
    _reject_secret_like_json(parsed_document)
    return document


def _verify_unambiguous_json(document: str) -> JsonValue:
    try:
        return cast(
            JsonValue,
            json.loads(
                document,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_non_finite,
                parse_int=_parse_bounded_int,
            ),
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else "nesting is too deep"
        raise FactoryCostPolicyError(
            code="policy_json",
            detail=f"invalid JSON: {detail}",
        ) from None


def _reject_secret_like_json(document: JsonValue) -> None:
    pending: list[JsonValue] = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            _reject_secret_like_text(value)
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            for key, nested_value in value.items():
                _reject_secret_like_text(key)
                pending.append(nested_value)


def _reject_secret_like_text(value: str) -> None:
    secret_reason = secret_like_content_reason(value)
    if secret_reason is not None:
        raise FactoryCostPolicyError(
            code="policy_secret",
            detail=f"policy contains secret-like content ({secret_reason})",
        )


def _reject_duplicate_pairs(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise FactoryCostPolicyError(
                code="policy_json",
                detail="duplicate JSON key is forbidden",
            )
        result[key] = value
    return result


def _parse_bounded_int(raw: str) -> int:
    value = int(raw)
    if not -(2**63) <= value <= (2**63) - 1:
        raise FactoryCostPolicyError(
            code="policy_json",
            detail="JSON integer exceeds the signed 64-bit boundary",
        )
    return value


def _reject_non_finite(raw: str) -> Never:
    raise FactoryCostPolicyError(
        code="policy_json",
        detail=f"non-finite JSON number is forbidden: {raw}",
    )
