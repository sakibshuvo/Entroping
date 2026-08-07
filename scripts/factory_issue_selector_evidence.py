from __future__ import annotations

import re
from typing import Literal

from scripts.factory_issue_selector_models import UserEvidence
from scripts.factory_issue_selector_yaml import (
    closed_mapping,
    compose_yaml,
    has_duplicate_key,
    string_value,
)

_SCHEMA_VERSION = "entroping.user-evidence.v1"
_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_status",
        "affected_journey",
        "severity",
        "source_classification",
        "verification_receipt",
    }
)
_JOURNEYS = frozenset(
    {"install", "first_run", "author", "run", "report", "integrate", "other"}
)
_SEVERITIES = frozenset({"blocker", "major", "minor"})
_SOURCES = frozenset(
    {"design_partner", "support", "public_issue", "other_user_channel"}
)
_RECEIPT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_YAML_FENCE_RE = re.compile(
    r"(?:^|\n)\s*```ya?ml\s*\n(?P<body>.*?)\n\s*```\s*(?=\n|$)",
    flags=re.IGNORECASE | re.DOTALL,
)


def parse_user_evidence(
    sections: tuple[str, ...], *, verification_label: bool
) -> UserEvidence:
    if not sections:
        warning = "user-evidence-label-mismatch" if verification_label else None
        return UserEvidence(warning=warning)
    if len(sections) != 1:
        return UserEvidence(warning="user-evidence-invalid")
    fenced = tuple(match.group("body") for match in _YAML_FENCE_RE.finditer(sections[0]))
    if len(fenced) != 1:
        return UserEvidence(warning="user-evidence-invalid")
    payload = _load_closed_yaml(fenced[0])
    if payload is None:
        return UserEvidence(warning="user-evidence-invalid")

    status = payload["evidence_status"]
    severity = payload["severity"]
    if status == "verified" and not verification_label:
        return UserEvidence(
            valid=True,
            severity=_severity(severity),
            warning="user-evidence-label-missing",
        )
    if status != "verified" and verification_label:
        return UserEvidence(
            valid=True,
            severity=_severity(severity),
            warning="user-evidence-label-mismatch",
        )
    return UserEvidence(
        valid=True,
        verified=status == "verified" and verification_label,
        severity=_severity(severity),
    )


def _load_closed_yaml(text: str) -> dict[str, str] | None:
    try:
        node = compose_yaml(text)
    except (RecursionError, ValueError):
        return None
    root = closed_mapping(node)
    if root is None or set(root) != {"user_evidence"}:
        return None
    nested = closed_mapping(root["user_evidence"])
    if nested is None or frozenset(nested) != _FIELDS:
        return None
    payload: dict[str, str] = {}
    for key, value_node in nested.items():
        if (value := string_value(value_node)) is None:
            return None
        payload[key] = value
    if payload["schema_version"] != _SCHEMA_VERSION:
        return None
    if payload["evidence_status"] not in {"verified", "unverified"}:
        return None
    if payload["affected_journey"] not in _JOURNEYS:
        return None
    if payload["severity"] not in _SEVERITIES:
        return None
    if payload["source_classification"] not in _SOURCES:
        return None
    receipt = payload["verification_receipt"]
    if _RECEIPT_RE.fullmatch(receipt) is None:
        return None
    return payload


def yaml_has_unique_keys(text: str) -> bool:
    try:
        node = compose_yaml(text)
        return node is not None and not has_duplicate_key(node)
    except (RecursionError, ValueError):
        return False


def _severity(value: str) -> Literal["blocker", "major", "minor"]:
    if value == "blocker":
        return "blocker"
    if value == "major":
        return "major"
    return "minor"
