"""Temporary Hurl execution-copy creation with QAnstitution gate injection."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from entroping.bridge.policy_to_hurl import HurlGateAssertion, compile_matching_gates
from entroping.models.hurl import HurlExchange, HurlTest, parse_hurl_exchanges
from entroping.models.qanstitution import GateRule

_REQUEST_LINE_RE = re.compile(
    r"^(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|CONNECT|TRACE)\s+\S+(?:\s+.*)?$",
)
_HTTP_LINE_RE = re.compile(r"^HTTP\s+\S+")


class GateInjectionError(ValueError):
    """Raised when temporary Hurl gate injection cannot proceed safely."""


@dataclass(frozen=True)
class HurlExecutionCopy:
    """Temporary Hurl file prepared for execution."""

    source_path: Path
    execution_path: Path
    injected_gates: tuple[HurlGateAssertion, ...]


@dataclass(frozen=True)
class _ResponseBlock:
    exchange: HurlExchange
    insert_at: int
    has_asserts: bool


def write_injected_execution_copy(
    hurl_test: HurlTest,
    gates: Sequence[GateRule],
    *,
    execution_root: Path,
) -> HurlExecutionCopy:
    """Write a temporary execution copy for one Hurl test without mutating source."""

    source_path = _validate_source_path(hurl_test.path)
    try:
        content = source_path.read_text(encoding="utf-8")
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
    injected_content, injected_gates = inject_gate_assertions(content, parsed_test, gates)

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
    )


def inject_gate_assertions(
    content: str,
    hurl_test: HurlTest,
    gates: Sequence[GateRule],
) -> tuple[str, tuple[HurlGateAssertion, ...]]:
    """Return Hurl content with matching gate assertions injected."""

    lines = content.splitlines()
    response_blocks = _find_response_blocks(lines, hurl_test.exchanges)
    if not response_blocks and gates:
        msg = f"No Hurl response sections found in {hurl_test.path}"
        raise GateInjectionError(msg)

    output: list[str] = []
    cursor = 0
    injected_by_id: dict[str, HurlGateAssertion] = {}

    for block in response_blocks:
        matching_gates = compile_matching_gates(gates, hurl_test, exchange=block.exchange)
        if not matching_gates:
            continue

        if block.has_asserts:
            output.extend(lines[cursor : block.insert_at])
            output.extend(_render_gate_lines(matching_gates))
            cursor = block.insert_at
        else:
            output.extend(lines[cursor : block.insert_at])
            output.append("[Asserts]")
            output.extend(_render_gate_lines(matching_gates))
            cursor = block.insert_at

        for gate in matching_gates:
            injected_by_id.setdefault(gate.rule_id, gate)

    output.extend(lines[cursor:])
    rendered = "\n".join(output)
    if content.endswith("\n"):
        rendered += "\n"
    return rendered, tuple(injected_by_id.values())


def _validate_source_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        msg = f"Refusing to inject gates into symlinked Hurl file: {expanded}"
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
    if path.is_symlink():
        msg = f"Refusing to write Hurl execution copy through symlinked execution path: {path}"
        raise GateInjectionError(msg)


def _execution_file_name(source_path: Path) -> str:
    digest = sha256(str(source_path).encode("utf-8")).hexdigest()[:12]
    return f"{source_path.stem}-{digest}.hurl"


def _find_response_blocks(
    lines: Sequence[str],
    exchanges: Sequence[HurlExchange],
) -> tuple[_ResponseBlock, ...]:
    blocks: list[_ResponseBlock] = []
    current_exchange_index = -1
    request_starts: list[int] = []
    pending_response_starts: list[tuple[int, HurlExchange]] = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        if _REQUEST_LINE_RE.fullmatch(stripped):
            current_exchange_index += 1
            request_starts.append(index)
            continue

        if _HTTP_LINE_RE.fullmatch(stripped) and 0 <= current_exchange_index < len(exchanges):
            pending_response_starts.append((index, exchanges[current_exchange_index]))

    for start, exchange in pending_response_starts:
        end = _next_request_start_after(request_starts, start) or len(lines)
        insert_at, has_asserts = _find_insert_position(lines, start=start, end=end)
        blocks.append(
            _ResponseBlock(
                exchange=exchange,
                insert_at=insert_at,
                has_asserts=has_asserts,
            ),
        )

    return tuple(blocks)


def _next_request_start_after(request_starts: Sequence[int], index: int) -> int | None:
    for request_start in request_starts:
        if request_start > index:
            return request_start
    return None


def _find_insert_position(lines: Sequence[str], *, start: int, end: int) -> tuple[int, bool]:
    for index in range(start + 1, end):
        if lines[index].strip() != "[Asserts]":
            continue

        section_end = index + 1
        while section_end < end and not _is_new_section(lines[section_end]):
            section_end += 1
        return _without_trailing_blank_lines(lines, start=index + 1, end=section_end), True

    return _without_trailing_blank_lines(lines, start=start + 1, end=end), False


def _is_new_section(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]") and stripped != "[Asserts]"


def _without_trailing_blank_lines(lines: Sequence[str], *, start: int, end: int) -> int:
    insert_at = end
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    return insert_at


def _render_gate_lines(gates: Sequence[HurlGateAssertion]) -> list[str]:
    rendered: list[str] = []
    for gate in gates:
        rendered.append(f"# entroping-gate: {gate.rule_id} enforcement={gate.enforcement}")
        rendered.append(gate.assertion)
    return rendered
