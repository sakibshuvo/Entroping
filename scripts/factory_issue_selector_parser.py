from __future__ import annotations

import re
from collections.abc import Mapping

from scripts.factory_control_plane_policy import normalize_repo_path
from scripts.factory_issue_selector_evidence import (
    parse_user_evidence,
    yaml_has_unique_keys,
)
from scripts.factory_issue_selector_models import JsonValue, ParsedIssue
from scripts.factory_issue_selector_yaml import (
    closed_mapping,
    compose_yaml,
    sequence_items,
    string_value,
)

_REQUIRED_HEADINGS = frozenset(
    {"outcome", "scope", "non-goals", "acceptance criteria", "verification", "autonomy"}
)
_VERIFICATION_LANES = (
    "tiny-docs",
    "docs-guardrail",
    "tests-only",
    "normal-code",
    "security-runtime",
    "release-ci-architecture",
)
_HEADING_RE = re.compile(r"^ {0,3}#{2,6}[ \t]+(?P<title>.+?)[ \t]*$")
_FENCE_RE = re.compile(r"^ {0,3}(?P<token>`{3,}|~{3,})")
_BULLET_RE = re.compile(r"^\s*[-+*]\s+(?P<value>.+?)\s*$")
_DEPENDENCY_RE = re.compile(r"#(\d+)")
_LANE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?verification\s+lane\s*:\s*`?([a-z0-9-]+)`?[.\s]*$"
)
_YAML_RE = re.compile(
    r"(?:^|\n)\s*```ya?ml\s*\n(?P<body>.*?)\n\s*```\s*(?=\n|$)",
    flags=re.IGNORECASE | re.DOTALL,
)
_UNSAFE_SCOPE_META = frozenset("?[]{}!")
_SCOPE_KEY_RE = re.compile(r"(?im)^\s*(?:allowed files|allowed_files)\s*:")
INVALID_DEPENDENCIES_SECTION = "dependencies-invalid"


class IssueParseError(ValueError):
    pass


def parse_issue(payload: Mapping[str, JsonValue]) -> ParsedIssue:
    number = _positive_int(payload.get("number"), "issue number")
    title = _string(payload.get("title"), "issue title")
    state = _string(payload.get("state"), "issue state").upper()
    url = _string(payload.get("html_url"), "issue URL")
    body_value = payload.get("body")
    body = "" if body_value is None else _string(body_value, "issue body")
    labels = _labels(payload.get("labels"))
    sections = _sections(body)
    allowed_scopes = _allowed_scopes(sections, body)
    evidence = parse_user_evidence(
        tuple(sections.get("user evidence", ())),
        verification_label="evidence:user-verified" in labels,
    )
    return ParsedIssue(
        number=number,
        title=title,
        url=url,
        state=state,
        milestone_present=isinstance(payload.get("milestone"), Mapping),
        labels=labels,
        assignee_count=_assignee_count(payload.get("assignees")),
        sections=frozenset(
            {
                heading
                for heading in _REQUIRED_HEADINGS
                if len(sections.get(heading, ())) == 1
                and sections[heading][0].strip()
            }
            | (
                {INVALID_DEPENDENCIES_SECTION}
                if len(sections.get("dependencies", ())) > 1
                else set()
            )
        ),
        verification_lanes=_verification_lanes(sections),
        autonomy_labels=tuple(label for label in labels if label.startswith("autonomy:")),
        priority_labels=tuple(label for label in labels if label.startswith("priority:")),
        status_labels=tuple(label for label in labels if label.startswith("status:")),
        type_labels=tuple(label for label in labels if label.startswith("type:")),
        dependency_numbers=_dependencies(sections),
        allowed_scopes=allowed_scopes,
        evidence=evidence,
    )


def normalize_scope(raw_scope: str) -> str | None:
    candidate = raw_scope.strip().strip("`")
    if not candidate or any(character in candidate for character in _UNSAFE_SCOPE_META):
        return None
    stars = candidate.count("*")
    if stars:
        recursive = stars == 2 and candidate.endswith("/**")
        file_family = stars == 1 and "*" in candidate.rsplit("/", maxsplit=1)[-1]
        if not recursive and not file_family:
            return None
    return normalize_repo_path(candidate)


