"""Bounded Hurl exchange and request-body location for mutation materialization.
The linear lexer is quote-aware across text, tags, declarations, comments, CDATA,
and PIs; DOCTYPE subsets defer `>` until balanced. Depth tracks one root, malformed
input fails closed, and status lines are accepted only at body boundaries; adjacent
entries remain distinct. It retains no XML body text or parsed tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from entroping.core import mutation_materializer_io as _io

MutationMaterializerError = _io.MutationMaterializerError
_STATUS_RE: Final = re.compile(r"^(HTTP\s+)(\d{3})(?=\s|$)")
_REQUEST_RE: Final = re.compile(
    r"^(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|CONNECT|TRACE)\s+\S+(?:\s+.*)?$"
)
_JSON_STRING_RE: Final = re.compile(r'"(?:\\.|[^"\\])*"')
_XML_TEXT, _XML_TAG, _XML_COMMENT = "text", "tag", "comment"
_XML_CDATA, _XML_PI, _XML_DECLARATION = "cdata", "pi", "declaration"
_XML_MARKERS: Final = {_XML_COMMENT: "-->", _XML_CDATA: "]]>", _XML_PI: "?>"}
_XML_CONSTRUCTS: Final = (
    ("<!--", _XML_COMMENT, 4, False),
    ("<![CDATA[", _XML_CDATA, 9, False),
    ("<?", _XML_PI, 2, False),
    ("<!DOCTYPE", _XML_DECLARATION, 9, False),
    ("<!", _XML_DECLARATION, 2, False),
    ("</", _XML_TAG, 2, True),
)


@dataclass(slots=True)
class _XmlLexState:
    mode: str = _XML_TEXT  # Text, tag, declaration, or terminated-marker mode.
    resume_mode: str = _XML_TEXT  # Marker completion returns to this mode.
    quote: str = ""  # Quoted delimiters are inert in tags and declarations.
    marker_window: str = ""  # Bounded partial comment/CDATA/PI terminator.
    subset_depth: int = 0  # Internal-subset brackets defer declaration closing.
    depth: int = 0  # Open-element count; the root closes only at zero.
    started: bool = False  # Request body committed to XML lexical scanning.
    root_seen: bool = False  # At least one opening or self-closing element exists.
    root_closed: bool = False  # Complete root permits only trailing whitespace.
    malformed: bool = False  # Stray text or underflow fails closed.
    tag_closing: bool = False  # Current tag is an element close.
    tag_self_closing: bool = False  # Slash survives trailing tag whitespace.
    tag_name_seen: bool = False  # Empty tags are rejected at the terminator.

    @property
    def complete(self) -> bool:
        return self.root_closed and self.mode == _XML_TEXT


def _advance_marker(state: _XmlLexState, char: str, marker: str) -> None:
    state.marker_window = (state.marker_window + char)[-len(marker) :]
    if state.marker_window.endswith(marker):
        state.mode = state.resume_mode
        state.resume_mode = _XML_TEXT
        state.marker_window = ""


def _advance_xml_declaration_boundary(state: _XmlLexState, char: str) -> None:
    if char == "[":  # DOCTYPE internal subsets can contain their own `>` characters.
        state.subset_depth += 1
        return
    if char == "]":
        state.malformed = state.subset_depth == 0
        state.subset_depth = max(0, state.subset_depth - 1)
        return
    if char == ">" and state.subset_depth == 0:
        state.mode = _XML_TEXT


def _advance_xml_declaration_char(state: _XmlLexState, char: str) -> None:
    if state.quote:
        if char == state.quote:
            state.quote = ""
        return
    if char in {'"', "'"}:
        state.quote = char
        return
    _advance_xml_declaration_boundary(state, char)


def _finish_xml_closing_tag(state: _XmlLexState) -> None:
    if state.depth == 0:
        state.malformed = True
    else:
        state.depth -= 1
        state.root_closed = state.depth == 0


def _finish_xml_opening_tag(state: _XmlLexState) -> None:
    if state.root_closed:
        state.malformed = True
    else:
        state.root_seen = True
        if not state.tag_self_closing:
            state.depth += 1
        elif state.depth == 0:
            state.root_closed = True


def _finish_xml_tag(state: _XmlLexState) -> None:
    if not state.tag_name_seen:
        state.malformed = True
    elif state.tag_closing:
        _finish_xml_closing_tag(state)
    else:
        _finish_xml_opening_tag(state)
    state.mode = _XML_TEXT
    state.tag_closing = False
    state.tag_self_closing = False
    state.tag_name_seen = False


def _advance_xml_tag_boundary(state: _XmlLexState, char: str) -> None:
    if char == ">":
        _finish_xml_tag(state)
        return
    state.tag_name_seen |= not state.tag_name_seen and not char.isspace() and char != "/"
    if char == "/":
        state.tag_self_closing = True
        return
    state.tag_self_closing &= char.isspace()


def _advance_xml_tag_char(line: str, index: int, state: _XmlLexState) -> int:
    char = line[index]
    if state.quote:
        if char == state.quote:
            state.quote = ""
        return index + 1
    if char in {'"', "'"}:
        state.quote = char
    else:
        _advance_xml_tag_boundary(state, char)
    return index + 1


def _start_xml_construct(line: str, index: int, state: _XmlLexState) -> int:
    for prefix, mode, width, closing in _XML_CONSTRUCTS:
        if line.startswith(prefix, index):
            state.mode = mode
            state.resume_mode = _XML_TEXT
            if mode == _XML_DECLARATION:
                state.subset_depth = 0
            if mode == _XML_TAG:
                state.tag_closing = closing
                state.tag_self_closing = False
                state.tag_name_seen = False
            return index + width
    state.mode, state.resume_mode = _XML_TAG, _XML_TEXT
    state.tag_closing = state.tag_self_closing = state.tag_name_seen = False
    return index + 1


def _advance_xml_text(line: str, index: int, state: _XmlLexState) -> int:
    char = line[index]
    outside_root = state.depth == 0 and (not state.root_seen or state.root_closed)
    if char != "<":
        state.malformed |= outside_root and not char.isspace()
        return index + 1
    return _start_xml_construct(line, index, state)


def _advance_xml_declaration_line(line: str, index: int, state: _XmlLexState) -> int:
    if not state.quote and line.startswith("<!--", index):
        state.mode = _XML_COMMENT
        state.resume_mode = _XML_DECLARATION
        return index + 4
    if not state.quote and line.startswith("<?", index):
        state.mode = _XML_PI
        state.resume_mode = _XML_DECLARATION
        return index + 2
    _advance_xml_declaration_char(state, line[index])
    return index + 1


_XML_MODE_HANDLERS: Final = {
    _XML_DECLARATION: _advance_xml_declaration_line,
    _XML_TAG: _advance_xml_tag_char,
}


def _advance_xml_line(line: str, state: _XmlLexState) -> bool:
    """Lex one line of XML without building a tree or retaining body text."""

    index = 0
    while index < len(line):
        if state.mode in _XML_MARKERS:
            _advance_marker(state, line[index], _XML_MARKERS[state.mode])
            index += 1
        else:
            handler = _XML_MODE_HANDLERS.get(state.mode, _advance_xml_text)
            index = handler(line, index, state)
        if state.malformed:  # Never infer boundaries from malformed lexical state.
            return False
    return not state.malformed


def _xml_status_boundary(line: str, state: _XmlLexState) -> bool:
    return state.mode == _XML_TEXT and state.depth == 0 and _STATUS_RE.match(line) is not None


def _reject(condition: bool, error: str) -> None:
    if condition:
        raise MutationMaterializerError(error)


@dataclass(slots=True)
class _ExchangeScanState:
    request_lines: list[int] = field(default_factory=list)
    status_by_request: dict[int, int] = field(default_factory=dict)
    phase: str = "seek"
    current_request: int = 0
    request_fenced: bool = False
    request_xml: _XmlLexState = field(default_factory=_XmlLexState)
    request_xml_ambiguous: bool = False
    response_mode: str = "none"
    response_depth: int = 0
    response_xml: _XmlLexState = field(default_factory=_XmlLexState)


def _scan_hurl_exchanges(lines: list[str]) -> tuple[list[int], dict[int, int]]:
    scan = _ExchangeScanState()
    for line_number, line in enumerate(lines):
        stripped = line.strip()
        if scan.phase == "seek":
            _scan_seek(scan, line_number, stripped)
        elif scan.phase == "request":
            _scan_request(scan, line_number, stripped)
        else:
            _scan_response(scan, line_number, stripped)
    return scan.request_lines, scan.status_by_request


def _scan_seek(scan: _ExchangeScanState, line_number: int, line: str) -> None:
    if _REQUEST_RE.fullmatch(line) is not None:
        _begin_request(scan, line_number)


def _begin_request(scan: _ExchangeScanState, line_number: int) -> None:
    scan.request_lines.append(line_number)
    scan.current_request = line_number
    scan.phase = "request"
    scan.request_fenced = False
    scan.request_xml = _XmlLexState()
    scan.request_xml_ambiguous = False


def _scan_request(scan: _ExchangeScanState, line_number: int, line: str) -> None:
    consumed, scan.request_fenced, scan.request_xml_ambiguous = _request_body_step(
        line,
        scan.request_fenced,
        scan.request_xml,
        scan.request_xml_ambiguous,
    )
    if consumed:
        return
    if _STATUS_RE.match(line) is not None:
        scan.status_by_request[scan.current_request] = line_number
        scan.phase = "response"
        scan.response_mode = "none"
        scan.response_depth = 0
        scan.response_xml = _XmlLexState()


def _scan_response(scan: _ExchangeScanState, line_number: int, line: str) -> None:
    if scan.response_mode == "none":
        if _REQUEST_RE.fullmatch(line) is not None:
            _begin_request(scan, line_number)
        else:
            scan.response_mode, scan.response_depth = _response_start(scan, line)
        return
    if scan.response_mode == "boundary":
        _scan_response_boundary(scan, line_number, line)
        return
    if scan.response_mode == "xml":
        _scan_response_xml(scan, line)
        return
    scan.response_mode, scan.response_depth = _response_body_step(
        line, scan.response_mode, scan.response_depth
    )


def _scan_response_xml(scan: _ExchangeScanState, line: str) -> None:
    if not _advance_xml_line(line, scan.response_xml):
        scan.response_mode = "raw"
    elif scan.response_xml.complete:
        scan.response_mode = "boundary"


def _scan_response_boundary(scan: _ExchangeScanState, line_number: int, line: str) -> None:
    if not line:
        return
    if _REQUEST_RE.fullmatch(line) is not None:
        _begin_request(scan, line_number)
        scan.response_mode = "none"
    else:
        scan.response_mode = "raw"
        scan.response_depth = 0


def _request_body_step(
    line: str,
    fenced: bool,
    xml: _XmlLexState,
    ambiguous: bool,
) -> tuple[bool, bool, bool]:
    if fenced:
        return True, line != "```", ambiguous
    if any((ambiguous, xml.started)):
        return _request_body_started(line, xml, ambiguous)
    if line.startswith("```"):
        return True, True, False
    if not line.startswith("<"):
        return False, False, False
    xml.started = True
    return True, False, not _advance_xml_line(line, xml)


def _request_body_started(line: str, xml: _XmlLexState, ambiguous: bool) -> tuple[bool, bool, bool]:
    if ambiguous:  # Preserve the exact consumed/ambiguous tuple before XML boundaries.
        return True, False, True
    if _xml_status_boundary(line, xml) or (xml.complete and not line.startswith("<")):
        return False, False, False
    return True, False, not _advance_xml_line(line, xml)


def _response_start(scan: _ExchangeScanState, line: str) -> tuple[str, int]:
    if line in {"", "[Asserts]", "[Captures]"}:
        return "none", 0
    if line.startswith("```"):
        return "fenced", 0
    if line.startswith("<"):
        return _response_xml_start(scan, line)
    if line.startswith(("{", "[")):
        return _response_depth_result("json", _json_bracket_delta(line))
    return "raw", 0


def _response_xml_start(scan: _ExchangeScanState, line: str) -> tuple[str, int]:
    scan.response_xml = _XmlLexState(started=True)
    if not _advance_xml_line(line, scan.response_xml):
        return "raw", 0
    return ("boundary", 0) if scan.response_xml.complete else ("xml", 0)


def _response_body_step(line: str, mode: str, depth: int) -> tuple[str, int]:
    if mode == "fenced":
        return _response_fence_step(line, mode, depth)
    if mode == "raw":
        return _response_raw_step(line, mode, depth)
    depth += _json_bracket_delta(line)
    return _response_depth_result(mode, depth)


def _response_fence_step(line: str, mode: str, depth: int) -> tuple[str, int]:
    return ("boundary", 0) if line == "```" else (mode, depth)


def _response_raw_step(line: str, mode: str, depth: int) -> tuple[str, int]:
    return ("boundary", 0) if not line else (mode, depth)


def _response_depth_result(mode: str, depth: int) -> tuple[str, int]:
    return ("boundary", 0) if depth <= 0 else (mode, depth)


def response_statuses(lines: list[str]) -> dict[int, re.Match[str]]:
    _, status_by_request = _scan_hurl_exchanges(lines)
    statuses: dict[int, re.Match[str]] = {}
    for line_number in status_by_request.values():
        match = _STATUS_RE.match(lines[line_number].rstrip("\r\n"))
        if match is not None:
            statuses[line_number] = match
    return statuses


def _json_bracket_delta(value: str) -> int:
    # Braces inside JSON strings cannot close a response body.
    unquoted = _JSON_STRING_RE.sub("", value)
    return unquoted.count("{") + unquoted.count("[") - unquoted.count("}") - unquoted.count("]")


def locate_request_json_body(content: str, request_ordinal: int) -> tuple[int, int]:
    lines = content.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    request_lines, status_by_request = _scan_hurl_exchanges(lines)
    _reject(request_ordinal >= len(request_lines), "request ordinal is out of range")
    request_line = request_lines[request_ordinal]
    next_request = (
        request_lines[request_ordinal + 1]
        if request_ordinal + 1 < len(request_lines)
        else len(lines)
    )
    exchange_end = (
        offsets[status_by_request[request_line]]
        if request_line in status_by_request
        else len(content)
    )
    exchange_end = min(
        exchange_end, offsets[next_request] if next_request < len(lines) else len(content)
    )
    segment_start = offsets[request_line] + len(lines[request_line])
    relative_start, relative_end = _locate_json_in_exchange(content[segment_start:exchange_end])
    return segment_start + relative_start, segment_start + relative_end


def _locate_json_in_exchange(segment: str) -> tuple[int, int]:
    lines = segment.splitlines(keepends=True)
    offsets = _line_offsets(lines)
    blank_line = _first_blank_line(lines)
    candidate_start_line = 0 if blank_line is None else blank_line + 1
    fenced = _locate_fenced_json(lines, offsets, candidate_start_line)
    if fenced is not None:
        return fenced
    body_line = _find_body_line(lines, candidate_start_line)
    if body_line is None:
        raise MutationMaterializerError("request JSON body is missing")
    return offsets[body_line], len(segment)


def _find_body_line(lines: list[str], start: int) -> int | None:
    for line_number in range(start, len(lines)):
        value = lines[line_number].strip()
        if re.fullmatch(r"\[[A-Z][A-Za-z0-9_-]*\]", value):
            start = 0
        elif _looks_like_json_value(value, start > 0):
            return line_number
    return None


def _first_blank_line(lines: list[str]) -> int | None:
    for line_number, line in enumerate(lines):
        value = line.strip()
        if not value or _looks_like_json_value(value):
            return line_number if not value else None
    return None


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    return offsets


def _locate_fenced_json(
    lines: list[str], offsets: list[int], candidate_start_line: int
) -> tuple[int, int] | None:
    opening, closing = _find_fence_bounds(lines, candidate_start_line)
    if opening is None:
        return None
    if closing is None:
        raise MutationMaterializerError("request JSON body fence is incomplete")
    return offsets[opening] + len(lines[opening]), offsets[closing]


def _find_fence_bounds(lines: list[str], start: int) -> tuple[int | None, int | None]:
    opening = _find_fence_opening(lines, start)
    if opening is None:
        return None, None
    return opening, _find_fence_closing(lines, opening)


def _find_fence_opening(lines: list[str], start: int) -> int | None:
    opening: int | None = None
    for line_number in range(start, len(lines)):
        if lines[line_number].strip().lower().startswith("```json"):
            if opening is not None:
                raise MutationMaterializerError("request contains multiple JSON bodies")
            opening = line_number
    return opening


def _find_fence_closing(lines: list[str], opening: int) -> int | None:
    for line_number in range(opening + 1, len(lines)):
        if lines[line_number].strip() == "```":
            return line_number
    return None


def _looks_like_json_value(value: str, allow_any: bool = False) -> bool:
    if not value:
        return False
    if allow_any:
        return True
    return (
        value.lower().startswith("```json")
        or value[0] in '{["-0123456789'
        or value.startswith(("true", "false", "null"))
    )
