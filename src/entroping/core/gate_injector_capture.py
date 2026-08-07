"""Private response-body capture naming for temporary Hurl copies."""

import re
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

from entroping.bridge.policy_to_hurl import HurlGateAssertion


def reserved_response_capture_name(
    *,
    source_path: Path,
    response_index: int,
    source_content: str,
    reserved_names: Sequence[str],
) -> str:
    """Return a source-free, collision-safe capture identifier."""

    digest = sha256(f"{source_path.resolve()}#{response_index}".encode()).hexdigest()
    base_name = f"__entroping_response_body_{digest[:16]}_{response_index}"
    return _unique_capture_name(base_name, source_content, reserved_names)


def build_response_capture_plan(
    sections: Sequence[tuple[int, bool]],
    *,
    source_path: Path,
    source_content: str,
) -> tuple[tuple[str, ...], dict[int, tuple[str, bool]]]:
    """Return capture names and insertion points for response sections."""

    names: list[str] = []
    insertions: dict[int, tuple[str, bool]] = {}
    for response_index, (position, has_captures) in enumerate(sections):
        name = reserved_response_capture_name(
            source_path=source_path,
            response_index=response_index,
            source_content=source_content,
            reserved_names=names,
        )
        names.append(name)
        insertions[position] = (name, not has_captures)
    return tuple(names), insertions


def build_gate_capture_plan(
    sections: Sequence[tuple[int, bool, int, bool]],
    gates_by_section: Sequence[Sequence[HurlGateAssertion]],
    injected_gates: Sequence[HurlGateAssertion],
    *,
    source_path: Path,
    source_content: str,
) -> tuple[
    dict[int, tuple[HurlGateAssertion, ...]],
    dict[int, bool],
    tuple[str, ...],
    dict[int, tuple[str, bool]],
]:
    """Build assertion and response-capture insertions for one source copy."""

    has_asserts = {section[0]: section[1] for section in sections}
    if not injected_gates:
        return {}, has_asserts, (), {}
    gate_insertions = _gate_insertions(sections, gates_by_section)
    capture_source = "\n".join((source_content, *(gate.assertion for gate in injected_gates)))
    capture_names, capture_insertions = build_response_capture_plan(
        tuple((section[2], section[3]) for section in sections),
        source_path=source_path,
        source_content=capture_source,
    )
    return gate_insertions, has_asserts, capture_names, capture_insertions


def _gate_insertions(
    sections: Sequence[tuple[int, bool, int, bool]],
    gates_by_section: Sequence[Sequence[HurlGateAssertion]],
) -> dict[int, tuple[HurlGateAssertion, ...]]:
    return {
        section[0]: tuple(gates)
        for section, gates in zip(sections, gates_by_section, strict=True)
        if gates
    }


def _unique_capture_name(
    base_name: str,
    source_content: str,
    reserved_names: Sequence[str],
) -> str:
    used_names = {*reserved_names}
    candidate = base_name
    suffix = 0
    while candidate in used_names or _capture_name_in_source(candidate, source_content):
        suffix += 1
        candidate = f"{base_name}_{suffix}"
    return candidate


def _capture_name_in_source(candidate: str, source_content: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(candidate)}(?![A-Za-z0-9_])"
    return re.search(pattern, source_content) is not None