def scopes_overlap(left: str, right: str) -> bool:
    normalized_left = normalize_scope(left)
    normalized_right = normalize_scope(right)
    if normalized_left is None or normalized_right is None:
        return True
    normalized_left = normalized_left.casefold()
    normalized_right = normalized_right.casefold()
    left_prefix = normalized_left.split("*", maxsplit=1)[0].rstrip("/")
    right_prefix = normalized_right.split("*", maxsplit=1)[0].rstrip("/")
    if "*" in normalized_left or "*" in normalized_right:
        return left_prefix.startswith(right_prefix) or right_prefix.startswith(
            left_prefix
        )
    return (
        normalized_left == normalized_right
        or normalized_left.startswith(f"{right_prefix}/")
        or normalized_right.startswith(f"{left_prefix}/")
    )


def _sections(body: str) -> dict[str, tuple[str, ...]]:
    collected: dict[str, list[str]] = {}
    current: str | None = None
    buffer: list[str] = []
    fence: str | None = None
    for line in body.splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence_match is not None:
            fence_marker = fence_match.group("token")
            fence = (
                fence_marker
                if fence is None
                else (None if fence_marker.startswith(fence) else fence)
            )
        heading_match = None if fence is not None else _HEADING_RE.match(line)
        if heading_match is not None:
            if current is not None:
                collected.setdefault(current, []).append("\n".join(buffer).strip())
            current = _heading_name(heading_match.group("title"))
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        collected.setdefault(current, []).append("\n".join(buffer).strip())
    return {key: tuple(values) for key, values in collected.items()}


def _heading_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).replace("non goals", "non-goals")


def _allowed_scopes(
    sections: Mapping[str, tuple[str, ...]], body: str
) -> tuple[str, ...]:
    raw_scopes: list[str] = []
    values = sections.get("allowed files", ())
    if len(values) == 1:
        raw_scopes.extend(
            match.group("value")
            for line in values[0].splitlines()
            if (match := _BULLET_RE.match(line)) is not None
        )
    for match in _YAML_RE.finditer(body):
        packet_scopes = _packet_scopes(match.group("body"))
        if packet_scopes is None:
            return ()
        raw_scopes.extend(packet_scopes)
    normalized = tuple(normalize_scope(value) for value in raw_scopes)
    if not normalized or any(value is None for value in normalized):
        return ()
    return tuple(sorted(set(value for value in normalized if value is not None)))


def _packet_scopes(text: str) -> tuple[str, ...] | None:
    if _SCOPE_KEY_RE.search(text) is None:
        return ()
    if not yaml_has_unique_keys(text):
        return None
    try:
        packet = closed_mapping(compose_yaml(text))
    except (RecursionError, ValueError):
        return None
    if packet is None:
        return None
    if "allowed files" in packet and "allowed_files" in packet:
        return None
    value_node = packet.get("allowed files", packet.get("allowed_files"))
    if value_node is None:
        return None
    if (value := string_value(value_node)) is not None:
        return (value,)
    items = sequence_items(value_node)
    if items is not None:
        values = tuple(string_value(item) for item in items)
        if all(item is not None for item in values):
            return tuple(item for item in values if item is not None)
    return None


def _verification_lanes(sections: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    values = sections.get("verification", ())
    if len(values) != 1:
        return ()
    return tuple(_LANE_RE.findall(values[0]))


def _dependencies(sections: Mapping[str, tuple[str, ...]]) -> tuple[int, ...]:
    values = sections.get("dependencies", ())
    if len(values) != 1:
        return ()
    return tuple(
        sorted({int(match.group(1)) for match in _DEPENDENCY_RE.finditer(values[0])})
    )


def _labels(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise IssueParseError("issue labels must be a list")
    labels: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            raise IssueParseError("issue label must be an object")
        labels.append(_string(item.get("name"), "issue label"))
    return tuple(sorted(labels))


def _assignee_count(value: JsonValue) -> int:
    if not isinstance(value, list):
        raise IssueParseError("issue assignees must be a list of objects")
    if any(not isinstance(item, dict) for item in value):
        raise IssueParseError("issue assignees must be a list of objects")
    return len(value)


def _positive_int(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise IssueParseError(f"{label} must be a positive integer")
    return value


def _string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IssueParseError(f"{label} must be a non-empty string")
    return value.strip()
