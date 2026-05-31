"""Small, validated condition DSL for QAnstitution gate matching."""

import re
from dataclasses import dataclass
from typing import Literal, cast

ContainsField = Literal["tags", "path", "url"]


class ConditionSyntaxError(ValueError):
    """Raised when a QAnstitution condition is outside the supported DSL."""


@dataclass(frozen=True)
class TrueCondition:
    """Condition that matches every test."""

    kind: Literal["true"] = "true"


@dataclass(frozen=True)
class ContainsCondition:
    """Condition requiring a field to contain a value."""

    field: ContainsField
    value: str
    kind: Literal["contains"] = "contains"


@dataclass(frozen=True)
class StartsWithCondition:
    """Condition requiring a field to start with a value."""

    field: Literal["path"]
    value: str
    kind: Literal["startswith"] = "startswith"


@dataclass(frozen=True)
class EqualsCondition:
    """Condition requiring a field to equal a value."""

    field: Literal["method"]
    value: str
    kind: Literal["equals"] = "equals"


@dataclass(frozen=True)
class MetaEqualsCondition:
    """Condition requiring Entroping metadata to equal a value."""

    key: str
    value: str
    kind: Literal["meta_equals"] = "meta_equals"


Condition = (
    TrueCondition
    | ContainsCondition
    | StartsWithCondition
    | EqualsCondition
    | MetaEqualsCondition
)

_CONTAINS_RE = re.compile(r"^(tags|path|url) contains '([^']+)'$")
_STARTS_WITH_RE = re.compile(r"^(path) startswith '([^']+)'$")
_EQUALS_RE = re.compile(r"^(method) == '([^']+)'$")
_META_EQUALS_RE = re.compile(r"^meta\.([A-Za-z_][A-Za-z0-9_]*) == '([^']+)'$")
CONDITION_JSON_SCHEMA_PATTERN = (
    r"^(true|"
    r"(tags|path|url) contains '[^']+'|"
    r"path startswith '[^']+'|"
    r"method == '[^']+'|"
    r"meta\.[A-Za-z_][A-Za-z0-9_]* == '[^']+')$"
)


def parse_condition(expression: str) -> Condition:
    """Parse the supported v4.1 condition DSL into a typed condition object."""

    normalized = expression.strip()
    if normalized == "true":
        return TrueCondition()

    contains_match = _CONTAINS_RE.fullmatch(normalized)
    if contains_match:
        field, value = contains_match.groups()
        return ContainsCondition(field=cast(ContainsField, field), value=value)

    starts_with_match = _STARTS_WITH_RE.fullmatch(normalized)
    if starts_with_match:
        _field, value = starts_with_match.groups()
        return StartsWithCondition(field="path", value=value)

    equals_match = _EQUALS_RE.fullmatch(normalized)
    if equals_match:
        _field, value = equals_match.groups()
        return EqualsCondition(field="method", value=value)

    meta_match = _META_EQUALS_RE.fullmatch(normalized)
    if meta_match:
        key, value = meta_match.groups()
        return MetaEqualsCondition(key=key, value=value)

    msg = f"Unsupported QAnstitution condition syntax: {expression!r}"
    raise ConditionSyntaxError(msg)
