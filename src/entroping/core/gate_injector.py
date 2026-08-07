"""Temporary Hurl execution-copy creation with QAnstitution gate injection."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from entroping.bridge.policy_to_hurl import HurlGateAssertion, compile_matching_gates
from entroping.core.gate_injector_capture import build_gate_capture_plan
from entroping.core.known_failures import normalize_known_failure_test
from entroping.core.path_safety import first_symlink_path_component
from entroping.hurl_source import HurlSourceTooLargeError, read_hurl_source_text
from entroping.models.hurl import HurlExchange, HurlTest, parse_hurl_exchanges
from entroping.models.qanstitution import (
    GateRule,
    KnownFailure,
    KnownFailureValidationError,
    validate_known_failure_expiries,
)

_REQUEST_LINE_RE = re.compile(
    r"^(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|CONNECT|TRACE)\s+\S+(?:\s+.*)?$",
)
_HTTP_LINE_RE = re.compile(r"^HTTP\s+\S+")


class GateInjectionError(ValueError):
    """Raised when temporary Hurl gate injection cannot proceed safely."""


@dataclass(frozen=True)
class AppliedKnownFailure:
    """Known-failure exception applied to one injected governance gate."""

    test: str
    rule_id: str
    issue_id: str
    expires: str
    reason: str


@dataclass(frozen=True)
class HurlExecutionCopy:
    """Temporary Hurl file prepared for execution."""

    source_path: Path
    execution_path: Path
    injected_gates: tuple[HurlGateAssertion, ...]
    known_failures: tuple[AppliedKnownFailure, ...] = ()
    injected_gate_lines: tuple[tuple[int, HurlGateAssertion], ...] = ()
    response_capture_names: tuple[str, ...] = ()
    operation_id: str | None = None
    source: str | None = None
    negative_category: str | None = None
    severity: str | None = None
    auth_flow: str | None = None
    auth_requires: tuple[str, ...] = ()
    auth_produces: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ResponseBlock:
    exchange: HurlExchange
    assert_insert_at: int
    has_asserts: bool
    capture_insert_at: int
    has_captures: bool


def write_injected_execution_copy(
    hurl_test: HurlTest,
    gates: Sequence[GateRule],
    *,
    execution_root: Path,
    known_failures: Sequence[KnownFailure] = (),
    project_root: Path | None = None,
    today: date | None = None,
) -> HurlExecutionCopy:
    """Write a temporary execution copy for one Hurl test without mutating source."""

    source_path = _validate_source_path(hurl_test.path)
    try:
        validate_known_failure_expiries(known_failures, today=today)
    except KnownFailureValidationError as exc:
        raise GateInjectionError(str(exc)) from exc
    try:
        content = read_hurl_source_text(source_path)
    except HurlSourceTooLargeError as exc:
        raise GateInjectionError(str(exc)) from exc
    except UnicodeDecodeError as exc:
        msg = f"{source_path}: file is not valid UTF-8"
        raise GateInjectionError(msg) from exc
    except OSError as exc:
        msg = f"Could not read Hurl source file {source_path}: {exc}"
        raise GateInjectionError(msg) from exc

    parsed_test = HurlTest(
        path=source_path,
        metadata=hurl_test.metadata,
        exchanges=parse_hurl_exchanges(content),
    )
    (
        injected_content,
        injected_gates,
        applied_known_failures,
        injected_gate_lines,
        response_capture_names,
    ) = _inject_gate_assertions(
        content,
        parsed_test,
        gates,
        known_failures=known_failures,
        project_root=project_root,
    )

    resolved_root = execution_root.expanduser().resolve()
    if resolved_root.exists() and not resolved_root.is_dir():
        msg = f"Execution root must be a directory: {resolved_root}"
        raise GateInjectionError(msg)
    resolved_root.mkdir(parents=True, exist_ok=True)

    execution_path = resolved_root / _execution_file_name(source_path)
    _validate_execution_path(execution_path)
    execution_path.write_text(injected_content, encoding="utf-8")
    return HurlExecutionCopy(
        source_path=source_path,
        execution_path=execution_path,
        injected_gates=injected_gates,
        known_failures=applied_known_failures,
        injected_gate_lines=injected_gate_lines,
        response_capture_names=response_capture_names,
        operation_id=parsed_test.metadata.operation_id,
        source=parsed_test.metadata.meta.get("source"),
        negative_category=parsed_test.metadata.meta.get("negative_category"),
        severity=parsed_test.metadata.meta.get("severity"),
        auth_flow=parsed_test.metadata.auth_flow,
        auth_requires=parsed_test.metadata.auth_requires,
        auth_produces=parsed_test.metadata.auth_produces,
    )


def inject_gate_assertions(
    content: str,
    hurl_test: HurlTest,
    gates: Sequence[GateRule],
) -> tuple[str, tuple[HurlGateAssertion, ...]]:
    """Return Hurl content with matching gate assertions injected."""

    (
        injected_content,
        injected_gates,
        _applied_known_failures,
        _injected_gate_lines,
        _response_capture_names,
    ) = _inject_gate_assertions(
        content,
        hurl_test,
        gates,
        known_failures=(),
        project_root=None,
    )
    return injected_content, injected_gates


def _inject_gate_assertions(
    content: str,
    hurl_test: HurlTest,
    gates: Sequence[GateRule],
    *,
    known_failures: Sequence[KnownFailure],
    project_root: Path | None,
) -> tuple[
    str,
    tuple[HurlGateAssertion, ...],
    tuple[AppliedKnownFailure, ...],
    tuple[tuple[int, HurlGateAssertion], ...],
    tuple[str, ...],
]:
    """Return Hurl content with matching active known-failure gates omitted."""

    if not gates:
        return content, (), (), (), ()

    lines = content.splitlines()
    response_blocks = _find_response_blocks(lines, hurl_test.exchanges)
    if not response_blocks and gates:
        msg = f"No Hurl response sections found in {hurl_test.path}"
        raise GateInjectionError(msg)

    injected_by_id: dict[str, HurlGateAssertion] = {}
    applied_by_rule_id: dict[str, AppliedKnownFailure] = {}
    injected_gate_lines: list[tuple[int, HurlGateAssertion]] = []
    active_known_failures = _matching_known_failures_by_rule_id(
        source_path=hurl_test.path,
        project_root=project_root,
        known_failures=known_failures,
    )

    gates_by_block: list[tuple[HurlGateAssertion, ...]] = []
    for block in response_blocks:
        matching_gates = compile_matching_gates(gates, hurl_test, exchange=block.exchange)
        injectable_gates: list[HurlGateAssertion] = []
        for gate in matching_gates:
            known_failure = active_known_failures.get(gate.rule_id)
            if known_failure is None:
                injectable_gates.append(gate)
                continue
            applied_by_rule_id.setdefault(gate.rule_id, _to_applied_known_failure(known_failure))

        matching_gates = tuple(injectable_gates)
        gates_by_block.append(matching_gates)
        for gate in matching_gates:
            injected_by_id.setdefault(gate.rule_id, gate)

    (
        gate_insertions,
        has_asserts_by_position,
        response_capture_names,
        capture_insertions,
    ) = build_gate_capture_plan(
        tuple(
            (
                block.assert_insert_at,
                block.has_asserts,
                block.capture_insert_at,
                block.has_captures,
            )
            for block in response_blocks
        ),
        gates_by_block,
        tuple(injected_by_id.values()),
        source_path=hurl_test.path,
        source_content=content,
    )

    output: list[str] = []
    cursor = 0
    insertion_positions = sorted(set(gate_insertions) | set(capture_insertions))
    for position in insertion_positions:
        output.extend(lines[cursor:position])
        inserted_gates = gate_insertions.get(position)
        if inserted_gates is not None:
            if not has_asserts_by_position[position]:
                output.append("[Asserts]")
            _append_gate_lines(output, inserted_gates, injected_gate_lines)
        capture = capture_insertions.get(position)
        if capture is not None:
            capture_name, add_section = capture
            if add_section:
                output.append("[Captures]")
            output.append(f"{capture_name}: bytes")
        cursor = position
    output.extend(lines[cursor:])
    rendered = "\n".join(output)
    if content.endswith("\n"):
        rendered += "\n"
    return (
        rendered,
        tuple(injected_by_id.values()),
        tuple(applied_by_rule_id.values()),
        tuple(injected_gate_lines),
        tuple(response_capture_names),
    )


def _matching_known_failures_by_rule_id(
    *,
    source_path: Path,
    project_root: Path | None,
    known_failures: Sequence[KnownFailure],
) -> dict[str, KnownFailure]:
    test_key = _test_path_key(source_path, project_root)
    matches: dict[str, KnownFailure] = {}
    for known_failure in known_failures:
        if normalize_known_failure_test(known_failure.test) != test_key:
            continue
        matches.setdefault(known_failure.rule_id, known_failure)
    return matches


def _test_path_key(source_path: Path, project_root: Path | None) -> str:
    resolved = source_path.expanduser().resolve()
    if project_root is not None:
        root = project_root.expanduser().resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            pass
    return resolved.as_posix()


def _to_applied_known_failure(known_failure: KnownFailure) -> AppliedKnownFailure:
    return AppliedKnownFailure(
        test=normalize_known_failure_test(known_failure.test),
        rule_id=known_failure.rule_id,
        issue_id=known_failure.issue_id,
        expires=known_failure.expires,
        reason=known_failure.reason,
    )


def _validate_source_path(path: Path) -> Path:
    expanded = path.expanduser()
    symlink_component = first_symlink_path_component(expanded)
    if symlink_component is not None:
        msg = f"Refusing to inject gates into symlinked Hurl file: {symlink_component}"
        raise GateInjectionError(msg)

    resolved = expanded.resolve()
    if resolved.suffix != ".hurl":
        msg = f"Expected a .hurl file, got: {resolved}"
        raise GateInjectionError(msg)
    if not resolved.is_file():
        msg = f"Hurl source file not found: {resolved}"
        raise GateInjectionError(msg)
    return resolved


def _validate_execution_path(path: Path) -> None:
    symlink_component = first_symlink_path_component(path)
    if symlink_component is not None:
        msg = (
            "Refusing to write Hurl execution copy through symlinked execution path: "
            f"{symlink_component}"
        )
        raise GateInjectionError(msg)


def _execution_file_name(source_path: Path) -> str:
    digest = sha256(str(source_path).encode("utf-8")).hexdigest()[:12]
    return f"{source_path.stem}-{digest}.hurl"


def _find_response_blocks(
    lines: Sequence[str],
    exchanges: Sequence[HurlExchange],
) -> tuple[_ResponseBlock, ...]:
    current_exchange_index = -1
    request_starts: list[int] = []
    response_starts_by_exchange: dict[int, list[int]] = {
        exchange_index: [] for exchange_index in range(len(exchanges))
    }

    for index, line in enumerate(lines):
        stripped = line.strip()
        if _REQUEST_LINE_RE.fullmatch(stripped):
            current_exchange_index += 1
            request_starts.append(index)
            continue

        if _HTTP_LINE_RE.fullmatch(stripped) and 0 <= current_exchange_index < len(exchanges):
            response_starts_by_exchange[current_exchange_index].append(index)

    if len(request_starts) != len(exchanges):
        msg = (
            f"Parsed {len(exchanges)} Hurl exchange(s) but found "
            f"{len(request_starts)} request section marker(s); "
            "refusing gate injection because the Hurl structure is ambiguous"
        )
        raise GateInjectionError(msg)

    blocks: list[_ResponseBlock] = []
    for exchange_index, exchange in enumerate(exchanges):
        response_starts = response_starts_by_exchange[exchange_index]
        exchange_label = f"exchange {exchange_index + 1} ({exchange.method} {exchange.url})"
        if not response_starts:
            msg = f"Missing Hurl response section for {exchange_label}"
            raise GateInjectionError(msg)
        if len(response_starts) > 1:
            msg = f"Ambiguous Hurl response sections for {exchange_label}"
            raise GateInjectionError(msg)

        start = response_starts[0]
        end = _next_request_start_after(request_starts, start) or len(lines)
        assert_insert_at, has_asserts = _find_section_insert_position(
            lines,
            start=start,
            end=end,
            section="[Asserts]",
        )
        capture_insert_at, has_captures = _find_section_insert_position(
            lines,
            start=start,
            end=end,
            section="[Captures]",
        )
        blocks.append(
            _ResponseBlock(
                exchange=exchange,
                assert_insert_at=assert_insert_at,
                has_asserts=has_asserts,
                capture_insert_at=capture_insert_at,
                has_captures=has_captures,
            ),
        )

    return tuple(blocks)


def _next_request_start_after(request_starts: Sequence[int], index: int) -> int | None:
    for request_start in request_starts:
        if request_start > index:
            return request_start
    return None


def _find_section_insert_position(
    lines: Sequence[str],
    *,
    start: int,
    end: int,
    section: str,
) -> tuple[int, bool]:
    for index in range(start + 1, end):
        if lines[index].strip() != section:
            continue

        section_end = index + 1
        while section_end < end and not _is_new_section(lines[section_end]):
            section_end += 1
        return _without_trailing_blank_lines(lines, start=index + 1, end=section_end), True

    return _without_trailing_blank_lines(lines, start=start + 1, end=end), False


def _is_new_section(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def _without_trailing_blank_lines(lines: Sequence[str], *, start: int, end: int) -> int:
    insert_at = end
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    return insert_at


def _append_gate_lines(
    output: list[str],
    gates: Sequence[HurlGateAssertion],
    line_metadata: list[tuple[int, HurlGateAssertion]],
) -> None:
    """Append generated gate metadata/assertions and record assertion line numbers."""

    for gate in gates:
        output.append(f"# entroping-gate: {gate.rule_id} enforcement={gate.enforcement}")
        output.append(gate.assertion)
        line_metadata.append((len(output), gate))
