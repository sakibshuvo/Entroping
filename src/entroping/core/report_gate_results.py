"""Strict validation and loading helpers for serialized gate evidence."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn, TypeGuard, cast

from entroping.core.report_fingerprint import _has_control_character
from entroping.models.qanstitution import Enforcement
from entroping.models.report import GateResult, GateResultEvidence


def _require_gate_results(
    raw_gate_results: object,
    *,
    path: Path,
    test_index: int,
) -> None:
    if raw_gate_results is None:
        return
    if not isinstance(raw_gate_results, list):
        _raise_invalid_array(path, test_index)
    for gate_index, item in enumerate(raw_gate_results):
        _require_gate_result(item, path=path, test_index=test_index, gate_index=gate_index)


def _require_gate_result(
    item: object,
    *,
    path: Path,
    test_index: int,
    gate_index: int,
) -> None:
    if not isinstance(item, Mapping):
        _raise_non_object(path, test_index, gate_index)
    if not _is_valid_gate_result(item):
        _raise_invalid_gate_result(path, test_index, gate_index)


def _is_valid_gate_result(item: Mapping[object, object]) -> bool:
    return (
        _is_valid_rule_id(item.get("rule_id"))
        and _is_enforcement(item.get("enforcement"))
        and _is_gate_result(item.get("result"))
        and _is_json_int(item.get("exit_code"))
    )


def _is_valid_rule_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not _has_control_character(value)
    )


def _raise_invalid_array(path: Path, test_index: int) -> NoReturn:
    msg = f"Run report {path} field tests[{test_index}].gate_results must be a JSON array"
    raise ValueError(msg)


def _raise_invalid_gate_result(path: Path, test_index: int, gate_index: int) -> NoReturn:
    msg = (
        f"Run report {path} field tests[{test_index}].gate_results[{gate_index}] is invalid"
    )
    raise ValueError(msg)


def _raise_non_object(path: Path, test_index: int, gate_index: int) -> NoReturn:
    msg = (
        f"Run report {path} field tests[{test_index}].gate_results[{gate_index}] "
        "must be a JSON object"
    )
    raise ValueError(msg)


def _serialized_gate_results(raw_gate_results: object) -> tuple[GateResultEvidence, ...]:
    if not isinstance(raw_gate_results, list):
        return ()
    return tuple(
        _to_gate_result(item)
        for item in raw_gate_results
        if isinstance(item, Mapping) and _is_valid_gate_result(item)
    )


def _gate_results_to_dict(
    gate_results: Sequence[GateResultEvidence],
) -> list[dict[str, object]]:
    return [
        {
            "rule_id": gate.rule_id,
            "enforcement": gate.enforcement,
            "result": gate.result,
            "exit_code": gate.exit_code,
        }
        for gate in gate_results
    ]


def _gate_results_payload(
    gate_results: Sequence[GateResultEvidence],
) -> dict[str, object]:
    if not gate_results:
        return {}
    return {"gate_results": _gate_results_to_dict(gate_results)}


def _to_gate_result(item: Mapping[object, object]) -> GateResultEvidence:
    if not _is_valid_gate_result(item):
        raise ValueError("invalid serialized gate result")
    return GateResultEvidence(
        rule_id=cast(str, item["rule_id"]).strip(),
        enforcement=cast(Enforcement, item["enforcement"]),
        result=cast(GateResult, item["result"]),
        exit_code=cast(int, item["exit_code"]),
    )


def _is_enforcement(value: object) -> TypeGuard[Enforcement]:
    return value in {"block", "warn", "audit_only"}


def _is_gate_result(value: object) -> TypeGuard[GateResult]:
    return value in {"passed", "failed", "timeout", "error", "blocked"}


def _is_json_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
